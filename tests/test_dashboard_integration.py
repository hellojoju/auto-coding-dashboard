"""Dashboard V2 集成场景测试 — 快照 + 命令 + 事件 + 重连。"""

import time
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient
from pathlib import Path

from dashboard.api.routes import create_dashboard_app
from dashboard.event_bus import EventBus
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import (
    AgentInstance,
    Feature,
    ChatMessage,
    Command,
    Event,
)
from dashboard.command_processor import CommandProcessor, InvalidTransition


@pytest.fixture
def event_bus(tmp_path: Path) -> EventBus:
    return EventBus(log_file=tmp_path / "events.log")


@pytest.fixture
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(
        base_dir=tmp_path,
        project_id="integration_proj",
        run_id="run_001",
    )


@pytest.fixture
def app(event_bus: EventBus, repo: ProjectStateRepository):
    return create_dashboard_app(event_bus=event_bus, repository=repo)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- 场景 1: 空快照 → 添加 Agent → 快照反映变化 ---

async def test_scenario_empty_to_populated_snapshot(client, repo):
    """初始化空快照，添加 agent 后快照应反映变化。"""
    # 1. 初始快照应为空
    resp = await client.get("/api/dashboard/state")
    data = resp.json()
    assert data["project_id"] == "integration_proj"
    assert len(data["agents"]) == 0
    assert len(data["features"]) == 0

    # 2. 添加 agent
    agent = AgentInstance(id="pm-1", role="pm", instance_number=1, status="idle")
    repo.upsert_agent(agent)

    # 3. 快照应包含该 agent
    resp = await client.get("/api/dashboard/state")
    data = resp.json()
    assert len(data["agents"]) == 1
    assert data["agents"][0]["id"] == "pm-1"
    assert data["agents"][0]["status"] == "idle"


# --- 场景 2: 命令生命周期 — pending → accepted → applied ---

async def test_scenario_command_lifecycle(client, repo):
    """创建命令 → 接受 → 应用 → 查询状态一致。"""
    # 1. 创建命令
    resp = await client.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    assert resp.status_code == 202
    cmd_id = resp.json()["command_id"]

    # 2. 查询命令应为 pending 状态
    cmd = repo.get_command(cmd_id)
    assert cmd is not None
    assert cmd.status == "pending"

    # 3. 通过命令处理器接受
    processor = client._transport.app.state.command_processor
    processor.accept(cmd)
    assert cmd.status == "accepted"

    # 4. 应用命令
    processor.apply(cmd, result={"message": "decision approved"})
    assert cmd.status == "applied"
    assert cmd.result["message"] == "decision approved"


# --- 场景 3: 事件连续性和补发 ---

async def test_scenario_event_continuity_and_replay(client, repo):
    """写入多个事件 → 断线后通过 after_id 补发。"""
    repo.append_event(type="agent_started", payload={"agent_id": "dev-1"})
    repo.append_event(type="agent_log_emitted", payload={"message": "working"})
    repo.append_event(type="agent_completed", payload={"agent_id": "dev-1"})

    # 1. 获取全部事件
    resp = await client.get("/api/dashboard/events")
    data = resp.json()
    assert len(data["events"]) == 3

    # 2. 模拟断线后补发：只请求 event_id > 1 的事件
    resp = await client.get("/api/dashboard/events", params={"after_event_id": 1})
    data = resp.json()
    assert len(data["events"]) == 2
    assert data["events"][0]["type"] == "agent_log_emitted"
    assert data["events"][1]["type"] == "agent_completed"


# --- 场景 4: WebSocket hello 握手 ---

def test_scenario_websocket_hello(app):
    """WebSocket 连接后首先收到 hello 消息。"""
    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        data = ws.receive_json()
        assert data["type"] == "hello"
        assert data["schema_version"] == 1
        assert data["project_id"] == "integration_proj"
        assert "last_event_id" in data
        assert "agents" in data
        assert "features" in data


# --- 场景 5: WebSocket 收到广播事件 ---

def test_scenario_websocket_receives_broadcast(event_bus, repo):
    """通过 event_bus 发送事件后，WebSocket 客户端能收到广播。"""
    app = create_dashboard_app(event_bus=event_bus, repository=repo)
    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        # 先收 hello
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        # 发送事件
        event_bus.emit("agent_status_changed", agent_id="dev-1", message="busy")

        # 给 WebSocket 轮询时间
        time.sleep(0.3)

        # 接收广播
        data = ws.receive_json()
        assert data["type"] == "agent_status_changed"
        assert data["payload"]["agent_id"] == "dev-1"


# --- 场景 6: 快照 last_event_id 与事件一致 ---

def test_scenario_snapshot_last_event_id_matches(repo):
    """快照的 last_event_id 应与实际事件数量一致。"""
    repo.append_event(type="e1")
    repo.append_event(type="e2")
    repo.append_event(type="e3")

    snapshot = repo.load_snapshot()
    assert snapshot.last_event_id == 3


# --- 场景 7: 命令驳回流程 ---

async def test_scenario_command_rejected(client, repo):
    """创建命令 → 驳回 → 状态为 rejected。"""
    resp = await client.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    cmd_id = resp.json()["command_id"]
    cmd = repo.get_command(cmd_id)

    processor = client._transport.app.state.command_processor
    processor.reject(cmd, reason="need more details")
    assert cmd.status == "rejected"
    assert cmd.result["reason"] == "need more details"


# --- 场景 8: 无效状态转换应报错 ---

async def test_scenario_invalid_transition(client, repo):
    """pending → applied 是非法转换，应抛异常。"""
    resp = await client.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    cmd_id = resp.json()["command_id"]
    cmd = repo.get_command(cmd_id)

    processor = client._transport.app.state.command_processor
    with pytest.raises(InvalidTransition):
        processor.apply(cmd, result={"message": "should not work"})


# --- 场景 9: 多实例 workspace 隔离 ---

async def test_scenario_workspace_isolation(client, repo):
    """两个 workspace 各有 agent，过滤后互不干扰。"""
    a1 = AgentInstance(id="dev-1", role="backend", instance_number=1, workspace_id="ws-1")
    a2 = AgentInstance(id="dev-2", role="backend", instance_number=2, workspace_id="ws-2")
    f1 = Feature(id="F001", category="auth", description="login", workspace_id="ws-1")
    f2 = Feature(id="F002", category="api", description="REST", workspace_id="ws-2")

    repo.upsert_agent(a1)
    repo.upsert_agent(a2)
    repo.upsert_feature(f1)
    repo.upsert_feature(f2)

    ws1_agents = repo.get_agents_by_workspace("ws-1")
    assert len(ws1_agents) == 1
    assert ws1_agents[0].id == "dev-1"

    ws1_features = repo.get_features_by_workspace("ws-1")
    assert len(ws1_features) == 1
    assert ws1_features[0].id == "F001"

    ws2_agents = repo.get_agents_by_workspace("ws-2")
    assert len(ws2_agents) == 1
    assert ws2_agents[0].id == "dev-2"


# --- 场景 10: 聊天消息持久化 ---

async def test_scenario_chat_persistence(client, repo):
    """用户发送消息 → 快照包含聊天历史。"""
    resp = await client.post("/api/chat", json={"content": "今天进度如何？"})
    assert resp.status_code == 200

    snapshot = repo.load_snapshot()
    assert len(snapshot.chat_history) >= 1
    messages = [m for m in snapshot.chat_history if m.content == "今天进度如何？"]
    assert len(messages) == 1
    assert messages[0].role == "user"


# --- 场景 10b: EventBus 桥接事件也持久化到 Repository ---

async def test_scenario_event_persistence_on_bridge(client, repo):
    """通过 EventBus 桥接发送的事件也应出现在 Repository 中。"""
    resp = await client.post("/api/chat", json={"content": "测试事件持久化"})
    assert resp.status_code == 200

    events = repo.get_events_after(0)
    event_types = [e.type for e in events]
    assert "pm_response" in event_types or "pm_decision" in event_types


# --- 场景 11: 完整重连恢复 ---

def test_scenario_reconnection_recovery(app, repo):
    """前端断线重连 → 加载快照 → last_event_id 一致 → 补增量事件。"""
    # 模拟一些状态
    repo.upsert_agent(AgentInstance(id="pm-1", role="pm", instance_number=1, status="running"))
    repo.upsert_agent(AgentInstance(id="dev-1", role="backend", instance_number=1, status="idle"))
    repo.upsert_feature(Feature(id="F001", category="auth", description="login", status="in_progress"))
    repo.append_event(type="agent_started", payload={"agent_id": "pm-1"})
    repo.append_event(type="feature_started", payload={"feature_id": "F001"})

    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        # hello 消息包含快照和 last_event_id
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["last_event_id"] == 2
        assert len(hello["agents"]) == 2
        assert len(hello["features"]) == 1

        # 验证 agents 状态
        agents = hello["agents"]
        pm = next(a for a in agents if a["id"] == "pm-1")
        assert pm["status"] == "running"

        dev = next(a for a in agents if a["id"] == "dev-1")
        assert dev["status"] == "idle"


# --- 场景 12: 命令状态变更广播不重复 ---

def test_scenario_no_duplicate_broadcast(event_bus, repo):
    """通过 CommandProcessor 触发 on_event 后，同一条事件不应被广播两次。"""
    app = create_dashboard_app(event_bus=event_bus, repository=repo)
    client = TestClient(app)
    with client.websocket_connect("/ws/dashboard") as ws:
        # 收 hello
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        # 创建命令
        cmd_data = {"type": "approve_decision", "target_id": "pm"}
        cmd = Command(
            command_id="cmd-no-dup",
            project_id="integration_proj",
            run_id="run_001",
            type="approve_decision",
            target_id="pm",
            issued_by="user",
        )
        repo.save_command(cmd)

        # 通过处理器接受命令（触发 on_event → event_bus.emit → 补丁推送到 WS）
        processor = app.state.command_processor
        processor.accept(cmd)

        # 给 WebSocket 处理时间
        time.sleep(0.3)

        # 收集所有广播消息
        received_events = []
        while True:
            try:
                ws.settimeout(0.5)
                msg = ws.receive_json()
                received_events.append(msg)
            except Exception:
                break

        # 统计每种事件类型的出现次数
        event_type_counts: dict[str, int] = {}
        for msg in received_events:
            t = msg.get("type", "unknown")
            event_type_counts[t] = event_type_counts.get(t, 0) + 1

        # 每种事件类型最多出现一次
        for event_type, count in event_type_counts.items():
            assert count == 1, f"Event '{event_type}' was broadcast {count} times (expected 1)"
