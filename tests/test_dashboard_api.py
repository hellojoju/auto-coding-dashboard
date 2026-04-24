"""Dashboard REST API 和 WebSocket 路由测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from dashboard.api.routes import create_dashboard_app
from dashboard.event_bus import EventBus
from dashboard.models import AgentInstance


@pytest.fixture
def event_bus(tmp_path: Path) -> EventBus:
    return EventBus(log_file=tmp_path / "events.log")


# --- Original fixtures (legacy tests) ---

@pytest.fixture
def app(event_bus: EventBus):
    return create_dashboard_app(event_bus=event_bus)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Repository-backed fixtures ---

@pytest.fixture
def repo(tmp_path: Path):
    from dashboard.state_repository import ProjectStateRepository
    return ProjectStateRepository(
        base_dir=tmp_path,
        project_id="test_proj",
        run_id="run_001",
    )


@pytest.fixture
def app_with_repo(event_bus: EventBus, repo):
    return create_dashboard_app(event_bus=event_bus, repository=repo)


@pytest.fixture
async def client_with_repo(app_with_repo):
    transport = ASGITransport(app=app_with_repo)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- GET /api/dashboard/state ---

async def test_dashboard_state_returns_snapshot(client_with_repo):
    resp = await client_with_repo.get("/api/dashboard/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "project_id" in data
    assert "agents" in data
    assert "features" in data
    assert "chat_history" in data
    assert "last_event_id" in data


async def test_dashboard_state_reflects_agents(app_with_repo, repo):
    agent = AgentInstance(id="backend-1", role="backend", instance_number=1)
    repo.upsert_agent(agent)
    transport = ASGITransport(app=app_with_repo)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/state")
        data = resp.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["id"] == "backend-1"


# --- GET /api/dashboard/events ---

async def test_dashboard_events_returns_events(client_with_repo, repo):
    repo.append_event(type="agent_log_emitted")
    repo.append_event(type="agent_status_changed")
    resp = await client_with_repo.get("/api/dashboard/events")
    data = resp.json()
    assert "events" in data
    assert len(data["events"]) == 2
    assert data["project_id"] == "test_proj"


async def test_dashboard_events_with_after_id(client_with_repo, repo):
    repo.append_event(type="e1")
    repo.append_event(type="e2")
    repo.append_event(type="e3")
    resp = await client_with_repo.get("/api/dashboard/events", params={"after_event_id": 1})
    data = resp.json()
    assert len(data["events"]) == 2
    assert data["events"][0]["type"] == "e2"


# --- POST /api/dashboard/commands ---

async def test_create_command_returns_202(client_with_repo):
    resp = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert "command_id" in data
    assert data["was_duplicate"] is False


async def test_create_command_idempotent(client_with_repo):
    """相同 idempotency_key 的重复提交应返回相同 command_id。"""
    key = "idempotent-test-key-001"
    resp1 = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm", "idempotency_key": key},
    )
    assert resp1.status_code == 202
    data1 = resp1.json()
    assert data1["was_duplicate"] is False
    cmd_id = data1["command_id"]

    # 重复提交
    resp2 = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm", "idempotency_key": key},
    )
    assert resp2.status_code == 202
    data2 = resp2.json()
    assert data2["command_id"] == cmd_id
    assert data2["was_duplicate"] is True


async def test_create_command_without_idempotency_key(client_with_repo):
    """不带 idempotency_key 的命令正常创建。"""
    resp = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "was_duplicate" in data
    assert data["was_duplicate"] is False


async def test_get_command_by_id(client_with_repo):
    create_resp = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    cmd_id = create_resp.json()["command_id"]
    resp = await client_with_repo.get(f"/api/dashboard/commands/{cmd_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["command_id"] == cmd_id
    assert data["type"] == "approve_decision"


async def test_get_unknown_command_returns_404(client_with_repo):
    resp = await client_with_repo.get("/api/dashboard/commands/nonexistent")
    assert resp.status_code == 404


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


async def test_events_support_agent_filter(client_with_repo, repo):
    repo.append_event(type="agent_status_changed", agent_id="backend-1", message="busy")
    repo.append_event(type="agent_status_changed", agent_id="frontend-1", message="idle")
    resp = await client_with_repo.get("/api/events", params={"agent_id": "backend-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert len(data["events"]) == 1
    assert data["events"][0]["agent_id"] == "backend-1"


async def test_get_agent_status_returns_flattened_shape(client_with_repo, repo):
    from dashboard.models import AgentInstance

    repo.upsert_agent(AgentInstance(id="backend-1", role="backend", instance_number=1))
    resp = await client_with_repo.get("/api/agents/backend-1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "backend-1"
    assert data["role"] == "backend"
    assert "agent" not in data


async def test_list_blocking_issues_endpoint(client_with_repo, repo):
    from dashboard.models import BlockingIssue

    repo.create_blocking_issue(
        BlockingIssue(
            feature_id="F001",
            issue_type="code_error",
            detected_by="agent",
            description="syntax error",
        )
    )
    resp = await client_with_repo.get("/api/blocking-issues")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["issues"][0]["feature_id"] == "F001"


# --- WebSocket /ws/dashboard ---

async def test_websocket_connect_and_receive_event(app, event_bus):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as _client:  # noqa: F841
        # TestClient for WebSocket
        pass  # WebSocket 测试需要 TestClient，下面单独测


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
        assert data["payload"]["agent_id"] == "backend-1"
