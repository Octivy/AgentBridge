import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host_runtime.manifest import ManifestValidationError, merge_tool_namespaces, validate_manifest
from host_runtime.registry import (
    HostRegistration,
    discover_hosts,
    list_registrations,
    read_registration,
    remove_registration,
    write_registration,
)


def _registration(host_id: str = "blender-main", pid: int = 100, **overrides):
    values = {
        "host_id": host_id,
        "host_kind": "blender",
        "product": "Blender",
        "product_version": "4.2.0",
        "protocol_version": "1.0",
        "endpoint": "http://127.0.0.1:8870",
        "token": "t0ken",
        "pid": pid,
        "registered_at": "2026-08-12T00:00:00+00:00",
    }
    values.update(overrides)
    return HostRegistration(**values)


class TestRegistry:
    def test_write_read_roundtrip(self, tmp_path):
        registration = _registration()
        path = write_registration(tmp_path, registration)
        assert path.name == "blender-main-100.json"
        loaded = read_registration(path)
        assert loaded is not None
        assert loaded.host_id == "blender-main"
        assert loaded.token == "t0ken"
        assert loaded.endpoint == "http://127.0.0.1:8870"

    def test_list_ignores_invalid_files(self, tmp_path):
        write_registration(tmp_path, _registration())
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "wrong-version.json").write_text(
            json.dumps({**_registration().to_dict(), "schema_version": 99}),
            encoding="utf-8",
        )
        registrations = list_registrations(tmp_path)
        assert len(registrations) == 1
        assert registrations[0].host_id == "blender-main"

    def test_discover_prefers_latest_registration_per_host(self, tmp_path):
        write_registration(tmp_path, _registration(pid=1, registered_at="2026-08-12T00:00:00+00:00"))
        write_registration(tmp_path, _registration(pid=2, registered_at="2026-08-12T01:00:00+00:00"))
        write_registration(tmp_path, _registration(host_id="sketchup-main", pid=3))
        hosts = discover_hosts(tmp_path)
        assert [host.host_id for host in hosts] == ["blender-main", "sketchup-main"]
        blender = next(host for host in hosts if host.host_id == "blender-main")
        assert blender.pid == 2

    def test_remove_registration_by_host_and_pid(self, tmp_path):
        write_registration(tmp_path, _registration(pid=1))
        write_registration(tmp_path, _registration(pid=2))
        assert remove_registration(tmp_path, "blender-main", pid=1) == 1
        remaining = list_registrations(tmp_path)
        assert len(remaining) == 1
        assert remaining[0].pid == 2


class TestManifest:
    def test_valid_manifest_passes(self):
        manifest = {
            "schema_version": 1,
            "host_id": "blender-main",
            "host_kind": "blender",
            "product": "Blender",
            "product_version": "4.2.0",
            "protocol_version": "1.0",
            "tools": [
                {
                    "tool_name": "blender_scene_summary",
                    "display_name": "场景摘要",
                    "category": "analysis",
                    "description": "summary",
                    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                    "dry_run_supported": False,
                    "side_effect_level": "none",
                    "result_schema": {"type": "object"},
                }
            ],
        }
        normalized = validate_manifest(manifest)
        assert normalized["tools"][0]["tool_name"] == "blender_scene_summary"

    def test_manifest_without_tools_rejected(self):
        manifest = {
            "schema_version": 1,
            "host_id": "x",
            "host_kind": "x",
            "product": "x",
            "product_version": "1",
            "protocol_version": "1.0",
            "tools": [],
        }
        try:
            validate_manifest(manifest)
        except ManifestValidationError as exc:
            assert "at least one tool" in str(exc)
        else:
            raise AssertionError("empty tools should be rejected")

    def test_merge_tool_namespaces_avoids_double_prefix(self):
        manifests = [
            {
                "host_kind": "blender",
                "tools": [
                    {
                        "tool_name": "blender_scene_summary",
                        "input_schema": {"type": "object", "properties": {}},
                    },
                    {
                        "tool_name": "export_fbx",
                        "input_schema": {"type": "object", "properties": {}},
                    },
                ],
            }
        ]
        merged = merge_tool_namespaces(manifests)
        assert [tool["tool_name"] for tool in merged] == ["blender_scene_summary", "blender_export_fbx"]
