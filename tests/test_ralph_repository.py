"""Ralph State Repository 测试

覆盖：WorkUnit CRUD、状态转换持久化、Evidence/ReviewResult/Blocker 持久化
"""

from pathlib import Path

import pytest

from ralph.repository import RalphRepository
from ralph.schema.blocker import Blocker
from ralph.schema.evidence import Evidence
from ralph.schema.review_result import Issue, ReviewResult
from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus


@pytest.fixture
def repo(tmp_path: Path) -> RalphRepository:
    return RalphRepository(tmp_path / ".ralph")


def _make_unit(work_id: str = "W-001", status: WorkUnitStatus = WorkUnitStatus.DRAFT) -> WorkUnit:
    return WorkUnit(
        work_id=work_id,
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="API",
        acceptance_criteria=["测试通过"],
        task_harness=TaskHarness(harness_id="H-1", task_goal="test"),
        title="测试任务",
        status=status,
    )


# ── WorkUnit CRUD ────────────────────────────────────────────


class TestWorkUnitCRUD:
    def test_save_and_get(self, repo: RalphRepository) -> None:
        unit = _make_unit()
        repo.save_work_unit(unit)
        loaded = repo.get_work_unit("W-001")
        assert loaded is not None
        assert loaded.work_id == "W-001"
        assert loaded.status == WorkUnitStatus.DRAFT

    def test_get_nonexistent(self, repo: RalphRepository) -> None:
        assert repo.get_work_unit("nonexistent") is None

    def test_list_all(self, repo: RalphRepository) -> None:
        repo.save_work_unit(_make_unit("W-001"))
        repo.save_work_unit(_make_unit("W-002"))
        assert len(repo.list_work_units()) == 2

    def test_list_filter_by_status(self, repo: RalphRepository) -> None:
        repo.save_work_unit(_make_unit("W-001", WorkUnitStatus.DRAFT))
        repo.save_work_unit(_make_unit("W-002", WorkUnitStatus.READY))
        assert len(repo.list_work_units(WorkUnitStatus.DRAFT)) == 1
        assert len(repo.list_work_units(WorkUnitStatus.READY)) == 1

    def test_delete(self, repo: RalphRepository) -> None:
        repo.save_work_unit(_make_unit())
        assert repo.delete_work_unit("W-001") is True
        assert repo.get_work_unit("W-001") is None

    def test_delete_nonexistent(self, repo: RalphRepository) -> None:
        assert repo.delete_work_unit("nonexistent") is False

    def test_frozen_after_load(self, repo: RalphRepository) -> None:
        """加载的 WorkUnit 仍然是 frozen。"""
        import pytest as _pytest

        repo.save_work_unit(_make_unit())
        loaded = repo.get_work_unit("W-001")
        assert loaded is not None
        with _pytest.raises(AttributeError):
            loaded.work_id = "changed"  # type: ignore[misc]


# ── 状态转换持久化 ───────────────────────────────────────────


class TestTransitionPersistence:
    def test_transition_persists(self, repo: RalphRepository) -> None:
        repo.save_work_unit(_make_unit())
        new_unit = repo.transition("W-001", WorkUnitStatus.READY, actor_role="scheduler")
        assert new_unit.status == WorkUnitStatus.READY

        # 重新加载验证
        loaded = repo.get_work_unit("W-001")
        assert loaded is not None
        assert loaded.status == WorkUnitStatus.READY

    def test_transition_nonexistent_raises(self, repo: RalphRepository) -> None:
        with pytest.raises(ValueError, match="不存在"):
            repo.transition("nonexistent", WorkUnitStatus.READY)

    def test_illegal_transition_raises(self, repo: RalphRepository) -> None:
        repo.save_work_unit(_make_unit())
        with pytest.raises(Exception):
            repo.transition("W-001", WorkUnitStatus.ACCEPTED)

    def test_transition_log_persists(self, repo: RalphRepository) -> None:
        repo.save_work_unit(_make_unit())
        repo.transition("W-001", WorkUnitStatus.READY, reason="确认可执行")
        transitions = repo.get_transitions("W-001")
        assert len(transitions) == 1
        assert transitions[0]["reason"] == "确认可执行"


# ── Evidence ─────────────────────────────────────────────────


class TestEvidencePersistence:
    def test_save_and_get(self, repo: RalphRepository) -> None:
        e = Evidence(evidence_id="E-1", work_id="W-1", evidence_type="diff", file_path="/tmp/diff.txt")
        repo.save_evidence(e)
        loaded = repo.get_evidence("E-1")
        assert loaded is not None
        assert loaded.evidence_type == "diff"

    def test_list_by_work_id(self, repo: RalphRepository) -> None:
        repo.save_evidence(Evidence(evidence_id="E-1", work_id="W-1", evidence_type="diff", file_path="/tmp/d1"))
        repo.save_evidence(Evidence(evidence_id="E-2", work_id="W-1", evidence_type="test", file_path="/tmp/t1"))
        repo.save_evidence(Evidence(evidence_id="E-3", work_id="W-2", evidence_type="diff", file_path="/tmp/d2"))
        assert len(repo.list_evidence("W-1")) == 2
        assert len(repo.list_evidence()) == 3


# ── ReviewResult ─────────────────────────────────────────────


class TestReviewPersistence:
    def test_save_and_get(self, repo: RalphRepository) -> None:
        r = ReviewResult(
            work_id="W-1", reviewer_context_id="ctx-1",
            review_type="功能完整性", conclusion="通过", recommended_action="接受",
            issues_found=[Issue(description="命名问题", severity="low")],
        )
        repo.save_review(r)
        loaded = repo.get_review("W-1", "ctx-1")
        assert loaded is not None
        assert loaded.conclusion == "通过"
        assert len(loaded.issues_found) == 1

    def test_list_by_work_id(self, repo: RalphRepository) -> None:
        r1 = ReviewResult(work_id="W-1", reviewer_context_id="ctx-1", review_type="test", conclusion="通过", recommended_action="接受")
        r2 = ReviewResult(work_id="W-1", reviewer_context_id="ctx-2", review_type="test", conclusion="不通过", recommended_action="返工")
        repo.save_review(r1)
        repo.save_review(r2)
        assert len(repo.list_reviews("W-1")) == 2


# ── Blocker ──────────────────────────────────────────────────


class TestBlockerPersistence:
    def test_save_and_get(self, repo: RalphRepository) -> None:
        b = Blocker(blocker_id="B-1", work_id="W-1", reason="缺少依赖", blocker_type="dependency")
        repo.save_blocker(b)
        loaded = repo.get_blocker("B-1")
        assert loaded is not None
        assert loaded.resolved is False

    def test_list_filter(self, repo: RalphRepository) -> None:
        repo.save_blocker(Blocker(blocker_id="B-1", work_id="W-1", reason="r1", blocker_type="dependency"))
        repo.save_blocker(Blocker(blocker_id="B-2", work_id="W-1", reason="r2", blocker_type="tool", resolved=True))
        assert len(repo.list_blockers(work_id="W-1")) == 2
        assert len(repo.list_blockers(resolved=False)) == 1
        assert len(repo.list_blockers(resolved=True)) == 1
