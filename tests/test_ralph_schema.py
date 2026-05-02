"""Ralph Schema 单元测试

覆盖：WorkUnit、TaskHarness、ContextPack、Evidence、ReviewResult、Blocker
"""

import json

import pytest

from ralph.schema.blocker import Blocker
from ralph.schema.context_pack import ContextPack
from ralph.schema.evidence import Evidence
from ralph.schema.review_result import CriterionResult, Issue, ReviewResult
from ralph.schema.task_harness import RetryPolicy, TaskHarness, TimeoutPolicy
from ralph.schema.work_unit import ALLOWED_TRANSITIONS, WorkUnit, WorkUnitStatus


# ── WorkUnitStatus ───────────────────────────────────────────


class TestWorkUnitStatus:
    def test_eight_states(self) -> None:
        assert len(WorkUnitStatus) == 8

    def test_status_values(self) -> None:
        assert WorkUnitStatus.DRAFT.value == "draft"
        assert WorkUnitStatus.READY.value == "ready"
        assert WorkUnitStatus.RUNNING.value == "running"
        assert WorkUnitStatus.NEEDS_REVIEW.value == "needs_review"
        assert WorkUnitStatus.FAILED.value == "failed"
        assert WorkUnitStatus.NEEDS_REWORK.value == "needs_rework"
        assert WorkUnitStatus.BLOCKED.value == "blocked"
        assert WorkUnitStatus.ACCEPTED.value == "accepted"


# ── WorkUnit ─────────────────────────────────────────────────


class TestWorkUnit:
    def _make_unit(self, **overrides) -> WorkUnit:
        defaults = {
            "work_id": "W-001",
            "work_type": "开发",
            "producer_role": "backend",
            "reviewer_role": "qa",
            "expected_output": "一个可用的 API",
            "acceptance_criteria": ["API 返回 200", "有测试覆盖"],
            "task_harness": TaskHarness(
                harness_id="H-001",
                task_goal="实现 API",
            ),
            "title": "实现用户 API",
        }
        defaults.update(overrides)
        return WorkUnit(**defaults)

    def test_frozen(self) -> None:
        unit = self._make_unit()
        with pytest.raises(AttributeError):
            unit.work_id = "changed"  # type: ignore[misc]

    def test_default_status_draft(self) -> None:
        unit = self._make_unit()
        assert unit.status == WorkUnitStatus.DRAFT

    def test_can_transition_draft_to_ready(self) -> None:
        unit = self._make_unit()
        assert unit.can_transition_to(WorkUnitStatus.READY) is True

    def test_cannot_transition_draft_to_accepted(self) -> None:
        unit = self._make_unit()
        assert unit.can_transition_to(WorkUnitStatus.ACCEPTED) is False

    def test_running_can_go_to_needs_review(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.RUNNING)
        assert unit.can_transition_to(WorkUnitStatus.NEEDS_REVIEW) is True

    def test_running_can_go_to_failed(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.RUNNING)
        assert unit.can_transition_to(WorkUnitStatus.FAILED) is True

    def test_running_can_go_to_blocked(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.RUNNING)
        assert unit.can_transition_to(WorkUnitStatus.BLOCKED) is True

    def test_running_cannot_go_to_draft(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.RUNNING)
        assert unit.can_transition_to(WorkUnitStatus.DRAFT) is False

    def test_accepted_is_terminal(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.ACCEPTED)
        for status in WorkUnitStatus:
            assert unit.can_transition_to(status) is False

    def test_needs_review_can_go_to_accepted(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.NEEDS_REVIEW)
        assert unit.can_transition_to(WorkUnitStatus.ACCEPTED) is True

    def test_needs_review_can_go_to_needs_rework(self) -> None:
        unit = self._make_unit(status=WorkUnitStatus.NEEDS_REVIEW)
        assert unit.can_transition_to(WorkUnitStatus.NEEDS_REWORK) is True

    def test_validate_ready_passes(self) -> None:
        unit = self._make_unit()
        assert unit.validate_ready() == []

    def test_validate_ready_missing_criteria(self) -> None:
        unit = self._make_unit(acceptance_criteria=[])
        errors = unit.validate_ready()
        assert any("acceptance_criteria" in e for e in errors)

    def test_validate_ready_missing_producer(self) -> None:
        unit = self._make_unit(producer_role="")
        errors = unit.validate_ready()
        assert any("producer_role" in e for e in errors)

    def test_validate_ready_missing_reviewer(self) -> None:
        unit = self._make_unit(reviewer_role="")
        errors = unit.validate_ready()
        assert any("reviewer_role" in e for e in errors)

    def test_validate_ready_missing_harness(self) -> None:
        unit = self._make_unit(task_harness=None)
        errors = unit.validate_ready()
        assert any("task_harness" in e for e in errors)

    def test_all_transitions_covered(self) -> None:
        """确保所有 8 个状态都在转换表中。"""
        for status in WorkUnitStatus:
            assert status in ALLOWED_TRANSITIONS


# ── TaskHarness ──────────────────────────────────────────────


class TestTaskHarness:
    def test_frozen(self) -> None:
        h = TaskHarness(harness_id="H-1", task_goal="test")
        with pytest.raises(AttributeError):
            h.harness_id = "changed"  # type: ignore[misc]

    def test_validate_passes(self) -> None:
        h = TaskHarness(
            harness_id="H-1",
            task_goal="实现功能",
            context_sources=["PRD", "接口文档"],
            scope_allow=["src/api/"],
            scope_deny=["src/auth/"],
            evidence_required=["diff.txt"],
            reviewer_role="qa",
            stop_conditions=["发现大规模删除"],
        )
        assert h.validate() == []

    def test_validate_missing_fields(self) -> None:
        h = TaskHarness(harness_id="", task_goal="")
        errors = h.validate()
        assert len(errors) >= 5  # harness_id, task_goal, context_sources, scope_*, evidence, reviewer, stop

    def test_default_policies(self) -> None:
        h = TaskHarness(harness_id="H-1", task_goal="test")
        assert h.retry_policy.max_retries == 3
        assert h.timeout_policy.execution_timeout_seconds == 600


# ── ContextPack ──────────────────────────────────────────────


class TestContextPack:
    def test_frozen(self) -> None:
        cp = ContextPack(work_id="W-1")
        with pytest.raises(AttributeError):
            cp.work_id = "changed"  # type: ignore[misc]

    def test_estimate_tokens(self) -> None:
        cp = ContextPack(
            work_id="W-1",
            task_description="实现用户 API" * 100,
            prd_fragment="用户管理模块" * 50,
        )
        tokens = cp.estimate_tokens()
        assert tokens > 0


# ── Evidence ─────────────────────────────────────────────────


class TestEvidence:
    def test_frozen(self) -> None:
        e = Evidence(evidence_id="E-1", work_id="W-1", evidence_type="diff", file_path="/tmp/diff.txt")
        with pytest.raises(AttributeError):
            e.evidence_id = "changed"  # type: ignore[misc]

    def test_auto_created_at(self) -> None:
        e = Evidence(evidence_id="E-1", work_id="W-1", evidence_type="diff", file_path="/tmp/diff.txt")
        assert e.created_at != ""


# ── ReviewResult ─────────────────────────────────────────────


class TestReviewResult:
    def test_passed_property(self) -> None:
        r = ReviewResult(
            work_id="W-1",
            reviewer_context_id="ctx-1",
            review_type="功能完整性",
            conclusion="通过",
            recommended_action="接受",
        )
        assert r.passed is True

    def test_not_passed(self) -> None:
        r = ReviewResult(
            work_id="W-1",
            reviewer_context_id="ctx-1",
            review_type="功能完整性",
            conclusion="不通过",
            recommended_action="返工",
        )
        assert r.passed is False

    def test_has_critical_issues(self) -> None:
        r = ReviewResult(
            work_id="W-1",
            reviewer_context_id="ctx-1",
            review_type="功能完整性",
            conclusion="不通过",
            recommended_action="返工",
            issues_found=[Issue(description="安全漏洞", severity="critical")],
        )
        assert r.has_critical_issues is True

    def test_no_critical_issues(self) -> None:
        r = ReviewResult(
            work_id="W-1",
            reviewer_context_id="ctx-1",
            review_type="功能完整性",
            conclusion="通过",
            recommended_action="接受",
            issues_found=[Issue(description="命名不规范", severity="low")],
        )
        assert r.has_critical_issues is False


# ── Blocker ──────────────────────────────────────────────────


class TestBlocker:
    def test_frozen(self) -> None:
        b = Blocker(blocker_id="B-1", work_id="W-1", reason="缺少依赖", blocker_type="dependency")
        with pytest.raises(AttributeError):
            b.blocker_id = "changed"  # type: ignore[misc]

    def test_default_not_resolved(self) -> None:
        b = Blocker(blocker_id="B-1", work_id="W-1", reason="test", blocker_type="tool_unavailable")
        assert b.resolved is False
