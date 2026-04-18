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
    repo.upsert_feature(feature)
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
