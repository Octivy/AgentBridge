import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from http_api.app import app


client = TestClient(app)


class TestClientUi:
    def test_ui_page_is_served(self):
        response = client.get("/ui")
        assert response.status_code == 200
        assert "AgentBridge 客户端" in response.text
        assert "软件宿主" in response.text

    def test_hosts_endpoint_shape(self):
        response = client.get("/hosts")
        assert response.status_code == 200
        data = response.json()
        assert set(data) == {"hosts", "tools", "errors"}
        assert isinstance(data["hosts"], list)
        assert isinstance(data["tools"], list)
