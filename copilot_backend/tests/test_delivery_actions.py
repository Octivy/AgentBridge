"""Tests for consumable deliverables: open / reveal / preview / rollback."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from delivery import actions  # noqa: E402
from delivery.models import DeliverableCreate  # noqa: E402
from delivery.service import DeliveryService  # noqa: E402
from delivery.store import DeliveryStore  # noqa: E402
from host_runtime.client import HostError  # noqa: E402
from host_runtime.registry import HostRegistration  # noqa: E402


@pytest.fixture
def service(tmp_path):
    return DeliveryService(store=DeliveryStore(path=tmp_path / "deliveries.json"))


def add_file_deliverable(service, tmp_path, name="scene.png", kind="screenshot", content=b"png-bytes"):
    file_path = tmp_path / name
    file_path.write_bytes(content)
    service.add_deliverable("task-1", DeliverableCreate(name=name, kind=kind, path=str(file_path)))
    return file_path


# ----- rollback token ledger parsing -----


def test_reads_house_style_ledger(tmp_path):
    ledger = tmp_path / "house-build.json"
    ledger.write_text(
        json.dumps({"perm": "p", "created": [["地板", "rhino-box-地板"], ["后墙", "rhino-box-后墙"]]}, ensure_ascii=False),
        encoding="utf-8",
    )
    tokens = actions.read_rollback_tokens(ledger)
    assert tokens == [
        {"name": "地板", "token": "rhino-box-地板"},
        {"name": "后墙", "token": "rhino-box-后墙"},
    ]


def test_reads_plan_style_ledger_and_dedupes(tmp_path):
    ledger = tmp_path / "plan-build.json"
    ledger.write_text(
        json.dumps(
            {
                "objects": [
                    {"name": "墙A", "rollback_token": "rhino-box-A"},
                    {"name": "墙B", "rollback_token": "rhino-box-B"},
                    {"name": "墙A-重复", "rollback_token": "rhino-box-A"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tokens = actions.read_rollback_tokens(ledger)
    assert [item["token"] for item in tokens] == ["rhino-box-A", "rhino-box-B"]


def test_reads_generic_token_list(tmp_path):
    ledger = tmp_path / "tokens.json"
    ledger.write_text(json.dumps({"tokens": [{"name": "x", "token": "tok-x"}]}), encoding="utf-8")
    assert actions.read_rollback_tokens(ledger) == [{"name": "x", "token": "tok-x"}]


# ----- lookup / preview -----


def test_get_deliverable_missing_raises(service, tmp_path):
    with pytest.raises(actions.DeliverableNotFound):
        actions.get_deliverable("missing-task", 0, service)
    add_file_deliverable(service, tmp_path)
    with pytest.raises(actions.DeliverableNotFound):
        actions.get_deliverable("task-1", 5, service)


def test_preview_info_reports_type_and_size(service, tmp_path):
    add_file_deliverable(service, tmp_path, name="shot.png", content=b"12345")
    info = actions.preview_info("task-1", 0, service)
    assert info["content_type"] == "image/png"
    assert info["size"] == 5
    assert info["name"] == "shot.png"


def test_preview_missing_file_is_action_error(service, tmp_path):
    service.add_deliverable(
        "task-1", DeliverableCreate(name="ghost.png", kind="screenshot", path=str(tmp_path / "ghost.png"))
    )
    with pytest.raises(actions.DeliverableActionError):
        actions.preview_info("task-1", 0, service)


# ----- open / reveal (OS side effects stubbed) -----


def test_open_calls_os_startfile(service, tmp_path, monkeypatch):
    add_file_deliverable(service, tmp_path)
    opened = []
    monkeypatch.setattr(actions.os, "startfile", lambda path: opened.append(str(path)), raising=False)
    monkeypatch.setattr(actions.subprocess, "Popen", lambda args: opened.append(" ".join(args)))
    result = actions.open_deliverable("task-1", 0, service)
    assert result["ok"] is True
    assert opened, "open action must hand the file to the OS"


def test_reveal_uses_explorer_select_on_windows(service, tmp_path, monkeypatch):
    add_file_deliverable(service, tmp_path, name="model.blend", kind="model")
    spawned = []

    class FakePopen:
        def __init__(self, args):
            spawned.append(list(args))

    monkeypatch.setattr(actions.subprocess, "Popen", FakePopen)
    result = actions.reveal_deliverable("task-1", 0, service)
    assert result["ok"] is True
    if actions.os.name == "nt":
        assert spawned and spawned[0][0] == "explorer"
        assert spawned[0][1].startswith("/select,")


# ----- rollback -----


def _registration(host_id="rhino"):
    return HostRegistration(
        host_id=host_id,
        host_kind=host_id,
        product="Rhino",
        product_version="8.0",
        protocol_version="1",
        endpoint="http://127.0.0.1:59999",
        token="tok",
        pid=1234,
        registered_at="2026-08-14T00:00:00+00:00",
    )


def _ledger_deliverable(service, tmp_path, tokens):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps({"created": [[name, token] for name, token in tokens]}, ensure_ascii=False),
        encoding="utf-8",
    )
    service.add_deliverable(
        "task-1", DeliverableCreate(name="ledger.json", kind="tool-token-ledger", path=str(ledger))
    )


def test_rollback_rejects_token_outside_ledger(service, tmp_path, monkeypatch):
    _ledger_deliverable(service, tmp_path, [("墙", "rhino-box-墙")])
    monkeypatch.setattr(actions, "discover_hosts", lambda registry_dir=None: [_registration()])
    with pytest.raises(actions.DeliverableActionError, match="不属于"):
        actions.rollback_deliverable("task-1", 0, "rhino-box-别的", service=service)


def test_rollback_without_hosts_explains(service, tmp_path, monkeypatch):
    _ledger_deliverable(service, tmp_path, [("墙", "rhino-box-墙")])
    monkeypatch.setattr(actions, "discover_hosts", lambda registry_dir=None: [])
    with pytest.raises(actions.DeliverableActionError, match="没有已注册的在线宿主"):
        actions.rollback_deliverable("task-1", 0, "rhino-box-墙", service=service)


def test_rollback_success_through_registered_host(service, tmp_path, monkeypatch):
    _ledger_deliverable(service, tmp_path, [("墙", "rhino-box-墙")])
    monkeypatch.setattr(actions, "discover_hosts", lambda registry_dir=None: [_registration()])

    class FakeClient:
        def __init__(self, endpoint, token, timeout_seconds=10.0):
            self.endpoint = endpoint

        def rollback(self, token):
            assert token == "rhino-box-墙"
            return {"ok": True, "deleted": True}

    monkeypatch.setattr(actions, "HostClient", FakeClient)
    result = actions.rollback_deliverable("task-1", 0, "rhino-box-墙", service=service)
    assert result["ok"] is True
    assert result["host_id"] == "rhino"


def test_rollback_reports_attempted_hosts_on_failure(service, tmp_path, monkeypatch):
    _ledger_deliverable(service, tmp_path, [("墙", "rhino-box-墙")])
    monkeypatch.setattr(actions, "discover_hosts", lambda registry_dir=None: [_registration()])

    class FailingClient:
        def __init__(self, endpoint, token, timeout_seconds=10.0):
            pass

        def rollback(self, token):
            raise HostError("unknown rollback token", error_code="invalid_arguments")

    monkeypatch.setattr(actions, "HostClient", FailingClient)
    with pytest.raises(actions.DeliverableActionError, match="没有在线宿主能执行该回滚"):
        actions.rollback_deliverable("task-1", 0, "rhino-box-墙", service=service)
