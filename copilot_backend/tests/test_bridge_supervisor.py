"""Tests for the bridge supervisor (auto-restart, budget, port attribution)."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host_config.events import ConnectionEventLog  # noqa: E402
from host_config.heal import BridgeSupervisor  # noqa: E402


def _config(host_id, *, enabled=True, auto_start=True, command="python bridge.py"):
    return SimpleNamespace(
        host_id=host_id,
        enabled=enabled,
        auto_start=auto_start,
        launch=SimpleNamespace(command=command),
    )


class FakeService:
    def __init__(self, configs):
        self._configs = configs
        self.started = []
        self.process_running = {config.host_id: False for config in configs}

    def list_configs(self):
        return list(self._configs)

    def status(self, host_id):
        return SimpleNamespace(process_running=self.process_running.get(host_id, False))

    def start(self, host_id):
        self.started.append(host_id)
        self.process_running[host_id] = True
        return self.status(host_id)


def _make(tmp_path, service, *, max_restarts=5, log_dir=None):
    events = ConnectionEventLog(path=tmp_path / "events.json")
    supervisor = BridgeSupervisor(
        service=service,
        events=events,
        interval_seconds=1,
        max_restarts=max_restarts,
        restart_window_seconds=300,
        log_dir=log_dir,
    )
    return supervisor, events


def _kinds(events):
    return [item["kind"] for item in events.list()]


def test_restarts_dead_auto_start_bridge(tmp_path):
    service = FakeService([_config("rhino")])
    supervisor, events = _make(tmp_path, service)

    supervisor.poll_once()

    assert service.started == ["rhino"]
    assert "bridge_auto_restarted" in _kinds(events)


def test_ignores_running_and_non_auto_start_hosts(tmp_path):
    running = _config("running")
    manual = _config("manual", auto_start=False)
    service = FakeService([running, manual])
    service.process_running["running"] = True  # alive, must be skipped
    supervisor, events = _make(tmp_path, service)

    supervisor.poll_once()

    assert service.started == []  # running skipped, manual not auto_start
    assert events.list() == []


def test_restart_budget_stops_restart_storm(tmp_path):
    service = FakeService([_config("rhino")])
    supervisor, events = _make(tmp_path, service, max_restarts=3)

    for _ in range(5):
        # the bridge keeps dying right after each successful start
        service.process_running["rhino"] = False
        supervisor.poll_once()

    assert len(service.started) == 3  # capped at max_restarts
    kinds = _kinds(events)
    assert kinds.count("bridge_auto_restarted") == 3
    assert "restart_budget_exhausted" in kinds


def test_port_conflict_is_attributed(tmp_path):
    log_dir = tmp_path / "host-logs"
    log_dir.mkdir()
    (log_dir / "rhino.log").write_text(
        "Traceback ... OSError: [WinError 10048] Only one usage of each socket address ...",
        encoding="utf-8",
    )
    service = FakeService([_config("rhino")])
    supervisor, events = _make(tmp_path, service, log_dir=log_dir)

    supervisor.poll_once()

    kinds = _kinds(events)
    assert "bridge_auto_restarted" in kinds
    assert "port_conflict" in kinds
    auto = next(item for item in events.list() if item["kind"] == "bridge_auto_restarted")
    assert "端口被占用" in auto["message"]


def test_status_reports_restart_counts(tmp_path):
    service = FakeService([_config("rhino")])
    supervisor, events = _make(tmp_path, service, max_restarts=5)
    service.process_running["rhino"] = False
    supervisor.poll_once()

    status = supervisor.status()
    assert status["running"] is False  # thread not started
    assert status["restarts_in_window"].get("rhino") == 1


def test_start_and_stop_thread(tmp_path):
    service = FakeService([_config("rhino")])
    supervisor, events = _make(tmp_path, service, max_restarts=5)
    assert supervisor.start() is True
    assert supervisor.running() is True
    assert supervisor.start() is False  # already running
    supervisor.stop()
    assert supervisor.running() is False
