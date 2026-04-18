"""Event sequencing：event_id 单调递增和断线补发测试。"""

import pytest
from pathlib import Path
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import Event


@pytest.fixture
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(
        base_dir=tmp_path,
        project_id="test_proj",
        run_id="run_001",
    )


# --- event_id 单调递增 ---

def test_event_ids_start_at_one(repo: ProjectStateRepository) -> None:
    e = repo.append_event(Event(type="agent_log_emitted"))
    assert e.event_id == 1


def test_event_ids_are_monotonic(repo: ProjectStateRepository) -> None:
    e1 = repo.append_event(Event(type="agent_log_emitted"))
    e2 = repo.append_event(Event(type="agent_status_changed"))
    e3 = repo.append_event(Event(type="command_applied"))
    assert e3.event_id > e2.event_id > e1.event_id


def test_event_ids_consecutive(repo: ProjectStateRepository) -> None:
    ids = [repo.append_event(Event(type=f"e{i}")).event_id for i in range(5)]
    assert ids == [1, 2, 3, 4, 5]


# --- 断线补发 ---

def test_events_after_id_returns_tail(repo: ProjectStateRepository) -> None:
    repo.append_event(Event(type="e1"))
    repo.append_event(Event(type="e2"))
    repo.append_event(Event(type="e3"))
    after = repo.get_events_after(1)
    assert len(after) == 2
    assert after[0].type == "e2"
    assert after[1].type == "e3"


def test_events_after_id_empty(repo: ProjectStateRepository) -> None:
    repo.append_event(Event(type="e1"))
    after = repo.get_events_after(1)
    assert len(after) == 0


def test_events_after_id_with_limit(repo: ProjectStateRepository) -> None:
    for i in range(10):
        repo.append_event(Event(type=f"e{i}"))
    after = repo.get_events_after(0, limit=3)
    assert len(after) == 3
    assert after[0].type == "e0"
    assert after[2].type == "e2"


def test_events_after_id_beyond_last(repo: ProjectStateRepository) -> None:
    repo.append_event(Event(type="e1"))
    after = repo.get_events_after(999)
    assert len(after) == 0


# --- 事件携带 project_id / run_id ---

def test_event_carries_metadata(repo: ProjectStateRepository) -> None:
    e = repo.append_event(Event(type="test"))
    assert e.project_id == "test_proj"
    assert e.run_id == "run_001"


# --- 快照 last_event_id 与事件一致 ---

def test_snapshot_last_event_id_matches_events(repo: ProjectStateRepository) -> None:
    repo.append_event(Event(type="e1"))
    repo.append_event(Event(type="e2"))
    snapshot = repo.load_snapshot()
    assert snapshot.last_event_id == 2
