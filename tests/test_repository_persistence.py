"""ProjectStateRepository 文件持久化测试 — 验证重启后状态不丢失。"""

import pytest
from pathlib import Path
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import (
    AgentInstance, Feature, Command, Event, ChatMessage
)


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "repo_state"


@pytest.fixture
def repo(base_dir: Path) -> ProjectStateRepository:
    return ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )


# --- Agent 持久化 ---

def test_agent_survives_restart(repo: ProjectStateRepository, base_dir: Path) -> None:
    agent = AgentInstance(id="backend-1", role="backend", instance_number=1)
    repo.upsert_agent(agent)

    # 模拟重启：新实例指向同一目录
    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert len(snapshot.agents) == 1
    assert snapshot.agents[0].id == "backend-1"
    assert snapshot.agents[0].role == "backend"


def test_agent_update_persists(repo: ProjectStateRepository, base_dir: Path) -> None:
    agent = AgentInstance(id="fe-1", role="frontend", instance_number=1)
    repo.upsert_agent(agent)
    agent.status = "busy"
    agent.current_feature = "F001"
    repo.upsert_agent(agent)

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert snapshot.agents[0].status == "busy"
    assert snapshot.agents[0].current_feature == "F001"


# --- Feature 持久化 ---

def test_feature_survives_restart(repo: ProjectStateRepository, base_dir: Path) -> None:
    feature = Feature(id="F001", category="backend", description="Add user API")
    repo.upsert_feature(feature)

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert len(snapshot.features) == 1
    assert snapshot.features[0].id == "F001"


def test_feature_update_persists(repo: ProjectStateRepository, base_dir: Path) -> None:
    feature = Feature(id="F001", category="backend", description="Add user API")
    repo.upsert_feature(feature)
    feature.status = "in_progress"
    feature.started_at = "2026-04-18T10:00:00"
    repo.upsert_feature(feature, event_type="feature_updated")

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert snapshot.features[0].status == "in_progress"


# --- Command 持久化 ---

def test_command_survives_restart(repo: ProjectStateRepository, base_dir: Path) -> None:
    cmd = Command(command_id="cmd_001", type="approve_decision")
    repo.save_command(cmd)

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    retrieved = restarted.get_command("cmd_001")
    assert retrieved is not None
    assert retrieved.command_id == "cmd_001"
    assert retrieved.type == "approve_decision"


# --- Event 持久化 ---

def test_events_survive_restart(repo: ProjectStateRepository, base_dir: Path) -> None:
    repo.append_event(type="agent_log_emitted")
    repo.append_event(type="agent_status_changed")
    repo.append_event(type="command_applied")

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert snapshot.last_event_id == 3

    after = restarted.get_events_after(1)
    assert len(after) == 2
    assert after[0].type == "agent_status_changed"
    assert after[1].type == "command_applied"


# --- Chat 持久化 ---

def test_chat_survives_restart(repo: ProjectStateRepository, base_dir: Path) -> None:
    msg = ChatMessage(id="chat_1", role="user", content="进展如何？")
    repo.add_chat_message(msg)

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert len(snapshot.chat_history) == 1
    assert snapshot.chat_history[0].content == "进展如何？"


# --- 综合：所有类型一起持久化 ---

def test_full_state_survives_restart(repo: ProjectStateRepository, base_dir: Path) -> None:
    agent = AgentInstance(id="backend-1", role="backend", instance_number=1)
    repo.upsert_agent(agent)

    feature = Feature(id="F001", category="auth", description="login")
    repo.upsert_feature(feature)

    cmd = Command(command_id="cmd_001", type="start_feature")
    repo.save_command(cmd)

    repo.append_event(type="feature_started")

    msg = ChatMessage(id="chat_1", role="pm", content="开始 F001")
    repo.add_chat_message(msg)

    restarted = ProjectStateRepository(
        base_dir=base_dir,
        project_id="test_proj",
        run_id="run_001",
    )
    snapshot = restarted.load_snapshot()
    assert len(snapshot.agents) == 1
    assert len(snapshot.features) == 1
    assert len(snapshot.chat_history) == 1
    assert snapshot.last_event_id == 1
