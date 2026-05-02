"""测试 ExecutionLedger"""

import pytest

from core.execution_ledger import ExecutionEntry, ExecutionLedger, ExecutionStatus


@pytest.fixture
def ledger(tmp_path):
    ledger_file = tmp_path / "execution-ledger.json"
    return ExecutionLedger(ledger_file=ledger_file)


def test_log_execution(ledger):
    entry = ledger.log_execution(
        feature_id="feat-1",
        status=ExecutionStatus.COMPLETED,
        agent_id="backend-1",
        files_changed=["src/a.py"],
    )
    assert entry.feature_id == "feat-1"
    assert entry.status == ExecutionStatus.COMPLETED.value


def test_get_feature_history(ledger):
    ledger.log_execution("feat-1", ExecutionStatus.FAILED, "backend-1")
    ledger.log_execution("feat-1", ExecutionStatus.COMPLETED, "backend-1")

    history = ledger.get_feature_history("feat-1")
    assert len(history) == 2
    assert history[0].status == ExecutionStatus.FAILED.value
    assert history[1].status == ExecutionStatus.COMPLETED.value


def test_get_summary(ledger):
    ledger.log_execution("feat-1", ExecutionStatus.COMPLETED, "backend-1")
    ledger.log_execution("feat-2", ExecutionStatus.COMPLETED, "frontend-1")
    ledger.log_execution("feat-3", ExecutionStatus.FAILED, "backend-1")

    summary = ledger.get_summary()
    assert summary["total_executions"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1


def test_persistence(tmp_path):
    """验证台账数据持久化后能正确恢复"""
    ledger_file = tmp_path / "execution-ledger.json"

    # 写入数据
    ledger1 = ExecutionLedger(ledger_file=ledger_file)
    ledger1.log_execution("feat-1", ExecutionStatus.COMPLETED, "backend-1")
    ledger1.log_execution("feat-2", ExecutionStatus.FAILED, "frontend-1")

    # 重新加载
    ledger2 = ExecutionLedger(ledger_file=ledger_file)
    assert len(ledger2._entries) == 2
    assert ledger2._entries[0].feature_id == "feat-1"
    assert ledger2._entries[1].feature_id == "feat-2"


def test_entry_to_dict():
    entry = ExecutionEntry(
        feature_id="feat-1",
        status="completed",
        agent_id="backend-1",
        files_changed=["a.py"],
    )
    d = entry.to_dict()
    assert d["feature_id"] == "feat-1"
    assert d["files_changed"] == ["a.py"]


def test_entry_from_dict():
    data = {
        "feature_id": "feat-2",
        "status": "failed",
        "agent_id": "frontend-1",
        "error": "timeout",
        "files_changed": [],
        "retry_count": 1,
    }
    entry = ExecutionEntry.from_dict(data)
    assert entry.feature_id == "feat-2"
    assert entry.error == "timeout"
    assert entry.retry_count == 1
