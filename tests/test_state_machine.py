"""WorkUnit 状态机测试

覆盖：合法转换、非法转换、角色权限、转换日志
"""

import json
from pathlib import Path

import pytest

from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus
from ralph.state_machine import InvalidTransitionError, StateMachine


@pytest.fixture
def state_machine(tmp_path: Path) -> StateMachine:
    return StateMachine(tmp_path / "state")


def _make_unit(status: WorkUnitStatus = WorkUnitStatus.DRAFT) -> WorkUnit:
    return WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="API",
        acceptance_criteria=["测试通过"],
        task_harness=TaskHarness(harness_id="H-1", task_goal="test"),
        title="测试任务",
        status=status,
    )


# ── 合法转换 ─────────────────────────────────────────────────


class TestValidTransitions:
    def test_draft_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        new = state_machine.transition(unit, WorkUnitStatus.READY, actor_role="scheduler")
        assert new.status == WorkUnitStatus.READY

    def test_ready_to_running(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.READY)
        new = state_machine.transition(unit, WorkUnitStatus.RUNNING, actor_role="scheduler")
        assert new.status == WorkUnitStatus.RUNNING

    def test_running_to_needs_review(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.RUNNING)
        new = state_machine.transition(unit, WorkUnitStatus.NEEDS_REVIEW, actor_role="executor")
        assert new.status == WorkUnitStatus.NEEDS_REVIEW

    def test_running_to_failed(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.RUNNING)
        new = state_machine.transition(unit, WorkUnitStatus.FAILED, actor_role="executor")
        assert new.status == WorkUnitStatus.FAILED

    def test_running_to_blocked(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.RUNNING)
        new = state_machine.transition(unit, WorkUnitStatus.BLOCKED, actor_role="executor")
        assert new.status == WorkUnitStatus.BLOCKED

    def test_needs_review_to_accepted(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.NEEDS_REVIEW)
        new = state_machine.transition(unit, WorkUnitStatus.ACCEPTED, actor_role="scheduler")
        assert new.status == WorkUnitStatus.ACCEPTED

    def test_needs_review_to_needs_rework(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.NEEDS_REVIEW)
        new = state_machine.transition(unit, WorkUnitStatus.NEEDS_REWORK, actor_role="scheduler")
        assert new.status == WorkUnitStatus.NEEDS_REWORK

    def test_failed_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.FAILED)
        new = state_machine.transition(unit, WorkUnitStatus.READY, actor_role="scheduler")
        assert new.status == WorkUnitStatus.READY

    def test_needs_rework_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.NEEDS_REWORK)
        new = state_machine.transition(unit, WorkUnitStatus.READY)
        assert new.status == WorkUnitStatus.READY

    def test_blocked_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.BLOCKED)
        new = state_machine.transition(unit, WorkUnitStatus.READY, actor_role="scheduler")
        assert new.status == WorkUnitStatus.READY


# ── 非法转换 ─────────────────────────────────────────────────


class TestInvalidTransitions:
    def test_draft_to_running(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        with pytest.raises(InvalidTransitionError):
            state_machine.transition(unit, WorkUnitStatus.RUNNING)

    def test_draft_to_accepted(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        with pytest.raises(InvalidTransitionError):
            state_machine.transition(unit, WorkUnitStatus.ACCEPTED)

    def test_accepted_is_terminal(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.ACCEPTED)
        for status in WorkUnitStatus:
            if status == WorkUnitStatus.ACCEPTED:
                continue
            with pytest.raises(InvalidTransitionError):
                state_machine.transition(unit, status)

    def test_running_to_draft(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.RUNNING)
        with pytest.raises(InvalidTransitionError):
            state_machine.transition(unit, WorkUnitStatus.DRAFT)

    def test_error_message_contains_statuses(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        with pytest.raises(InvalidTransitionError, match="draft.*running"):
            state_machine.transition(unit, WorkUnitStatus.RUNNING)


# ── 角色权限 ─────────────────────────────────────────────────


class TestRolePermissions:
    def test_scheduler_can_draft_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        new = state_machine.transition(unit, WorkUnitStatus.READY, actor_role="scheduler")
        assert new.status == WorkUnitStatus.READY

    def test_executor_cannot_draft_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        with pytest.raises(InvalidTransitionError, match="executor"):
            state_machine.transition(unit, WorkUnitStatus.READY, actor_role="executor")

    def test_executor_can_running_to_needs_review(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.RUNNING)
        new = state_machine.transition(unit, WorkUnitStatus.NEEDS_REVIEW, actor_role="executor")
        assert new.status == WorkUnitStatus.NEEDS_REVIEW

    def test_scheduler_cannot_running_to_needs_review(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.RUNNING)
        with pytest.raises(InvalidTransitionError, match="scheduler"):
            state_machine.transition(unit, WorkUnitStatus.NEEDS_REVIEW, actor_role="scheduler")

    def test_reviewer_can_suggest_accepted(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.NEEDS_REVIEW)
        new = state_machine.transition(unit, WorkUnitStatus.ACCEPTED, actor_role="reviewer")
        assert new.status == WorkUnitStatus.ACCEPTED

    def test_reviewer_cannot_draft_to_ready(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        with pytest.raises(InvalidTransitionError, match="reviewer"):
            state_machine.transition(unit, WorkUnitStatus.READY, actor_role="reviewer")

    def test_unknown_role_not_restricted(self, state_machine: StateMachine) -> None:
        """未知角色不限制（向后兼容）"""
        unit = _make_unit(WorkUnitStatus.DRAFT)
        new = state_machine.transition(unit, WorkUnitStatus.READY, actor_role="custom_agent")
        assert new.status == WorkUnitStatus.READY


# ── 转换日志 ─────────────────────────────────────────────────


class TestTransitionLog:
    def test_log_written(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        state_machine.transition(
            unit, WorkUnitStatus.READY, actor_role="scheduler", reason="确认可执行"
        )
        transitions = state_machine.get_transitions("W-001")
        assert len(transitions) == 1
        assert transitions[0]["from_status"] == "draft"
        assert transitions[0]["to_status"] == "ready"
        assert transitions[0]["actor_role"] == "scheduler"
        assert transitions[0]["reason"] == "确认可执行"

    def test_multiple_transitions_logged(self, state_machine: StateMachine) -> None:
        unit = _make_unit(WorkUnitStatus.DRAFT)
        unit = state_machine.transition(unit, WorkUnitStatus.READY)
        unit = state_machine.transition(unit, WorkUnitStatus.RUNNING)
        unit = state_machine.transition(unit, WorkUnitStatus.NEEDS_REVIEW)
        transitions = state_machine.get_transitions("W-001")
        assert len(transitions) == 3

    def test_filter_by_work_id(self, state_machine: StateMachine) -> None:
        unit1 = _make_unit(WorkUnitStatus.DRAFT)
        unit1 = state_machine.transition(unit1, WorkUnitStatus.READY)

        unit2 = WorkUnit(
            work_id="W-002", work_type="dev", producer_role="backend",
            reviewer_role="qa", expected_output="test",
            task_harness=TaskHarness(harness_id="H-2", task_goal="test"),
            status=WorkUnitStatus.DRAFT,
        )
        unit2 = state_machine.transition(unit2, WorkUnitStatus.READY)

        assert len(state_machine.get_transitions("W-001")) == 1
        assert len(state_machine.get_transitions("W-002")) == 1
        assert len(state_machine.get_transitions()) == 2

    def test_immutability(self, state_machine: StateMachine) -> None:
        """原始 WorkUnit 不被修改。"""
        unit = _make_unit(WorkUnitStatus.DRAFT)
        state_machine.transition(unit, WorkUnitStatus.READY)
        assert unit.status == WorkUnitStatus.DRAFT  # 原始不变
