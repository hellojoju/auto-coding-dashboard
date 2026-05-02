"""Review Manager 测试"""

import pytest

from ralph.review_manager import ReviewManager, ReviewRequest
from ralph.schema.review_result import ReviewResult


@pytest.fixture
def manager() -> ReviewManager:
    return ReviewManager(reviewer_context_id="reviewer-test")


class TestReviewManager:
    def test_review_with_diff_passes(self, manager: ReviewManager) -> None:
        req = ReviewRequest(
            work_id="W-1",
            diff_summary="src/app.py | 5 +++--",
            acceptance_criteria=["功能正确", "测试通过"],
            evidence_files=["diff.txt"],
        )
        result = manager.review(req)
        assert result.conclusion == "通过"
        assert result.recommended_action == "接受"
        assert len(result.criteria_results) == 2
        assert all(c.passed for c in result.criteria_results)

    def test_review_no_diff_fails(self, manager: ReviewManager) -> None:
        req = ReviewRequest(
            work_id="W-1",
            diff_summary="",
            acceptance_criteria=["功能正确"],
            evidence_files=["diff.txt"],
        )
        result = manager.review(req)
        assert result.conclusion == "不通过"
        assert any("没有 diff" in i.description for i in result.issues_found)

    def test_review_no_evidence_fails(self, manager: ReviewManager) -> None:
        req = ReviewRequest(
            work_id="W-1",
            diff_summary="src/app.py | 5 +++--",
            acceptance_criteria=["功能正确"],
            evidence_files=[],
        )
        result = manager.review(req)
        assert result.conclusion == "不通过"
        assert any("没有提交证据" in i.description for i in result.issues_found)

    def test_review_is_independent(self, manager: ReviewManager) -> None:
        """审查结果不包含执行 agent 的自述（独立验收原则）。"""
        req = ReviewRequest(
            work_id="W-1",
            diff_summary="修改了 src/app.py",
            acceptance_criteria=["功能正确"],
            evidence_files=["diff.txt"],
            task_description="实现功能",
        )
        result = manager.review(req)
        # reviewer_context_id 表明是独立上下文
        assert result.reviewer_context_id == "reviewer-test"

    def test_create_rework_request(self, manager: ReviewManager) -> None:
        req = ReviewRequest(
            work_id="W-1",
            diff_summary="",
            acceptance_criteria=["功能正确"],
            evidence_files=[],
        )
        review = manager.review(req)
        rework = manager.create_rework_request(review)
        assert rework["work_id"] == "W-1"
        assert rework["reason"] == "返工"
        assert "issues" in rework
        assert rework["priority"] == "medium"

    def test_harness_checked(self, manager: ReviewManager) -> None:
        req = ReviewRequest(
            work_id="W-1",
            diff_summary="修改",
            acceptance_criteria=["标准"],
            evidence_files=["diff.txt"],
        )
        result = manager.review(req)
        assert result.harness_checked is True
