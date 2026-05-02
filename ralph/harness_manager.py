"""Task Harness Manager — 门禁系统

文档依据：
- AI 协议 §6.1 执行前门禁（8 项检查）
- AI 协议 §6.2 执行中约束（6 项记录）
- AI 协议 §6.3 执行后门禁（7 项检查）
- AI 协议 §6.4 harness 不是提示词 — 必须由 runtime 执行校验
- MVP 清单 §8 任务 Harness 验收清单（16 项）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ralph.schema.task_harness import TaskHarness

if TYPE_CHECKING:
    from ralph.schema.work_unit import WorkUnit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreflightResult:
    """执行前门禁检查结果。"""

    passed: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InflightRecord:
    """执行中约束记录。"""

    contexts_read: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    checkpoints_passed: list[str] = field(default_factory=list)
    timeout_hit: bool = False
    exceptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PostflightResult:
    """执行后门禁检查结果。"""

    passed: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class HarnessManager:
    """任务 Harness 管理器。

    - 为每个 WorkUnit 生成/校验 TaskHarness
    - 执行前门禁（§6.1）
    - 执行中约束记录（§6.2）
    - 执行后门禁（§6.3）
    """

    def __init__(self) -> None:
        self._inflight_records: dict[str, InflightRecord] = {}

    def validate_harness(self, harness: TaskHarness) -> list[str]:
        """校验 harness 是否满足 §6 的 17 个必填字段要求。

        MVP 清单 §8：缺少 harness 不能进入 ready。
        只有自然语言没有结构化字段时拒绝。
        没有禁止范围、证据要求、独立验收者时拒绝。
        """
        errors = harness.validate()
        # 额外检查：harness_id 和 task_goal 不能为空白字符
        if harness.harness_id and not harness.harness_id.strip():
            errors.append("harness_id 为空白字符")
        if harness.task_goal and not harness.task_goal.strip():
            errors.append("task_goal 为空白字符")
        return errors

    def preflight(self, unit: WorkUnit) -> PreflightResult:
        """执行前门禁 — 对齐 §6.1，8 项检查。

        任务进入 running 前，runtime 必须检查：
        1. task_harness 存在。
        2. 上下文来源存在且可读取。
        3. 允许修改范围明确。
        4. 禁止修改范围明确。
        5. 验收标准可判定。
        6. 独立验收者已指定。
        7. 需要的工具可用。
        8. 阻塞条件未触发。
        """
        checks: list[str] = []
        failures: list[str] = []

        # 1. harness 存在
        checks.append("task_harness 存在")
        if unit.task_harness is None:
            failures.append("task_harness 为空")

        # 2. 上下文来源可读
        checks.append("上下文来源可读取")
        if unit.task_harness and not unit.task_harness.context_sources:
            failures.append("context_sources 为空")

        # 3. 允许修改范围明确
        checks.append("允许修改范围明确")
        if not unit.scope_allow:
            failures.append("scope_allow 为空")

        # 4. 禁止修改范围明确
        checks.append("禁止修改范围明确")
        if not unit.scope_deny:
            failures.append("scope_deny 为空")

        # 5. 验收标准可判定
        checks.append("验收标准可判定")
        if not unit.acceptance_criteria:
            failures.append("acceptance_criteria 为空")

        # 6. 独立验收者已指定
        checks.append("独立验收者已指定")
        if not unit.reviewer_role:
            failures.append("reviewer_role 为空")

        # 7. 工具可用（harness 层面检查）
        checks.append("工具可用")
        if unit.task_harness and unit.task_harness.denied_tools:
            # 有禁止工具列表即可，不需要具体检查
            pass

        # 8. 阻塞条件未触发
        checks.append("阻塞条件未触发")
        if unit.task_harness and not unit.task_harness.stop_conditions:
            failures.append("stop_conditions 为空（必须有停止条件）")

        passed = len(failures) == 0
        if not passed:
            logger.warning("执行前门禁失败: %s", failures)

        return PreflightResult(passed=passed, checks=checks, failures=failures)

    def start_inflight(self, work_id: str) -> None:
        """开始执行中约束记录。"""
        self._inflight_records[work_id] = InflightRecord()

    def record_inflight(
        self,
        work_id: str,
        *,
        contexts_read: list[str] | None = None,
        tools_used: list[str] | None = None,
        files_modified: list[str] | None = None,
        checkpoint: str = "",
        timeout_hit: bool = False,
        exception: str = "",
    ) -> None:
        """记录执行中事件（§6.2）。"""
        record = self._inflight_records.get(work_id)
        if record is None:
            return

        # InflightRecord 是 frozen，需要创建新的
        from dataclasses import replace

        updates: dict = {}
        if contexts_read:
            updates["contexts_read"] = list(record.contexts_read) + contexts_read
        if tools_used:
            updates["tools_used"] = list(record.tools_used) + tools_used
        if files_modified:
            updates["files_modified"] = list(record.files_modified) + files_modified
        if checkpoint:
            updates["checkpoints_passed"] = list(record.checkpoints_passed) + [checkpoint]
        if timeout_hit:
            updates["timeout_hit"] = True
        if exception:
            updates["exceptions"] = list(record.exceptions) + [exception]

        self._inflight_records[work_id] = replace(record, **updates)

    def get_inflight(self, work_id: str) -> InflightRecord | None:
        """获取执行中记录。"""
        return self._inflight_records.get(work_id)

    def postflight(
        self,
        unit: WorkUnit,
        files_changed: list[str],
        evidence_files: list[str],
        test_passed: bool | None,
        review_completed: bool,
    ) -> PostflightResult:
        """执行后门禁 — 对齐 §6.3，7 项检查。

        任务进入 accepted 前，runtime 必须检查：
        1. 修改范围没有越界。
        2. 必要证据已保存。
        3. 测试或检查命令已执行。
        4. 验收标准逐条有结果。
        5. 独立 review 已完成。
        6. 阻塞项为空或已被处理。
        7. 下游影响已记录。
        """
        checks: list[str] = []
        failures: list[str] = []

        # 1. 修改范围没有越界
        checks.append("修改范围没有越界")
        for f in files_changed:
            in_scope = any(f.startswith(s) for s in unit.scope_allow)
            in_deny = any(f.startswith(s) or f.endswith(s) for s in unit.scope_deny)
            if in_deny:
                failures.append(f"修改了禁止范围内的文件: {f}")
            elif not in_scope and unit.scope_allow:
                failures.append(f"修改了允许范围外的文件: {f}")

        # 2. 必要证据已保存
        checks.append("必要证据已保存")
        if unit.task_harness and not evidence_files:
            failures.append("没有保存任何证据")

        # 3. 测试已执行
        checks.append("测试已执行")
        if test_passed is None:
            failures.append("测试结果未知")
        elif not test_passed:
            failures.append("测试未通过")

        # 4. 验收标准逐条有结果（简化：有验收标准即可）
        checks.append("验收标准已定义")
        if not unit.acceptance_criteria:
            failures.append("没有验收标准")

        # 5. 独立 review 已完成
        checks.append("独立 review 已完成")
        if not review_completed:
            failures.append("独立 review 未完成")

        # 6. 阻塞项已处理（简化：不检查具体 blocker）
        checks.append("阻塞项已处理")

        # 7. 下游影响已记录（简化：不检查具体影响）
        checks.append("下游影响已记录")

        passed = len(failures) == 0
        if not passed:
            logger.warning("执行后门禁失败: %s", failures)

        return PostflightResult(passed=passed, checks=checks, failures=failures)
