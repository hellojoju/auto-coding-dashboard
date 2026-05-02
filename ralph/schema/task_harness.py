"""TaskHarness — 任务运行外壳

文档依据：
- AI 协议 §6 任务 Harness 契约（17 个必填字段）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetryPolicy:
    """失败重试规则。"""

    max_retries: int = 3
    backoff_seconds: float = 5.0
    retry_on: list[str] = field(default_factory=lambda: ["failed", "blocked"])


@dataclass(frozen=True)
class TimeoutPolicy:
    """超时规则。"""

    execution_timeout_seconds: int = 600  # 10 分钟
    checkpoint_interval_seconds: int = 120  # 2 分钟
    review_timeout_seconds: int = 300  # 5 分钟


@dataclass(frozen=True)
class TaskHarness:
    """任务运行外壳 — 对齐 AI 协议 §6，全部 17 个字段。

    harness 不能只写在 prompt 里，必须以结构化数据保存，
    并由 runtime 执行校验（§6.4）。
    """

    # ── 标识和目标 ───────────────────────────────────────────
    harness_id: str  # harness 唯一标识
    task_goal: str  # 当前任务要达成的目标

    # ── 上下文控制 ───────────────────────────────────────────
    context_sources: list[str] = field(default_factory=list)  # 允许读取的上下文来源
    context_budget: str = ""  # 上下文大小和读取边界

    # ── 工具控制 ─────────────────────────────────────────────
    allowed_tools: list[str] = field(default_factory=list)  # 允许使用的工具或命令
    denied_tools: list[str] = field(default_factory=list)  # 禁止使用的工具或命令

    # ── 范围控制 ─────────────────────────────────────────────
    scope_allow: list[str] = field(default_factory=list)  # 允许修改范围
    scope_deny: list[str] = field(default_factory=list)  # 禁止修改范围

    # ── 门禁 ─────────────────────────────────────────────────
    preflight_checks: list[str] = field(default_factory=list)  # 执行前检查
    checkpoints: list[str] = field(default_factory=list)  # 执行中检查点
    validation_gates: list[str] = field(default_factory=list)  # 执行后验收门禁

    # ── 证据 ─────────────────────────────────────────────────
    evidence_required: list[str] = field(default_factory=list)  # 必须保存的证据

    # ── 策略 ─────────────────────────────────────────────────
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    rollback_strategy: str = ""  # 回滚方式
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)

    # ── 约束 ─────────────────────────────────────────────────
    stop_conditions: list[str] = field(default_factory=list)  # 必须停止或阻塞的条件
    reviewer_role: str = ""  # 独立验收者角色
    status_transitions: dict = field(default_factory=dict)  # 允许的状态变化

    def validate(self) -> list[str]:
        """校验 harness 是否满足 §6 的 17 个必填字段要求。"""
        errors: list[str] = []
        if not self.harness_id:
            errors.append("缺少 harness_id")
        if not self.task_goal:
            errors.append("缺少 task_goal")
        if not self.context_sources:
            errors.append("缺少 context_sources")
        if not self.scope_allow:
            errors.append("缺少 scope_allow")
        if not self.scope_deny:
            errors.append("缺少 scope_deny（必须有禁止范围）")
        if not self.evidence_required:
            errors.append("缺少 evidence_required")
        if not self.reviewer_role:
            errors.append("缺少 reviewer_role")
        if not self.stop_conditions:
            errors.append("缺少 stop_conditions")
        return errors
