"""Ralph Command Handler — 处理 WorkUnit 相关的命令。

将审批中心的用户操作转换为 WorkUnit 状态转换。
支持命令：accept_review, request_rework, override_accept, expand_scope,
          resolve_blocker, retry_work_unit, cancel_work_unit,
          prepare_work_unit, execute_work_unit, dangerous_op_confirm。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from dashboard.models import Command
from ralph.repository import RalphRepository
from ralph.schema.work_unit import WorkUnitStatus

logger = logging.getLogger(__name__)


class RalphCommandHandler:
    """处理 Ralph WorkUnit 相关命令。"""

    def __init__(self, ralph_dir: Path, engine: Any = None) -> None:
        self._ralph_dir = Path(ralph_dir)
        self._repository = RalphRepository(self._ralph_dir)
        self._engine = engine

    def handle(self, command: Command) -> dict[str, Any]:
        """处理 Ralph 命令，返回结果字典。

        Args:
            command: 包含 type, target_id, payload 的 Command

        Returns:
            {"success": bool, "message": str, "work_id": str, "new_status": str}
        """
        cmd_type = command.type
        work_id = command.target_id
        payload = command.payload or {}

        logger.info("处理 Ralph 命令: %s, work_id: %s", cmd_type, work_id)

        # 对于 prepare_work_unit，work_id 可以为空
        if cmd_type != "prepare_work_unit":
            unit = self._repository.get_work_unit(work_id)
            if unit is None:
                return {
                    "success": False,
                    "message": f"WorkUnit {work_id} 不存在",
                    "work_id": work_id,
                    "new_status": None,
                }

        try:
            handler_map = {
                "accept_review": self._handle_accept_review,
                "request_rework": self._handle_request_rework,
                "override_accept": self._handle_override_accept,
                "expand_scope": self._handle_expand_scope,
                "dangerous_op_confirm": self._handle_dangerous_op_confirm,
                "resolve_blocker": self._handle_resolve_blocker,
                "retry_work_unit": self._handle_retry_work_unit,
                "cancel_work_unit": self._handle_cancel_work_unit,
                "prepare_work_unit": self._handle_prepare_work_unit,
                "execute_work_unit": self._handle_execute_work_unit,
            }

            handler = handler_map.get(cmd_type)
            if handler is None:
                return {
                    "success": False,
                    "message": f"未知的 Ralph 命令类型: {cmd_type}",
                    "work_id": work_id,
                    "new_status": None,
                }
            return handler(work_id, payload)
        except Exception as e:
            logger.error("处理 Ralph 命令失败: %s", e)
            current = self._repository.get_work_unit(work_id)
            return {
                "success": False,
                "message": str(e),
                "work_id": work_id,
                "new_status": current.status.value if current else None,
            }

    # ------------------------------------------------------------------
    # 审查相关命令
    # ------------------------------------------------------------------

    def _handle_accept_review(self, work_id: str, payload: dict) -> dict[str, Any]:
        """接受审查结果：needs_review → accepted。"""
        unit = self._repository.get_work_unit(work_id)
        if unit.status != WorkUnitStatus.NEEDS_REVIEW:
            return {
                "success": False,
                "message": f"WorkUnit 当前状态为 {unit.status.value}，无法执行 accept_review",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        feedback = payload.get("feedback", "审查通过")
        new_unit = self._repository.transition(
            work_id, WorkUnitStatus.ACCEPTED, actor_role="scheduler", reason=feedback
        )

        return {
            "success": True,
            "message": "审查已接受",
            "work_id": work_id,
            "new_status": new_unit.status.value,
        }

    def _handle_request_rework(self, work_id: str, payload: dict) -> dict[str, Any]:
        """请求返工：needs_review → needs_rework。"""
        unit = self._repository.get_work_unit(work_id)
        if unit.status != WorkUnitStatus.NEEDS_REVIEW:
            return {
                "success": False,
                "message": f"WorkUnit 当前状态为 {unit.status.value}，无法执行 request_rework",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        reason = payload.get("reason", "需要返工")
        new_unit = self._repository.transition(
            work_id, WorkUnitStatus.NEEDS_REWORK, actor_role="scheduler", reason=reason
        )

        return {
            "success": True,
            "message": f"已请求返工: {reason}",
            "work_id": work_id,
            "new_status": new_unit.status.value,
        }

    def _handle_override_accept(self, work_id: str, payload: dict) -> dict[str, Any]:
        """强制接受（覆盖审查结果）：任意状态 → accepted。"""
        reason = payload.get("reason", "PM 强制接受")

        unit = self._repository.get_work_unit(work_id)
        new_unit = replace(unit, status=WorkUnitStatus.ACCEPTED)
        self._repository.save_work_unit(new_unit)

        logger.info("PM 强制接受 WorkUnit %s: %s", work_id, reason)

        return {
            "success": True,
            "message": f"已强制接受: {reason}",
            "work_id": work_id,
            "new_status": WorkUnitStatus.ACCEPTED.value,
        }

    # ------------------------------------------------------------------
    # 范围扩展命令
    # ------------------------------------------------------------------

    def _handle_expand_scope(self, work_id: str, payload: dict) -> dict[str, Any]:
        """扩展范围请求：记录扩展请求，等待确认。"""
        scope_additions = payload.get("scope_additions", [])
        reason = payload.get("reason", "")

        logger.info("WorkUnit %s 范围扩展请求: %s, 原因: %s", work_id, scope_additions, reason)

        from ralph.schema.blocker import Blocker

        blocker = Blocker(
            blocker_id=f"scope_expand_{work_id}_{int(time.time())}",
            work_id=work_id,
            blocker_type="scope_expansion_pending",
            reason=f"范围扩展请求: {reason}",
        )
        self._repository.save_blocker(blocker)

        return {
            "success": True,
            "message": "范围扩展请求已记录，等待确认",
            "work_id": work_id,
            "new_status": self._repository.get_work_unit(work_id).status.value,
            "blocker_id": blocker.blocker_id,
        }

    # ------------------------------------------------------------------
    # 危险操作确认
    # ------------------------------------------------------------------

    def _handle_dangerous_op_confirm(self, work_id: str, payload: dict) -> dict[str, Any]:
        """确认危险操作：解除 blocker 并继续执行。"""
        blocker_id = payload.get("blocker_id", "")
        confirmed = payload.get("confirmed", True)

        if blocker_id:
            blocker = self._repository.get_blocker(blocker_id)
            if blocker is not None:
                updated_blocker = replace(
                    blocker,
                    resolved=True,
                    resolution="confirmed" if confirmed else "cancelled",
                )
                self._repository.save_blocker(updated_blocker)

        if confirmed:
            unit = self._repository.get_work_unit(work_id)
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason="危险操作已确认"
                )
                return {
                    "success": True,
                    "message": "危险操作已确认，继续执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        return {
            "success": True,
            "message": "危险操作已取消" if not confirmed else "危险操作已处理",
            "work_id": work_id,
            "new_status": self._repository.get_work_unit(work_id).status.value,
        }

    # ------------------------------------------------------------------
    # 阻塞解决（统一入口，替代旧的六个分散处理器）
    # ------------------------------------------------------------------

    def _handle_resolve_blocker(self, work_id: str, payload: dict) -> dict[str, Any]:
        """解决阻塞项 — 统一入口。

        支持 payload 字段：
        - blocker_id: 要解决的 blocker ID
        - resolution: 'approve' | 'reject' | 'retry' | 'skip' | 'abort' | 'resume'
        - reason: 解决原因说明
        - 其他类型特定字段
        """
        blocker_id = payload.get("blocker_id", "")
        resolution = payload.get("resolution", "approve")
        reason = payload.get("reason", "")

        unit = self._repository.get_work_unit(work_id)

        # 先标记 blocker 为已解决
        if blocker_id:
            blocker = self._repository.get_blocker(blocker_id)
            if blocker is not None:
                updated = replace(blocker, resolved=True, resolution=resolution)
                self._repository.save_blocker(updated)

        # 根据 resolution 执行状态转换
        if resolution == "approve":
            # 批准后续操作：解除阻塞 → ready
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"阻塞已批准: {reason}"
                )
                return {
                    "success": True,
                    "message": "阻塞已批准，继续执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        elif resolution == "reject":
            # 拒绝：保持当前状态或标记为 failed
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = replace(unit, status=WorkUnitStatus.FAILED)
                self._repository.save_work_unit(new_unit)
                return {
                    "success": True,
                    "message": f"阻塞已拒绝: {reason}",
                    "work_id": work_id,
                    "new_status": WorkUnitStatus.FAILED.value,
                }

        elif resolution == "retry":
            # 重试：blocked → ready
            if unit.status in (WorkUnitStatus.BLOCKED, WorkUnitStatus.FAILED):
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"重试: {reason}"
                )
                return {
                    "success": True,
                    "message": "已标记为重新执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        elif resolution == "skip":
            # 跳过阻塞：强制接受
            new_unit = replace(unit, status=WorkUnitStatus.ACCEPTED)
            self._repository.save_work_unit(new_unit)
            return {
                "success": True,
                "message": f"已跳过阻塞: {reason}",
                "work_id": work_id,
                "new_status": WorkUnitStatus.ACCEPTED.value,
            }

        elif resolution == "abort":
            # 中止执行
            new_unit = replace(unit, status=WorkUnitStatus.FAILED)
            self._repository.save_work_unit(new_unit)
            return {
                "success": True,
                "message": f"已中止执行: {reason}",
                "work_id": work_id,
                "new_status": WorkUnitStatus.FAILED.value,
            }

        elif resolution == "resume":
            # 恢复执行
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"恢复执行: {reason}"
                )
                return {
                    "success": True,
                    "message": "已恢复执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        return {
            "success": True,
            "message": f"阻塞已处理: {resolution}",
            "work_id": work_id,
            "new_status": unit.status.value,
        }

    # ------------------------------------------------------------------
    # 执行控制命令
    # ------------------------------------------------------------------

    def _handle_prepare_work_unit(self, work_id: str, payload: dict) -> dict[str, Any]:
        """准备 WorkUnit 执行：确保上下文和 harness 就绪。

        如果 work_id 为空但 payload 中有完整 WorkUnit 数据，则创建新的 WorkUnit。
        如果 work_id 已有对应的 draft WorkUnit，则调用引擎预检，将其置为 ready。
        """
        # 情况1: 从 payload 创建新 WorkUnit
        if not work_id and payload.get("title"):
            return self._create_work_unit_from_payload(payload)

        # 情况2: 将已有 draft 置为 ready
        unit = self._repository.get_work_unit(work_id)
        if unit is None:
            return {
                "success": False,
                "message": f"WorkUnit {work_id} 不存在",
                "work_id": work_id,
                "new_status": None,
            }

        if unit.status == WorkUnitStatus.DRAFT:
            if self._engine is not None:
                try:
                    self._engine.prepare(work_id)
                    new_unit = self._repository.get_work_unit(work_id)
                    return {
                        "success": True,
                        "message": "WorkUnit 通过预检，已标记为 ready",
                        "work_id": work_id,
                        "new_status": new_unit.status.value,
                    }
                except ValueError as e:
                    return {
                        "success": False,
                        "message": f"WorkUnit 预检失败: {e}",
                        "work_id": work_id,
                        "new_status": unit.status.value,
                    }

            new_unit = self._repository.transition(
                work_id, WorkUnitStatus.READY, actor_role="scheduler", reason="WorkUnit 已准备就绪"
            )
            return {
                "success": True,
                "message": "WorkUnit 已标记为 ready",
                "work_id": work_id,
                "new_status": new_unit.status.value,
            }

        if unit.status == WorkUnitStatus.READY:
            return {
                "success": True,
                "message": "WorkUnit 已处于 ready 状态",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        return {
            "success": False,
            "message": f"WorkUnit 当前状态为 {unit.status.value}，无法准备",
            "work_id": work_id,
            "new_status": unit.status.value,
        }

    def _create_work_unit_from_payload(self, payload: dict) -> dict[str, Any]:
        """从 payload 创建新的 WorkUnit。"""
        from ralph.schema.work_unit import WorkUnit

        work_id = payload.get("work_id", f"W_{int(time.time())}")
        new_unit = WorkUnit(
            work_id=work_id,
            work_type=payload.get("work_type", "development"),
            title=payload.get("title", "Untitled"),
            background=payload.get("background", ""),
            target=payload.get("target", ""),
            scope_allow=payload.get("scope_allow", []),
            scope_deny=payload.get("scope_deny", []),
            dependencies=payload.get("dependencies", []),
            input_files=payload.get("input_files", []),
            expected_output=payload.get("expected_output", ""),
            acceptance_criteria=payload.get("acceptance_criteria", []),
            test_command=payload.get("test_command", ""),
            rollback_strategy=payload.get("rollback_strategy", ""),
            task_harness=payload.get("task_harness"),
            context_pack=payload.get("context_pack"),
            assumptions=payload.get("assumptions", []),
            impact_if_wrong=payload.get("impact_if_wrong", ""),
            risk_notes=payload.get("risk_notes", ""),
            status=WorkUnitStatus.DRAFT,
            producer_role=payload.get("producer_role", ""),
            reviewer_role=payload.get("reviewer_role", ""),
        )
        self._repository.save_work_unit(new_unit)

        return {
            "success": True,
            "message": f"WorkUnit {work_id} 已创建",
            "work_id": work_id,
            "new_status": WorkUnitStatus.DRAFT.value,
        }

    def _handle_execute_work_unit(self, work_id: str, payload: dict) -> dict[str, Any]:
        """执行 WorkUnit：ready → running → 实际执行。"""
        unit = self._repository.get_work_unit(work_id)

        if unit.status != WorkUnitStatus.READY:
            return {
                "success": False,
                "message": f"WorkUnit 当前状态为 {unit.status.value}，需要 ready 状态才能执行",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        if self._engine is None:
            # 无引擎时仅做状态转换（兼容旧模式）
            force = payload.get("force", False)
            reason = payload.get("reason", "开始执行" if not force else "强制执行")
            new_unit = self._repository.transition(
                work_id, WorkUnitStatus.RUNNING, actor_role="scheduler", reason=reason
            )
            logger.info("WorkUnit %s 已开始执行（无引擎）", work_id)
            return {
                "success": True,
                "message": "WorkUnit 已开始执行（未实际运行）",
                "work_id": work_id,
                "new_status": new_unit.status.value,
            }

        # 通过引擎执行：ready → running → needs_review
        try:
            result = asyncio.run(self._engine.execute(work_id))
            new_unit = self._repository.get_work_unit(work_id)
            logger.info("WorkUnit %s 执行完成: %s", work_id, result)
            return {
                "success": True,
                "message": "WorkUnit 执行完成",
                "work_id": work_id,
                "new_status": new_unit.status.value,
                "execution_result": result,
            }
        except Exception as e:
            logger.error("WorkUnit %s 执行失败: %s", work_id, e)
            return {
                "success": False,
                "message": f"WorkUnit 执行失败: {e}",
                "work_id": work_id,
                "new_status": WorkUnitStatus.FAILED.value,
            }

    def _handle_retry_work_unit(self, work_id: str, payload: dict) -> dict[str, Any]:
        """重试 WorkUnit：failed/needs_rework/blocked → ready。

        合并了旧的 execution_error_handle（retry 分支）逻辑。
        """
        unit = self._repository.get_work_unit(work_id)
        allowed_states = (WorkUnitStatus.FAILED, WorkUnitStatus.NEEDS_REWORK, WorkUnitStatus.BLOCKED)

        if unit.status not in allowed_states:
            return {
                "success": False,
                "message": f"WorkUnit 当前状态为 {unit.status.value}，无法重试（需为 failed/needs_rework/blocked）",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        reason = payload.get("reason", "重试任务")
        new_unit = self._repository.transition(
            work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"重试: {reason}"
        )

        # 同时解决关联的 blocker
        blocker_id = payload.get("blocker_id", "")
        if blocker_id:
            blocker = self._repository.get_blocker(blocker_id)
            if blocker is not None:
                updated = replace(blocker, resolved=True, resolution="retry")
                self._repository.save_blocker(updated)

        return {
            "success": True,
            "message": "WorkUnit 已标记为重新执行",
            "work_id": work_id,
            "new_status": new_unit.status.value,
        }

    def _handle_cancel_work_unit(self, work_id: str, payload: dict) -> dict[str, Any]:
        """取消 WorkUnit：任意非终态 → failed。"""
        unit = self._repository.get_work_unit(work_id)
        terminal_states = (WorkUnitStatus.ACCEPTED, WorkUnitStatus.FAILED)

        if unit.status in terminal_states:
            return {
                "success": False,
                "message": f"WorkUnit 已处于终态 {unit.status.value}，无法取消",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        reason = payload.get("reason", "任务已取消")
        new_unit = replace(unit, status=WorkUnitStatus.FAILED)
        self._repository.save_work_unit(new_unit)

        logger.info("WorkUnit %s 已取消: %s", work_id, reason)

        return {
            "success": True,
            "message": f"WorkUnit 已取消: {reason}",
            "work_id": work_id,
            "new_status": WorkUnitStatus.FAILED.value,
        }
