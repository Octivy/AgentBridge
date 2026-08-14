"""HTTP route tests for connection self-healing endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import http_api.routes as routes_module  # noqa: E402
from http_api.app import app  # noqa: E402


class FakeEvents:
    def __init__(self):
        self.items = [
            {"ts": "2026-08-14T00:00:00+00:00", "host_id": "rhino", "kind": "bridge_started", "level": "info", "message": "started"}
        ]

    def list(self, limit=50):
        return list(self.items)

    def clear(self):
        self.items = []
        return {"cleared": True, "removed": 1}

    def record(self, host_id, kind, message, level="info"):
        self.items.append({"ts": "t", "host_id": host_id, "kind": kind, "level": level, "message": message})


class FakeSupervisor:
    def start(self):
        return True

    def stop(self):
        pass

    def status(self):
        return {
            "running": True,
            "interval_seconds": 5,
            "max_restarts_per_window": 5,
            "restart_window_seconds": 300,
            "restarts_in_window": {"rhino": 1},
        }


@pytest.fixture
def client(monkeypatch):
    events = FakeEvents()
    supervisor = FakeSupervisor()
    monkeypatch.setattr(routes_module, "connection_event_log", events)
    monkeypatch.setattr(routes_module, "bridge_supervisor", supervisor)
    return TestClient(app), events, supervisor


def test_list_events(client):
    http, events, _ = client
    response = http.get("/config/connection/events")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["events"][0]["kind"] == "bridge_started"


def test_clear_events(client):
    http, events, _ = client
    response = http.post("/config/connection/events/clear")
    assert response.status_code == 200
    assert response.json()["removed"] == 1
    assert events.items == []


def test_heal_status_and_controls(client):
    http, _, supervisor = client
    status = http.get("/config/connection/heal")
    assert status.status_code == 200
    assert status.json()["running"] is True
    assert status.json()["restarts_in_window"]["rhino"] == 1

    started = http.post("/config/connection/heal/start")
    assert started.status_code == 200
    assert started.json()["started"] is True

    stopped = http.post("/config/connection/heal/stop")
    assert stopped.status_code == 200
    assert stopped.json()["running"] is True  # FakeSupervisor always reports running
