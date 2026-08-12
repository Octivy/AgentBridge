import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from host_runtime.client import HostClient, HostError

from adapters.blender.host import HostAdapter


TOOLS = [
    {
        "tool_name": "demo_read",
        "display_name": "Demo Read",
        "category": "analysis",
        "description": "read-only demo tool",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "dry_run_supported": False,
        "side_effect_level": "none",
        "result_schema": {"type": "object"},
    },
    {
        "tool_name": "demo_write",
        "display_name": "Demo Write",
        "category": "modeling",
        "description": "write demo tool with rollback",
        "input_schema": {
            "type": "object",
            "properties": {"size": {"type": "number"}},
            "additionalProperties": False,
        },
        "dry_run_supported": True,
        "side_effect_level": "high",
        "result_schema": {"type": "object"},
        "rollback_supported": True,
    },
]


@pytest.fixture
def adapter():
    calls = []

    def snapshot(scope):
        return {"ok": True, "snapshot": {"schema_version": 1, "source": "demo", "scope": scope}}

    def execute(tool_name, arguments, dry_run):
        calls.append((tool_name, arguments, dry_run))
        if tool_name == "demo_read":
            return {"ok": True, "result": {"value": 42}, "dry_run": False}
        if tool_name == "demo_write":
            if dry_run:
                return {"ok": True, "result": {"preview": {"size": arguments.get("size")}}, "dry_run": True}
            return {
                "ok": True,
                "result": {"object_id": "obj-1", "size": arguments.get("size")},
                "dry_run": False,
                "rollback_token": "rb-1",
            }
        return {"ok": False, "error_code": "unknown_tool", "error_message": tool_name}

    def rollback(rollback_token):
        return {"ok": True, "result": {"rolled_back": rollback_token == "rb-1"}}

    host = HostAdapter(
        host_id="demo-main",
        host_kind="demo",
        product="Demo",
        product_version="1.0",
        tools=TOOLS,
        snapshot_fn=snapshot,
        execute_fn=execute,
        rollback_fn=rollback,
        token="secret-token",
    )
    host.start()
    try:
        yield host, calls
    finally:
        host.stop()


def _client(adapter):
    return HostClient(adapter.endpoint, adapter.token)


class TestHostAdapter:
    def test_manifest_and_health(self, adapter):
        host, _ = adapter
        manifest = _client(host).manifest()
        assert manifest["host_kind"] == "demo"
        assert manifest["protocol_version"] == "1.0"
        assert [tool["tool_name"] for tool in manifest["tools"]] == ["demo_read", "demo_write"]
        health = _client(host).health()
        assert health["ok"] is True
        assert health["product"] == "Demo"

    def test_snapshot(self, adapter):
        host, _ = adapter
        result = _client(host).snapshot({"selection": ["Cube"]})
        assert result["snapshot"]["source"] == "demo"
        assert result["snapshot"]["scope"] == {"selection": ["Cube"]}

    def test_read_tool_and_write_dry_run(self, adapter):
        host, calls = adapter
        client = _client(host)
        assert client.execute_tool("demo_read")["result"]["value"] == 42
        preview = client.execute_tool("demo_write", {"size": 2.0}, dry_run=True)
        assert preview["dry_run"] is True
        assert preview["result"]["preview"] == {"size": 2.0}
        assert calls == [("demo_read", {}, False), ("demo_write", {"size": 2.0}, True)]

    def test_write_requires_permission_request_id(self, adapter):
        host, calls = adapter
        with pytest.raises(HostError) as exc:
            _client(host).execute_tool("demo_write", {"size": 1.0})
        assert exc.value.error_code == "permission_required"
        assert calls == []

    def test_write_with_permission_and_rollback(self, adapter):
        host, calls = adapter
        client = _client(host)
        result = client.execute_tool(
            "demo_write",
            {"size": 3.0, "permission_request_id": "perm_1"},
        )
        assert result["rollback_token"] == "rb-1"
        assert client.rollback("rb-1")["result"] == {"rolled_back": True}

    def test_unknown_tool(self, adapter):
        host, _ = adapter
        with pytest.raises(HostError) as exc:
            _client(host).execute_tool("ghost")
        assert exc.value.error_code == "unknown_tool"

    def test_unauthorized_request_rejected(self, adapter):
        host, _ = adapter
        client = HostClient(host.endpoint, "wrong-token")
        with pytest.raises(HostError) as exc:
            client.health()
        assert exc.value.status_code == 401
        assert exc.value.error_code == "unauthorized"

    def test_registration_payload_shape(self, adapter):
        host, _ = adapter
        registration = host.registration()
        assert registration["host_id"] == "demo-main"
        assert registration["endpoint"].startswith("http://127.0.0.1:")
        assert registration["token"] == "secret-token"
        assert registration["schema_version"] == 1
