"""Tests for the connection lifecycle event log."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host_config.events import ConnectionEventLog  # noqa: E402


def test_record_and_list_newest_first(tmp_path):
    log = ConnectionEventLog(path=tmp_path / "events.json")
    log.record("rhino", "bridge_started", "started")
    log.record("rhino", "bridge_auto_restarted", "restarted")
    items = log.list()
    assert [item["kind"] for item in items] == ["bridge_auto_restarted", "bridge_started"]
    assert items[0]["host_id"] == "rhino"
    assert items[0]["ts"]


def test_trim_to_max_events(tmp_path):
    log = ConnectionEventLog(path=tmp_path / "events.json", max_events=3)
    for index in range(5):
        log.record("h", f"kind-{index}", f"msg-{index}")
    items = log.list(limit=10)
    assert [item["kind"] for item in items] == ["kind-4", "kind-3", "kind-2"]


def test_clear(tmp_path):
    log = ConnectionEventLog(path=tmp_path / "events.json")
    log.record("h", "kind", "msg")
    result = log.clear()
    assert result["removed"] == 1
    assert log.list() == []


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "events.json"
    first = ConnectionEventLog(path=path)
    first.record("rhino", "port_conflict", "端口占用", level="warning")
    reloaded = ConnectionEventLog(path=path)
    items = reloaded.list()
    assert len(items) == 1
    assert items[0]["kind"] == "port_conflict"
    assert items[0]["level"] == "warning"


def test_corrupt_file_recovers_empty(tmp_path):
    path = tmp_path / "events.json"
    path.write_text("{not-json", encoding="utf-8")
    log = ConnectionEventLog(path=path)
    assert log.list() == []
