import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.events import HarnessEventType, make_harness_event
from harness.event_mapper import map_execution_event_to_harness_event
from harness.results import HarnessToolResult
from harness.tools import HarnessRiskLevel, HarnessToolMetadata
from mcp_runtime.tool_registry import get_tool


def test_harness_event_has_stable_sequence_and_visibility_defaults():
    event = make_harness_event(
        session_id="hs_1",
        task_id="task_1",
        event_type=HarnessEventType.TOOL_STARTED,
        sequence=3,
        summary="Reading drawing context",
    )

    assert event.session_id == "hs_1"
    assert event.task_id == "task_1"
    assert event.sequence == 3
    assert event.visible_to_user is True
    assert event.collapse_default is False
    assert event.payload == {}


def test_tool_metadata_defaults_to_fail_closed_unknown_risk():
    metadata = HarnessToolMetadata(tool_name="custom_tool", display_name="Custom Tool")

    assert metadata.risk_level == HarnessRiskLevel.CRITICAL
    assert metadata.audit_required is True
    assert metadata.dry_run_supported is False


def test_tool_result_preserves_core_legacy_keys():
    result = HarnessToolResult(tool_name="draw_line", summary="ok")
    payload = result.to_legacy_dict()

    assert payload["ok"] is True
    assert payload["tool_name"] == "draw_line"
    assert payload["summary"] == "ok"
    assert "data" in payload
    assert "error_code" in payload
    assert "error_message" in payload


def test_registry_exposes_harness_metadata_for_write_tool():
    tool = get_tool("draw_line")

    assert tool is not None
    assert tool.risk_level == "reversible_write"
    assert tool.collapse_policy == "expanded_on_write"
    assert tool.transaction_required is True
    assert tool.audit_required is True


def test_registry_exposes_read_only_metadata_for_snapshot_tool():
    tool = get_tool("get_drawing_snapshot")

    assert tool is not None
    assert tool.risk_level == "read_only"
    assert tool.transaction_required is False


def test_legacy_execution_event_maps_to_collapsed_harness_event():
    event = map_execution_event_to_harness_event(
        session_id="hs_1",
        task_id="task_1",
        sequence=7,
        execution_event={
            "tool_name": "draw_line",
            "status": "succeeded",
            "summary": "line created",
            "details": {"dry_run": False},
        },
        trace_id="trace_1",
    )

    assert event.event_type == HarnessEventType.TOOL_RESULT
    assert event.sequence == 7
    assert event.summary == "line created"
    assert event.collapse_default is True
    assert event.payload["source"] == "legacy_execution_event"
