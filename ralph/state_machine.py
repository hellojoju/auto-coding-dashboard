"""WorkUnit 状态机

文档依据：
- AI 协议 §7.1 状态定义（8 个状态和允许的下一阶段）
- AI 协议 §7.2 状态修改权限（调度/执行/审查 agent 各自的权限）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ralph.schema.work_unit import ALLOWED_TRANSITIONS, WorkUnit, WorkUnitStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """非法状态转换。"""

    def __init__(self, current: WorkUnitStatus, target: WorkUnitStatus, reason: str = "") -> None:
        self.current = current
        self.target = target
        self.reason = reason
        msg = f"非法状态转换: {current.value} → {target.value}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


# ── §7.2 状态修改权限 ────────────────────────────────────────
# 每个角色允许执行的状态转换

SCHEDULER_TRANSITIONS = {
    WorkUnitStatus.DRAFT: WorkUnitStatus.READY,
    WorkUnitStatus.READY: WorkUnitStatus.RUNNING,
    WorkUnitStatus.NEEDS_REVIEW: [
        WorkUnitStatus.ACCEPTED,
        WorkUnitStatus.NEEDS_REWORK,
        WorkUnitStatus.BLOCKED,
    ],
    WorkUnitStatus.FAILED: [WorkUnitStatus.READY, WorkUnitStatus.BLOCKED],
    WorkUnitStatus.BLOCKED: WorkUnitStatus.READY,
}

EXECUTOR_TRANSITIONS = {
    WorkUnitStatus.RUNNING: [
        WorkUnitStatus.NEEDS_REVIEW,
        WorkUnitStatus.FAILED,
        WorkUnitStatus.BLOCKED,
    ],
}

REVIEWER_CAN_SUGGEST = [
    WorkUnitStatus.ACCEPTED,
    WorkUnitStatus.NEEDS_REWORK,
    WorkUnitStatus.BLOCKED,
]


class StateMachine:
    """WorkUnit 状态机。

    - 严格按 §7.1 转换表执行
    - 每次转换写入 transitions.jsonl（§7.2）
    - 非法转换抛 InvalidTransitionError
    """

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._state_dir / "transitions.jsonl"

    def transition(
        self,
        unit: WorkUnit,
        new_status: WorkUnitStatus,
        actor_role: str = "",
        reason: str = "",
    ) -> WorkUnit:
        """执行状态转换，返回新的 WorkUnit。

        Args:
            unit: 当前 WorkUnit
            new_status: 目标状态
            actor_role: 执行转换的角色（scheduler/executor/reviewer）
            reason: 转换原因

        Returns:
            新的 WorkUnit（状态已更新）

        Raises:
            InvalidTransitionError: 非法转换
        """
        # 检查是否允许转换
        allowed = ALLOWED_TRANSITIONS.get(unit.status, [])
        if new_status not in allowed:
            raise InvalidTransitionError(unit.status, new_status, "不在允许的转换表中")

        # 检查角色权限
        if actor_role:
            self._check_role_permission(unit.status, new_status, actor_role)

        # 创建新 WorkUnit（不可变模式）
        from dataclasses import replace

        new_unit = replace(unit, status=new_status)

        # 写入转换日志
        self._log_transition(unit, new_status, actor_role, reason)

        logger.info(
            "状态转换: %s %s → %s (by %s)",
            unit.work_id,
            unit.status.value,
            new_status.value,
            actor_role or "system",
        )

        return new_unit

    def _check_role_permission(
        self,
        current: WorkUnitStatus,
        target: WorkUnitStatus,
        actor_role: str,
    ) -> None:
        """检查角色是否有权执行此转换（§7.2）。"""
        if actor_role == "scheduler":
            allowed = SCHEDULER_TRANSITIONS.get(current, [])
            if isinstance(allowed, WorkUnitStatus):
                allowed = [allowed]
            if target not in allowed:
                raise InvalidTransitionError(
                    current, target, f"scheduler 无权执行此转换"
                )
        elif actor_role == "executor":
            allowed = EXECUTOR_TRANSITIONS.get(current, [])
            if target not in allowed:
                raise InvalidTransitionError(
                    current, target, f"executor 无权执行此转换"
                )
        elif actor_role == "reviewer":
            # reviewer 只能建议，不能直接修改（§7.2）
            if target not in REVIEWER_CAN_SUGGEST:
                raise InvalidTransitionError(
                    current, target, f"reviewer 只能建议 accepted/needs_rework/blocked"
                )
        # 未知角色不限制（向后兼容）

    def _log_transition(
        self,
        unit: WorkUnit,
        new_status: WorkUnitStatus,
        actor_role: str,
        reason: str,
    ) -> None:
        """写入转换日志到 transitions.jsonl。"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "work_id": unit.work_id,
            "from_status": unit.status.value,
            "to_status": new_status.value,
            "actor_role": actor_role,
            "reason": reason,
        }
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("写入转换日志失败: %s", e)

    def get_transitions(self, work_id: str | None = None) -> list[dict]:
        """读取转换日志。

        Args:
            work_id: 过滤特定 work_id，None 则返回全部

        Returns:
            转换记录列表
        """
        if not self._log_path.exists():
            return []
        entries = []
        for line in self._log_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            if work_id is None or entry.get("work_id") == work_id:
                entries.append(entry)
        return entries
