"""测试 TaskQueue 基本功能"""
import pytest

from core.task_queue import TaskQueue


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时数据库"""
    db_file = tmp_path / "tasks.db"
    monkeypatch.setattr("core.task_queue.TASK_DB", db_file)
    yield


def test_enqueue_and_dequeue():
    queue = TaskQueue()
    task_id = queue.enqueue("feat-1", "backend", "Test task", priority=1)
    assert task_id == "task-feat-1-backend"

    task = queue.dequeue()
    assert task is not None
    assert task["feature_id"] == "feat-1"
    # dequeue 返回 dict(row) 后再更新 DB，所以返回的 status 是 'queued'
    # 但 DB 中的实际状态已更新为 'running'
    assert task["status"] == "queued"
    assert queue.stats().get("running", 0) == 1


def test_dequeue_empty_queue():
    queue = TaskQueue()
    assert queue.dequeue() is None


def test_priority_ordering():
    queue = TaskQueue()
    queue.enqueue("feat-1", "backend", "Low priority", priority=1)
    queue.enqueue("feat-2", "frontend", "High priority", priority=5)

    task = queue.dequeue()
    assert task["feature_id"] == "feat-2"  # 高优先级先出


def test_complete_task():
    queue = TaskQueue()
    queue.enqueue("feat-1", "backend", "Test task")
    queue.dequeue()
    queue.complete("task-feat-1-backend", "Success")

    stats = queue.stats()
    assert stats.get("completed", 0) == 1


def test_retry_on_failure():
    queue = TaskQueue()
    queue.enqueue("feat-1", "backend", "Test task")
    queue.dequeue()
    should_retry = queue.fail("task-feat-1-backend", "Error occurred")
    assert should_retry is True  # retry_count < max_retries
