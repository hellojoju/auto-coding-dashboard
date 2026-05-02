"""ReviewResult — 审查结论

文档依据：
- AI 协议 §8.3 审查结论格式
- AI 协议 §10 独立验收规则
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CriterionResult:
    """单条验收标准的判定结果。"""

    criterion: str
    passed: bool
    evidence: str = ""  # 判定依据
    notes: str = ""


@dataclass(frozen=True)
class Issue:
    """审查发现的问题。"""

    description: str
    severity: str  # critical / high / medium / low
    suggested_action: str = ""  # 建议处理方式
    file_path: str = ""


@dataclass(frozen=True)
class ReviewResult:
    """审查结论 — 对齐 AI 协议 §8.3。

    审查 agent 不直接修改最终状态。
    最终状态由调度 agent 根据协议修改（§7.2）。
    """

    work_id: str  # 被审查任务 ID
    reviewer_context_id: str  # 独立审查上下文 ID
    review_type: str  # 功能完整性/边界状态/假实现/接口一致性等
    conclusion: str  # 通过/不通过
    recommended_action: str  # 接受/返工/补测试/阻塞

    criteria_results: list[CriterionResult] = field(default_factory=list)
    issues_found: list[Issue] = field(default_factory=list)
    evidence_checked: list[str] = field(default_factory=list)
    harness_checked: bool = False

    @property
    def passed(self) -> bool:
        return self.conclusion == "通过"

    @property
    def has_critical_issues(self) -> bool:
        return any(i.severity == "critical" for i in self.issues_found)
