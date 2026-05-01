"""RalphCommandHandler 测试：验证 WorkUnit 命令处理。"""

from pathlib import Path

import pytest

from dashboard.models import Command
from ralph.command_handler import RalphCommandHandler
from ralph.schema.blocker import Blocker
from ralph.schema.task_harness import RetryPolicy, TaskHarness, TimeoutPolicy
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus


@pytest.fixture
def ralph_dir(tmp_path: Path) -> Path:
    return tmp_path / ".ralph"


@pytest.fixture
def handler(ralph_dir: Path) -> RalphCommandHandler:
    return RalphCommandHandler(ralph_dir)


@pytest.fixture
def sample_work_unit() -> WorkUnit:
    return WorkUnit(
        work_id="test-work-1",
        work_type="development",
        producer_role="backend",
        reviewer_role="tech_lead",
        expected_output="实现功能",
        acceptance_criteria=["测试通过"],
        title="测试任务",
        target="实现测试功能",
        task_harness=TaskHarness(
            harness_id="harness-1",
            task_goal="完成测试任务",
            context_sources=["file", "git"],
            context_budget="100k tokens",
            scope_allow=["src/"],
            scope_deny=[".env", "secrets/"],
            evidence_required=["diff", "test_output"],
            reviewer_role="tech_lead",
            stop_conditions=["测试失败", "安全扫描未通过"],
            retry_policy=RetryPolicy(max_retries=3),
            timeout_policy=TimeoutPolicy(execution_timeout_seconds=300),
        ),
    )


class TestRalphCommandHandler:
    def test_handle_accept_review_success(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """accept_review 命令应将 WorkUnit 从 needs_review 转为 accepted。"""
        # 准备：创建 WorkUnit 并设置为 needs_review 状态
        handler._repository.save_work_unit(sample_work_unit)
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.READY, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.RUNNING, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.NEEDS_REVIEW, actor_role="executor"
        )

        # 执行：发送 accept_review 命令
        cmd = Command(
            type="accept_review",
            target_id=sample_work_unit.work_id,
            payload={"feedback": "代码审查通过"},
        )
        result = handler.handle(cmd)

        # 验证：结果成功，状态变为 accepted
        assert result["success"] is True
        assert result["new_status"] == "accepted"

        # 验证：WorkUnit 状态确实改变了
        unit = handler._repository.get_work_unit(sample_work_unit.work_id)
        assert unit.status == WorkUnitStatus.ACCEPTED

    def test_handle_request_rework_success(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """request_rework 命令应将 WorkUnit 从 needs_review 转为 needs_rework。"""
        # 准备
        handler._repository.save_work_unit(sample_work_unit)
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.READY, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.RUNNING, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.NEEDS_REVIEW, actor_role="executor"
        )

        # 执行
        cmd = Command(
            type="request_rework",
            target_id=sample_work_unit.work_id,
            payload={"reason": "需要添加更多测试"},
        )
        result = handler.handle(cmd)

        # 验证
        assert result["success"] is True
        assert result["new_status"] == "needs_rework"

        unit = handler._repository.get_work_unit(sample_work_unit.work_id)
        assert unit.status == WorkUnitStatus.NEEDS_REWORK

    def test_handle_accept_review_wrong_status(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """accept_review 在非 needs_review 状态应失败。"""
        handler._repository.save_work_unit(sample_work_unit)

        cmd = Command(
            type="accept_review",
            target_id=sample_work_unit.work_id,
            payload={},
        )
        result = handler.handle(cmd)

        assert result["success"] is False
        assert "draft" in result["message"]  # 当前是 draft 状态

    def test_handle_nonexistent_work_unit(
        self, handler: RalphCommandHandler
    ) -> None:
        """处理不存在的 WorkUnit 应返回错误。"""
        cmd = Command(
            type="accept_review",
            target_id="nonexistent",
            payload={},
        )
        result = handler.handle(cmd)

        assert result["success"] is False
        assert "不存在" in result["message"]

    def test_handle_override_accept(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """override_accept 应强制接受任意状态的 WorkUnit。"""
        handler._repository.save_work_unit(sample_work_unit)

        cmd = Command(
            type="override_accept",
            target_id=sample_work_unit.work_id,
            payload={"reason": "PM 强制接受"},
        )
        result = handler.handle(cmd)

        assert result["success"] is True
        assert result["new_status"] == "accepted"

        unit = handler._repository.get_work_unit(sample_work_unit.work_id)
        assert unit.status == WorkUnitStatus.ACCEPTED

    def test_handle_dangerous_op_confirm(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """dangerous_op_confirm 应解除 blocked 状态。"""
        handler._repository.save_work_unit(sample_work_unit)
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.READY, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.RUNNING, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.BLOCKED, actor_role="executor", reason="危险操作"
        )

        # 创建 blocker
        blocker = Blocker(
            blocker_id="block-1",
            work_id=sample_work_unit.work_id,
            blocker_type="dangerous_operation",
            reason="危险操作待确认",
        )
        handler._repository.save_blocker(blocker)

        cmd = Command(
            type="dangerous_op_confirm",
            target_id=sample_work_unit.work_id,
            payload={"blocker_id": "block-1", "confirmed": True},
        )
        result = handler.handle(cmd)

        assert result["success"] is True
        assert result["new_status"] == "ready"

        # 验证 blocker 被标记为已解决
        resolved_blocker = handler._repository.get_blocker("block-1")
        assert resolved_blocker.resolved is True

    def test_handle_execution_error_retry(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """execution_error_handle 的 retry 动作应将失败状态转为 ready。"""
        handler._repository.save_work_unit(sample_work_unit)
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.READY, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.RUNNING, actor_role="scheduler"
        )
        handler._repository.transition(
            sample_work_unit.work_id, WorkUnitStatus.FAILED, actor_role="executor", reason="执行错误"
        )

        cmd = Command(
            type="execution_error_handle",
            target_id=sample_work_unit.work_id,
            payload={"action": "retry", "reason": "修复后重试"},
        )
        result = handler.handle(cmd)

        assert result["success"] is True
        assert result["new_status"] == "ready"

    def test_unknown_command_type(
        self, handler: RalphCommandHandler, sample_work_unit: WorkUnit
    ) -> None:
        """未知命令类型应返回错误。"""
        handler._repository.save_work_unit(sample_work_unit)

        cmd = Command(
            type="unknown_command",
            target_id=sample_work_unit.work_id,
            payload={},
        )
        result = handler.handle(cmd)

        assert result["success"] is False
        assert "未知" in result["message"]


class TestRalphCommandInConsumer:
    """测试 CommandConsumer 集成 Ralph 命令。"""

    def test_consumer_processes_accept_review_command(
        self,
        tmp_path: Path,
    ) -> None:
        """CommandConsumer 应能处理 accept_review 命令。"""
        from dashboard.command_processor import CommandProcessor
        from dashboard.consumer import CommandConsumer
        from dashboard.event_bus import EventBus
        from dashboard.state_repository import ProjectStateRepository

        # 准备
        repo = ProjectStateRepository(
            base_dir=tmp_path, project_id="test", run_id="run-1"
        )
        processor = CommandProcessor()
        event_bus = EventBus()
        consumer = CommandConsumer(repo, processor, event_bus)

        # 创建 WorkUnit 并推进到 needs_review
        work_unit = WorkUnit(
            work_id="wu-1",
            work_type="development",
            producer_role="backend",
            reviewer_role="tech_lead",
            expected_output="代码",
            acceptance_criteria=["测试通过"],
            title="测试",
            target="实现功能",
            task_harness=TaskHarness(
                harness_id="harness-wu1",
                task_goal="完成测试功能",
                context_sources=["file"],
                context_budget="100k",
                scope_allow=["src/"],
                scope_deny=["secrets/"],
                evidence_required=["diff"],
                reviewer_role="tech_lead",
                stop_conditions=["测试失败"],
                retry_policy=RetryPolicy(max_retries=3),
                timeout_policy=TimeoutPolicy(execution_timeout_seconds=300),
            ),
        )
        ralph_handler = RalphCommandHandler(tmp_path / ".ralph")
        ralph_handler._repository.save_work_unit(work_unit)
        ralph_handler._repository.transition("wu-1", WorkUnitStatus.READY, actor_role="scheduler")
        ralph_handler._repository.transition("wu-1", WorkUnitStatus.RUNNING, actor_role="scheduler")
        ralph_handler._repository.transition("wu-1", WorkUnitStatus.NEEDS_REVIEW, actor_role="executor")

        # 创建命令
        cmd = repo.save_command(
            Command(type="accept_review", target_id="wu-1", payload={"feedback": "LGTM"})
        )

        # 执行
        processed = consumer.process_once()

        # 验证
        assert processed == 1
        saved_cmd = repo.get_command(cmd.command_id)
        assert saved_cmd.status == "applied"
        assert saved_cmd.result.get("success") is True

        # 验证 WorkUnit 状态改变
        updated_unit = ralph_handler._repository.get_work_unit("wu-1")
        assert updated_unit.status == WorkUnitStatus.ACCEPTED

    def test_consumer_processes_request_rework_command(
        self,
        tmp_path: Path,
    ) -> None:
        """CommandConsumer 应能处理 request_rework 命令。"""
        from dashboard.command_processor import CommandProcessor
        from dashboard.consumer import CommandConsumer
        from dashboard.event_bus import EventBus
        from dashboard.state_repository import ProjectStateRepository

        repo = ProjectStateRepository(
            base_dir=tmp_path, project_id="test", run_id="run-1"
        )
        processor = CommandProcessor()
        event_bus = EventBus()
        consumer = CommandConsumer(repo, processor, event_bus)

        work_unit = WorkUnit(
            work_id="wu-2",
            work_type="development",
            producer_role="backend",
            reviewer_role="tech_lead",
            expected_output="代码",
            acceptance_criteria=["测试通过"],
            title="测试",
            target="实现功能",
            task_harness=TaskHarness(
                harness_id="harness-wu2",
                task_goal="完成测试功能",
                context_sources=["file"],
                context_budget="100k",
                scope_allow=["src/"],
                scope_deny=["secrets/"],
                evidence_required=["diff"],
                reviewer_role="tech_lead",
                stop_conditions=["测试失败"],
                retry_policy=RetryPolicy(max_retries=3),
                timeout_policy=TimeoutPolicy(execution_timeout_seconds=300),
            ),
        )
        ralph_handler = RalphCommandHandler(tmp_path / ".ralph")
        ralph_handler._repository.save_work_unit(work_unit)
        ralph_handler._repository.transition("wu-2", WorkUnitStatus.READY, actor_role="scheduler")
        ralph_handler._repository.transition("wu-2", WorkUnitStatus.RUNNING, actor_role="scheduler")
        ralph_handler._repository.transition("wu-2", WorkUnitStatus.NEEDS_REVIEW, actor_role="executor")

        cmd = repo.save_command(
            Command(type="request_rework", target_id="wu-2", payload={"reason": "需要修改"})
        )

        processed = consumer.process_once()

        assert processed == 1
        saved_cmd = repo.get_command(cmd.command_id)
        assert saved_cmd.status == "applied"

        updated_unit = ralph_handler._repository.get_work_unit("wu-2")
        assert updated_unit.status == WorkUnitStatus.NEEDS_REWORK
