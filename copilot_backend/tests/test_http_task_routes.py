"""HTTP route tests for async agent tasks and deliverable actions."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import http_api.routes as routes_module  # noqa: E402
from http_api.app import app  # noqa: E402


class FakeRunner:
    def __init__(self) -> None:
        self.started = []
        self.confirmed = []

    async def start_task(self, request):
        self.started.append(request)
        return {"task_id": "t-1", "status": "running", "user_goal": request.message}

    def list(self, limit=20):
        return [{"task_id": "t-1", "status": "completed"}]

    def get(self, task_id):
        if task_id == "t-1":
            return {"task_id": task_id, "status": "completed"}
        return None

    async def confirm_task(self, task_id, approve):
        if task_id == "t-locked":
            raise ValueError(f"task {task_id} is not awaiting confirmation")
        if task_id != "t-1":
            raise KeyError(task_id)
        self.confirmed.append((task_id, approve))
        return {"task_id": task_id, "status": "running"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_runner(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(routes_module, "agent_task_runner", runner)
    return runner


def test_agent_task_requires_message(client, fake_runner):
    response = client.post("/agent/task", json={"message": "  "})
    assert response.status_code == 400
    assert fake_runner.started == []


def test_agent_task_starts_asynchronously(client, fake_runner):
    response = client.post("/agent/task", json={"message": "汇总场景", "approval": "annotate"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "t-1"
    assert payload["status"] == "running"
    assert fake_runner.started[0].approval == "annotate"


def test_agent_task_list_and_get(client, fake_runner):
    listed = client.get("/agent/tasks")
    assert listed.status_code == 200
    assert listed.json()[0]["task_id"] == "t-1"

    found = client.get("/agent/tasks/t-1")
    assert found.status_code == 200
    missing = client.get("/agent/tasks/nope")
    assert missing.status_code == 404


def test_agent_task_confirm_routes_decision(client, fake_runner):
    response = client.post("/agent/tasks/t-1/confirm", json={"approve": True})
    assert response.status_code == 200
    assert fake_runner.confirmed == [("t-1", True)]


def test_agent_task_confirm_unknown_and_conflict(client, fake_runner):
    assert client.post("/agent/tasks/ghost/confirm", json={"approve": True}).status_code == 404
    locked = client.post("/agent/tasks/t-locked/confirm", json={"approve": False})
    assert locked.status_code == 409


def test_delivery_action_routes_404_for_unknown_task(client):
    assert client.post("/delivery/tasks/ghost/deliverables/0/open").status_code == 404
    assert client.post("/delivery/tasks/ghost/deliverables/0/reveal").status_code == 404
    assert client.get("/delivery/tasks/ghost/deliverables/0/file").status_code == 404
    assert client.get("/delivery/tasks/ghost/deliverables/0/rollback-tokens").status_code == 404
    rollback = client.post(
        "/delivery/tasks/ghost/deliverables/0/rollback", json={"token": "rhino-box-x"}
    )
    assert rollback.status_code == 404


def test_ui_contains_bridge_only_elements(client):
    page = client.get("/ui").text
    # 桥接定位：连接 / 监控 / 自愈 / Agent 接入
    assert 'id="wizard"' in page
    assert 'id="config-list"' in page
    assert 'id="host-list"' in page
    assert 'id="event-list"' in page
    assert 'id="mcp-servers"' in page
    # 后端接口仍在，但面板不暴露交付动作
    assert "rollback-tokens" not in page
    # 面板不再暴露：给智能体下命令 / 对话 / 任务交付 / 设置(模型配置)
    assert "task-hero" not in page
    assert 'id="messages"' not in page
    assert 'id="tasks"' not in page
    assert 'id="settings"' not in page
    assert 'id="hero-progress"' not in page
    assert 'id="at-progress"' not in page
