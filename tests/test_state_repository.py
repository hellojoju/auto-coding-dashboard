"""ProjectStateRepository 读写一致性和快照测试。"""

import pytest
from pathlib import Path
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import (
    AgentInstance, Feature, Command, Event, ChatMessage, Snapshot
)


@pytest.fixture
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(
        base_dir=tmp_path,
        project_id="test_proj",
        run_id="run_001",
    )


# --- 初始快照 ---

def test_repository_load_empty_snapshot(repo: ProjectStateRepository) -> None:
    snapshot = repo.load_snapshot()
    assert snapshot.project_id == "test_proj"
    assert snapshot.run_id == "run_001"
    assert snapshot.last_event_id == 0
    assert snapshot.snapshot_version == 1
    assert len(snapshot.agents) == 0
    assert len(snapshot.features) == 0
    assert len(snapshot.chat_history) == 0


# --- Agent 管理 ---

def test_repository_add_agent(repo: ProjectStateRepository) -> None:
    agent = AgentInstance(id="backend-1", role="backend", instance_number=1)
    repo.upsert_agent(agent)
    snapshot = repo.load_snapshot()
    assert len(snapshot.agents) == 1
    assert snapshot.agents[0].id == "backend-1"


def test_repository_update_agent_status(repo: ProjectStateRepository) -> None:
    agent = AgentInstance(id="fe-1", role="frontend", instance_number=1)
    repo.upsert_agent(agent)
    agent.status = "busy"
    agent.current_feature = "F001"
    repo.upsert_agent(agent)
    snapshot = repo.load_snapshot()
    assert snapshot.agents[0].status == "busy"
    assert snapshot.agents[0].current_feature == "F001"


# --- Feature 管理 ---

def test_repository_add_feature(repo: ProjectStateRepository) -> None:
    feature = Feature(id="F001", category="backend", description="Add user API")
    repo.upsert_feature(feature)
    snapshot = repo.load_snapshot()
    assert len(snapshot.features) == 1
    assert snapshot.features[0].id == "F001"


def test_repository_update_feature_status(repo: ProjectStateRepository) -> None:
    feature = Feature(id="F001", category="backend", description="Add user API")
    repo.upsert_feature(feature)
    feature.status = "in_progress"
    feature.started_at = "2026-04-18T10:00:00"
    repo.upsert_feature(feature, event_type="feature_updated")
    snapshot = repo.load_snapshot()
    assert snapshot.features[0].status == "in_progress"


# --- Command 持久化 ---

def test_repository_save_command(repo: ProjectStateRepository) -> None:
    cmd = Command(command_id="cmd_001", type="approve_decision")
    saved = repo.save_command(cmd)
    assert saved.project_id == "test_proj"
    assert saved.run_id == "run_001"
    retrieved = repo.get_command("cmd_001")
    assert retrieved is not None
    assert retrieved.command_id == "cmd_001"


def test_repository_get_unknown_command_returns_none(repo: ProjectStateRepository) -> None:
    assert repo.get_command("nonexistent") is None


# --- Event 单调递增 ---

def test_repository_event_ids_monotonic(repo: ProjectStateRepository) -> None:
    e1 = repo.append_event(Event(type="agent_log_emitted"))
    e2 = repo.append_event(type="agent_status_changed")
    e3 = repo.append_event(type="command_applied")
    assert e1.event_id == 1
    assert e2.event_id == 2
    assert e3.event_id == 3
    assert e3.event_id > e2.event_id > e1.event_id


def test_repository_events_after_id(repo: ProjectStateRepository) -> None:
    repo.append_event(type="e1")
    repo.append_event(type="e2")
    repo.append_event(type="e3")
    after = repo.get_events_after(1)
    assert len(after) == 2
    assert after[0].type == "e2"
    assert after[1].type == "e3"


def test_repository_events_after_id_with_limit(repo: ProjectStateRepository) -> None:
    for i in range(10):
        repo.append_event(type=f"e{i}")
    after = repo.get_events_after(0, limit=3)
    assert len(after) == 3


# --- Snapshot 包含 chat_history ---

def test_repository_snapshot_includes_chat(repo: ProjectStateRepository) -> None:
    msg = ChatMessage(id="chat_1", role="user", content="进展如何？")
    repo.add_chat_message(msg)
    snapshot = repo.load_snapshot()
    assert len(snapshot.chat_history) == 1
    assert snapshot.chat_history[0].content == "进展如何？"


# --- Milestone 5: Workspace 过滤（多实例隔离预留） ---

def test_repository_get_agents_by_workspace(repo: ProjectStateRepository) -> None:
    a1 = AgentInstance(id="agent-1", role="backend", instance_number=1, workspace_id="ws-alpha")
    a2 = AgentInstance(id="agent-2", role="backend", instance_number=2, workspace_id="ws-beta")
    a3 = AgentInstance(id="agent-3", role="frontend", instance_number=1, workspace_id="ws-alpha")
    repo.upsert_agent(a1)
    repo.upsert_agent(a2)
    repo.upsert_agent(a3)

    alpha_agents = repo.get_agents_by_workspace("ws-alpha")
    assert len(alpha_agents) == 2
    assert {a.id for a in alpha_agents} == {"agent-1", "agent-3"}

    beta_agents = repo.get_agents_by_workspace("ws-beta")
    assert len(beta_agents) == 1
    assert beta_agents[0].id == "agent-2"


def test_repository_get_features_by_workspace(repo: ProjectStateRepository) -> None:
    f1 = Feature(id="F001", category="auth", description="login", workspace_id="ws-alpha")
    f2 = Feature(id="F002", category="api", description="REST", workspace_id="ws-beta")
    f3 = Feature(id="F003", category="ui", description="form", workspace_id="ws-alpha")
    repo.upsert_feature(f1)
    repo.upsert_feature(f2)
    repo.upsert_feature(f3)

    alpha_features = repo.get_features_by_workspace("ws-alpha")
    assert len(alpha_features) == 2
    assert {f.id for f in alpha_features} == {"F001", "F003"}

    beta_features = repo.get_features_by_workspace("ws-beta")
    assert len(beta_features) == 1
    assert beta_features[0].id == "F002"


# --- Command 公开查询方法 ---

def test_list_pending_commands_returns_only_pending(repo: ProjectStateRepository) -> None:
    repo.save_command(Command(command_id="cmd_1", type="approve", status="pending"))
    repo.save_command(Command(command_id="cmd_2", type="approve", status="applied"))
    repo.save_command(Command(command_id="cmd_3", type="reject", status="pending"))

    pending = repo.list_pending_commands()
    assert len(pending) == 2
    assert all(c.status == "pending" for c in pending)


def test_list_commands_by_status_filters_correctly(repo: ProjectStateRepository) -> None:
    repo.save_command(Command(command_id="c1", type="approve", status="accepted"))
    repo.save_command(Command(command_id="c2", type="approve", status="rejected"))
    repo.save_command(Command(command_id="c3", type="approve", status="pending"))

    results = repo.list_commands_by_status("accepted", "rejected")
    assert len(results) == 2
    ids = {c.command_id for c in results}
    assert ids == {"c1", "c2"}


def test_list_all_commands_returns_readonly_copy(repo: ProjectStateRepository) -> None:
    repo.save_command(Command(command_id="c1", type="approve", status="pending"))
    all_cmds = repo.list_all_commands()
    assert len(all_cmds) == 1
    # 修改返回列表不应影响 repo 内部状态
    all_cmds.clear()
    assert len(repo.list_all_commands()) == 1


# --- upsert_feature 强制事件校验 ---

def test_upsert_feature_requires_event_on_status_change(repo: ProjectStateRepository) -> None:
    """状态变更时不传 event_type 应报错。"""
    f = Feature(id="F001", category="auth", description="login", status="pending")
    repo.upsert_feature(f)

    f.status = "in_progress"
    with pytest.raises(ValueError, match="no event_type provided"):
        repo.upsert_feature(f)


def test_upsert_feature_with_event_type_succeeds(repo: ProjectStateRepository) -> None:
    """状态变更时传入 event_type 应成功，且事件已追加。"""
    f = Feature(id="F001", category="auth", description="login", status="pending")
    repo.upsert_feature(f)

    f.status = "in_progress"
    repo.upsert_feature(f, event_type="feature_updated")

    events = repo.get_events_after(0)
    assert any(e.type == "feature_updated" for e in events)
    status_event = [e for e in events if e.type == "feature_updated"][0]
    assert status_event.payload["feature_id"] == "F001"
    assert status_event.payload["old_status"] == "pending"
    assert status_event.payload["new_status"] == "in_progress"


def test_upsert_feature_no_status_change_needs_no_event(repo: ProjectStateRepository) -> None:
    """状态不变（仅改其他字段），不传 event_type 不应报错。"""
    f = Feature(id="F001", category="auth", description="login", status="pending")
    repo.upsert_feature(f)

    f.description = "login with OAuth"
    repo.upsert_feature(f)  # 不传 event_type

    snapshot = repo.load_snapshot()
    assert snapshot.features[0].description == "login with OAuth"
    assert len(repo.get_events_after(0)) == 0
