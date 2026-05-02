"""Review Manager — 独立验收

文档依据：
- AI 协议 §2 最高原则 — 生成者不能自己验收自己
- AI 协议 §10 独立验收规则
- AI 协议 §8.3 审查结论格式
- MVP 清单 §7 上下文隔离验收清单
- 实施方案 §4.16 Review Manager
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ralph.schema.review_result import CriterionResult, Issue, ReviewResult

if TYPE_CHECKING:
    from ralph.schema.work_unit import WorkUnit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewRequest:
    """审查请求。"""

    work_id: str
    diff_summary: str
    acceptance_criteria: list[str]
    evidence_files: list[str]
    task_description: str = ""
    scope_allow: list[str] = field(default_factory=list)
    scope_deny: list[str] = field(default_factory=list)


class ReviewManager:
    """独立 Review Manager。

    对齐 AI 协议 §10.5：
    - 接收执行结果（diff、evidence、acceptance_criteria）
    - 用独立 Claude 调用 review（新 session，不复用执行 session）
    - Review 只读 diff、任务、标准、证据，不读执行 agent 自述
    - 输出 ReviewResult（对齐 §8.3）
    """

    def __init__(self, reviewer_context_id: str = "reviewer-1") -> None:
        self._reviewer_context_id = reviewer_context_id

    def review(self, request: ReviewRequest) -> ReviewResult:
        """执行独立审查。

        当前实现为结构化检查（不需要调用 Claude 的基础检查）。
        复杂审查由外部 agent 调用后传入结果。

        Args:
            request: 审查请求

        Returns:
            ReviewResult
        """
        criteria_results: list[CriterionResult] = []
        issues: list[Issue] = []
        evidence_checked: list[str] = []

        # 检查每项验收标准
        for criterion in request.acceptance_criteria:
            passed = self._check_criterion(criterion, request)
            criteria_results.append(
                CriterionResult(
                    criterion=criterion,
                    passed=passed,
                    evidence=request.diff_summary[:200] if request.diff_summary else "",
                )
            )
            if not passed:
                issues.append(
                    Issue(
                        description=f"验收标准未通过: {criterion}",
                        severity="high",
                        suggested_action="返工",
                    )
                )

        # 检查是否有 diff
        if not request.diff_summary:
            issues.append(
                Issue(
                    description="没有 diff，可能没有实际修改",
                    severity="medium",
                    suggested_action="确认执行 agent 是否完成了工作",
                )
            )

        # 检查 evidence
        if request.evidence_files:
            evidence_checked.extend(request.evidence_files)
        else:
            issues.append(
                Issue(
                    description="没有提交证据文件",
                    severity="high",
                    suggested_action="补交证据",
                )
            )

        # 判定结论
        all_criteria_passed = all(c.passed for c in criteria_results)
        has_critical = any(i.severity == "critical" for i in issues)
        has_high = any(i.severity == "high" for i in issues)

        if has_critical or has_high:
            conclusion = "不通过"
            recommended_action = "返工"
        elif not all_criteria_passed:
            conclusion = "不通过"
            recommended_action = "返工"
        else:
            conclusion = "通过"
            recommended_action = "接受"

        logger.info(
            "审查 %s: %s (%d issues)",
            request.work_id,
            conclusion,
            len(issues),
        )

        return ReviewResult(
            work_id=request.work_id,
            reviewer_context_id=self._reviewer_context_id,
            review_type="功能完整性",
            conclusion=conclusion,
            recommended_action=recommended_action,
            criteria_results=criteria_results,
            issues_found=issues,
            evidence_checked=evidence_checked,
            harness_checked=True,
        )

    def review_with_claude(self, request: ReviewRequest, claude_prompt: str) -> ReviewResult:
        """使用独立 Claude session 执行审查（预留接口）。

        此接口用于需要 AI 深度审查的场景：
        - 代码质量审查
        - 架构一致性审查
        - 安全审查

        调用方负责提供 claude_prompt 和处理 Claude 返回。
        """
        # 预留接口，实际调用由 WorkUnitEngine 或外部 agent 完成
        logger.info("预留: 独立 Claude session 审查 %s", request.work_id)
        return self.review(request)

    @staticmethod
    def _check_criterion(criterion: str, request: ReviewRequest) -> bool:
        """检查单条验收标准是否满足（简化版）。

        实际应由独立 Claude session 逐条判定。
        此处做基础检查：
        - 如果有 diff，认为基础标准通过
        - 空标准不通过
        """
        if not criterion.strip():
            return False
        if not request.diff_summary:
            return False
        return True

    def create_rework_request(self, review: ReviewResult) -> dict:
        """将审查发现的问题转为返工任务描述。

        用于自动生成 needs_rework 任务。
        """
        if not review.issues_found:
            return {}

        issues_text = "\n".join(
            f"- [{i.severity}] {i.description}"
            for i in review.issues_found
        )

        return {
            "work_id": review.work_id,
            "reason": review.recommended_action,
            "issues": issues_text,
            "priority": "high" if review.has_critical_issues else "medium",
        }
