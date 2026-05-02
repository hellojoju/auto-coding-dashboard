"""WorkUnit — AI 工作单元

文档依据：
- AI 协议 §5 AI 工作单元结构（13 个必填字段）
- AI 协议 §7.1 状态定义（8 个状态）
- AI 协议 §8.1 任务定义格式（20 个字段）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ralph.schema.context_pack import ContextPack
    from ralph.schema.evidence import Evidence
    from ralph.schema.review_result import ReviewResult
    from ralph.schema.task_harness import TaskHarness


class WorkUnitStatus(Enum):
    """工作单元状态 — 对齐 AI 协议 §7.1"""

    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    NEEDS_REWORK = "needs_rework"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"


# 允许的状态转换 — 对齐 AI 协议 §7.1
ALLOWED_TRANSITIONS: dict[WorkUnitStatus, list[WorkUnitStatus]] = {
    WorkUnitStatus.DRAFT: [WorkUnitStatus.READY],
    WorkUnitStatus.READY: [WorkUnitStatus.RUNNING],
    WorkUnitStatus.RUNNING: [
        WorkUnitStatus.NEEDS_REVIEW,
        WorkUnitStatus.FAILED,
        WorkUnitStatus.BLOCKED,
    ],
    WorkUnitStatus.NEEDS_REVIEW: [
        WorkUnitStatus.ACCEPTED,
        WorkUnitStatus.NEEDS_REWORK,
        WorkUnitStatus.BLOCKED,
    ],
    WorkUnitStatus.FAILED: [WorkUnitStatus.READY, WorkUnitStatus.BLOCKED],
    WorkUnitStatus.NEEDS_REWORK: [WorkUnitStatus.READY],
    WorkUnitStatus.BLOCKED: [WorkUnitStatus.READY],
    WorkUnitStatus.ACCEPTED: [],  # 终态
}


@dataclass(frozen=True)
class WorkUnit:
    """AI 工作单元 — 对齐 AI 协议 §5 + §8.1。

    §5 定义 13 个必填字段，§8.1 定义 20 个字段。
    本 dataclass 合并两者，取并集。
    """

    # ── §5 核心字段 ──────────────────────────────────────────
    work_id: str  # 工作编号
    work_type: str  # 开发/测试/review/返工/侦察
    producer_role: str  # 生成者角色
    reviewer_role: str  # 验收者角色
    expected_output: str  # 预期输出
    acceptance_criteria: list[str] = field(default_factory=list)  # 验收标准
    task_harness: TaskHarness | None = None  # 任务运行外壳
    context_pack: ContextPack | None = None  # 上下文包
    evidence: list[Evidence] = field(default_factory=list)  # 证据
    review_result: ReviewResult | None = None  # 验收结果
    status: WorkUnitStatus = WorkUnitStatus.DRAFT  # 状态

    # ── §8.1 任务定义字段 ────────────────────────────────────
    title: str = ""  # 任务标题
    background: str = ""  # 背景说明
    target: str = ""  # 具体目标
    scope_allow: list[str] = field(default_factory=list)  # 允许修改范围
    scope_deny: list[str] = field(default_factory=list)  # 禁止修改范围
    dependencies: list[str] = field(default_factory=list)  # 依赖任务 ID
    input_files: list[str] = field(default_factory=list)  # 输入文件
    test_command: str = ""  # 测试或检查方式
    rollback_strategy: str = ""  # 回滚方式
    assumptions: list[str] = field(default_factory=list)  # 前提假设
    impact_if_wrong: str = ""  # 假设错误的影响
    risk_notes: str = ""  # 风险说明

    def can_transition_to(self, new_status: WorkUnitStatus) -> bool:
        """检查是否允许转换到新状态。"""
        return new_status in ALLOWED_TRANSITIONS.get(self.status, [])

    def validate_ready(self) -> list[str]:
        """检查是否满足进入 ready 的条件。

        对齐 AI 协议 §5：缺少 acceptance_criteria、producer_role、
        reviewer_role 或 task_harness 时不得进入 ready。
        """
        errors: list[str] = []
        if not self.acceptance_criteria:
            errors.append("缺少 acceptance_criteria")
        if not self.producer_role:
            errors.append("缺少 producer_role")
        if not self.reviewer_role:
            errors.append("缺少 reviewer_role")
        if self.task_harness is None:
            errors.append("缺少 task_harness")
        return errors
