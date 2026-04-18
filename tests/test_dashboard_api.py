"""Dashboard REST API 和 WebSocket 路由测试。"""

import json
import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from dashboard.api.routes import create_dashboard_app
from dashboard.event_bus import EventBus
from dashboard.models import AgentInstance, DashboardState


@pytest.fixture
def event_bus(tmp_path: Path) -> EventBus:
    return EventBus(log_file=tmp_path / "events.log")


@pytest.fixture
def app(event_bus: EventBus):
    return create_dashboard_app(event_bus=event_bus)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- GET /api/state ---

async def test_state_returns_empty_snapshot(client):
    resp = await client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert "features" in data
    assert "events" in data
    assert "chat_history" in data


async def test_state_returns_agents_after_update(client):
    # 先通过内部接口添加 agent
    app = client._transport.app
    state = app.state.dashboard_state
    state.agents.append(AgentInstance(id="backend-1", role="backend", instance_number=1))
    resp = await client.get("/api/state")
    data = resp.json()
    assert len(data["agents"]) == 1
    assert data["agents"][0]["id"] == "backend-1"


# --- POST /api/chat ---

async def test_chat_accepts_user_message(client):
    resp = await client.post("/api/chat", json={"content": "进展如何？"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


async def test_chat_rejects_empty_message(client):
    resp = await client.post("/api/chat", json={"content": ""})
    assert resp.status_code == 422


# --- POST /api/approve ---

async def test_approve_records_decision(client):
    resp = await client.post("/api/approve", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# --- POST /api/reject ---

async def test_reject_records_decision(client):
    resp = await client.post("/api/reject", json={"reason": "需要更多测试"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# --- POST /api/pause ---

async def test_pause_unknown_agent_returns_404(client):
    resp = await client.post("/api/pause", json={"agent_id": "nonexistent"})
    assert resp.status_code == 404


# --- POST /api/resume ---

async def test_resume_unknown_agent_returns_404(client):
    resp = await client.post("/api/resume", json={"agent_id": "nonexistent"})
    assert resp.status_code == 404


# --- POST /api/retry ---

async def test_retry_feature(client):
    resp = await client.post("/api/retry", json={"feature_id": "F001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# --- POST /api/skip ---

async def test_skip_feature(client):
    resp = await client.post("/api/skip", json={"feature_id": "F001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# --- GET /api/events ---

async def test_events_returns_list(client, event_bus):
    event_bus.emit("agent_log", agent_id="test", message="hello")
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


# --- WebSocket /ws/dashboard ---

async def test_websocket_connect_and_receive_event(app, event_bus):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # TestClient for WebSocket
        pass  # WebSocket 测试需要 TestClient，下面单独测


from fastapi.testclient import TestClient


def test_websocket_connection(app):
    """WebSocket 连接成功并收到 hello 消息。"""
    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        data = ws.receive_json()
        assert data["type"] == "hello"
        assert "schema_version" in data
        assert "project_id" in data
        assert "last_event_id" in data


def test_websocket_receives_broadcast(event_bus):
    """发送事件后 WebSocket 客户端能收到。"""
    import time
    app = create_dashboard_app(event_bus=event_bus)
    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        # 先收 hello
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        # 发送事件
        event_bus.emit("agent_status_changed", agent_id="backend-1", message="busy")
        # 给 WebSocket 轮询一点时间
        time.sleep(0.3)
        # 接收广播
        data = ws.receive_json()
        assert data["type"] == "agent_status_changed"
        assert data["agent_id"] == "backend-1"
