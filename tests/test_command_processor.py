"""CommandProcessor 命令状态机测试。"""

import pytest

from dashboard.command_processor import CommandProcessor, InvalidTransitionError
from dashboard.models import Command


def test_command_transitions_pending_to_accepted() -> None:
    cmd = Command(command_id="cmd_001", type="approve_decision", status="pending")
    processor = CommandProcessor()
    processor.accept(cmd)
    assert cmd.status == "accepted"


def test_command_transitions_accepted_to_applied() -> None:
    cmd = Command(command_id="cmd_001", type="approve_decision", status="accepted")
    processor = CommandProcessor()
    processor.apply(cmd, result={"message": "done"})
    assert cmd.status == "applied"


def test_command_transitions_pending_to_rejected() -> None:
    cmd = Command(command_id="cmd_002", type="approve_decision", status="pending")
    processor = CommandProcessor()
    processor.reject(cmd, reason="not ready")
    assert cmd.status == "rejected"
    assert cmd.result["reason"] == "not ready"


def test_command_transitions_accepted_to_failed() -> None:
    cmd = Command(command_id="cmd_003", type="approve_decision", status="accepted")
    processor = CommandProcessor()
    processor.fail(cmd, reason="timeout")
    assert cmd.status == "failed"
    assert cmd.result["reason"] == "timeout"


def test_command_transitions_pending_to_cancelled() -> None:
    cmd = Command(command_id="cmd_004", type="approve_decision", status="pending")
    processor = CommandProcessor()
    processor.cancel(cmd)
    assert cmd.status == "cancelled"


def test_invalid_transition_raises() -> None:
    cmd = Command(command_id="cmd_005", type="noop", status="applied")
    processor = CommandProcessor()
    with pytest.raises(InvalidTransitionError):
        processor.accept(cmd)


def test_on_event_callback() -> None:
    events: list = []
    processor = CommandProcessor(on_event=lambda e: events.append(e))
    cmd = Command(command_id="cmd_006", type="approve_decision", status="pending")
    processor.accept(cmd)
    assert len(events) == 1
    assert events[0].type == "command_accepted"


def test_reject_emits_event() -> None:
    events: list = []
    processor = CommandProcessor(on_event=lambda e: events.append(e))
    cmd = Command(command_id="cmd_007", type="approve_decision", status="pending")
    processor.reject(cmd, reason="nope")
    assert len(events) == 1
    assert events[0].type == "command_rejected"
