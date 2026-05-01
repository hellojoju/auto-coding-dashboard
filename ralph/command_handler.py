"""Ralph Command Handler — 处理 WorkUnit 相关的命令。

将审批中心的用户操作转换为 WorkUnit 状态转换。
支持命令：accept_review, request_rework, override_accept, expand_scope 等。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dashboard.models import Command
from ralph.repository import RalphRepository
from ralph.schema.work_unit import WorkUnitStatus

logger = logging.getLogger(__name__)


class RalphCommandHandler:
    """处理 Ralph WorkUnit 相关命令。"""

    def __init__(self, ralph_dir: Path) -> None:
        self._ralph_dir = Path(ralph_dir)
        self._repository = RalphRepository(self._ralph_dir)

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

        # 检查 WorkUnit 是否存在
        unit = self._repository.get_work_unit(work_id)
        if unit is None:
            return {
                "success": False,
                "message": f"WorkUnit {work_id} 不存在",
                "work_id": work_id,
                "new_status": None,
            }

        try:
            if cmd_type == "accept_review":
                return self._handle_accept_review(work_id, payload)
            elif cmd_type == "request_rework":
                return self._handle_request_rework(work_id, payload)
            elif cmd_type == "override_accept":
                return self._handle_override_accept(work_id, payload)
            elif cmd_type == "expand_scope":
                return self._handle_expand_scope(work_id, payload)
            elif cmd_type == "scope_expansion_confirm":
                return self._handle_scope_expansion_confirm(work_id, payload)
            elif cmd_type == "dangerous_op_confirm":
                return self._handle_dangerous_op_confirm(work_id, payload)
            elif cmd_type == "review_dispute_resolve":
                return self._handle_review_dispute_resolve(work_id, payload)
            elif cmd_type == "missing_dep_resolve":
                return self._handle_missing_dep_resolve(work_id, payload)
            elif cmd_type == "execution_error_handle":
                return self._handle_execution_error_handle(work_id, payload)
            elif cmd_type == "manual_intervention":
                return self._handle_manual_intervention(work_id, payload)
            else:
                return {
                    "success": False,
                    "message": f"未知的 Ralph 命令类型: {cmd_type}",
                    "work_id": work_id,
                    "new_status": None,
                }
        except Exception as e:
            logger.error("处理 Ralph 命令失败: %s", e)
            return {
                "success": False,
                "message": str(e),
                "work_id": work_id,
                "new_status": None,
            }

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

        # 对于 override，我们直接保存新状态，不经过正常转换检查
        unit = self._repository.get_work_unit(work_id)
        from dataclasses import replace

        new_unit = replace(unit, status=WorkUnitStatus.ACCEPTED)
        self._repository.save_work_unit(new_unit)

        logger.info("PM 强制接受 WorkUnit %s: %s", work_id, reason)

        return {
            "success": True,
            "message": f"已强制接受: {reason}",
            "work_id": work_id,
            "new_status": WorkUnitStatus.ACCEPTED.value,
        }

    def _handle_expand_scope(self, work_id: str, payload: dict) -> dict[str, Any]:
        """扩展范围请求：记录扩展请求，等待确认。"""
        scope_additions = payload.get("scope_additions", [])
        reason = payload.get("reason", "")

        logger.info("WorkUnit %s 范围扩展请求: %s, 原因: %s", work_id, scope_additions, reason)

        # 创建 blocker 记录扩展请求
        from ralph.schema.blocker import Blocker

        blocker = Blocker(
            blocker_id=f"scope_expand_{work_id}_{int(__import__('time').time())}",
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

    def _handle_scope_expansion_confirm(self, work_id: str, payload: dict) -> dict[str, Any]:
        """确认范围扩展：解除 blocker 并继续。"""
        blocker_id = payload.get("blocker_id", "")
        approved = payload.get("approved", True)

        if blocker_id:
            blocker = self._repository.get_blocker(blocker_id)
            if blocker:
                blocker.resolved = True
                blocker.resolution = "approved" if approved else "rejected"
                self._repository.save_blocker(blocker)

        if approved:
            # 将 WorkUnit 状态重置为 ready 以继续执行
            unit = self._repository.get_work_unit(work_id)
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason="范围扩展已批准"
                )
                return {
                    "success": True,
                    "message": "范围扩展已批准，WorkUnit 继续执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        return {
            "success": True,
            "message": "范围扩展已拒绝" if not approved else "范围扩展已处理",
            "work_id": work_id,
            "new_status": self._repository.get_work_unit(work_id).status.value,
        }

    def _handle_dangerous_op_confirm(self, work_id: str, payload: dict) -> dict[str, Any]:
        """确认危险操作：解除 blocker 并继续执行。"""
        blocker_id = payload.get("blocker_id", "")
        confirmed = payload.get("confirmed", True)

        if blocker_id:
            blocker = self._repository.get_blocker(blocker_id)
            if blocker:
                # Blocker 是不可变的，创建新的实例
                from dataclasses import replace
                updated_blocker = replace(
                    blocker,
                    resolved=True,
                    resolution="confirmed" if confirmed else "cancelled"
                )
                self._repository.save_blocker(updated_blocker)

        if confirmed:
            # 解除阻塞，恢复到 ready 状态
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

    def _handle_review_dispute_resolve(self, work_id: str, payload: dict) -> dict[str, Any]:
        """解决审查争议。"""
        resolution = payload.get("resolution", "accept")  # accept|reject|rework
        reason = payload.get("reason", "")

        unit = self._repository.get_work_unit(work_id)

        if resolution == "accept":
            if unit.status == WorkUnitStatus.NEEDS_REVIEW:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.ACCEPTED, actor_role="scheduler", reason=f"争议解决: {reason}"
                )
                return {
                    "success": True,
                    "message": "争议已解决，接受 WorkUnit",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }
        elif resolution == "rework":
            if unit.status == WorkUnitStatus.NEEDS_REVIEW:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.NEEDS_REWORK, actor_role="scheduler", reason=f"争议解决: 需返工 - {reason}"
                )
                return {
                    "success": True,
                    "message": "争议已解决，请求返工",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        return {
            "success": True,
            "message": f"争议处理: {resolution}",
            "work_id": work_id,
            "new_status": unit.status.value,
        }

    def _handle_missing_dep_resolve(self, work_id: str, payload: dict) -> dict[str, Any]:
        """解决缺失依赖。"""
        dep_id = payload.get("dependency_id", "")
        resolution = payload.get("resolution", "provide")  # provide|skip|wait

        # 标记 blocker 为已解决
        blocker_id = payload.get("blocker_id", "")
        if blocker_id:
            blocker = self._repository.get_blocker(blocker_id)
            if blocker:
                blocker.resolved = True
                blocker.resolution = resolution
                self._repository.save_blocker(blocker)

        if resolution == "provide":
            # 解除阻塞，继续执行
            unit = self._repository.get_work_unit(work_id)
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"依赖 {dep_id} 已提供"
                )
                return {
                    "success": True,
                    "message": f"依赖 {dep_id} 已提供，继续执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }
        elif resolution == "skip":
            # 跳过依赖，继续执行
            unit = self._repository.get_work_unit(work_id)
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"跳过依赖 {dep_id}"
                )
                return {
                    "success": True,
                    "message": f"已跳过依赖 {dep_id}",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }

        return {
            "success": True,
            "message": f"依赖处理: {resolution}",
            "work_id": work_id,
            "new_status": self._repository.get_work_unit(work_id).status.value,
        }

    def _handle_execution_error_handle(self, work_id: str, payload: dict) -> dict[str, Any]:
        """处理执行错误。"""
        action = payload.get("action", "retry")  # retry|skip|abort
        reason = payload.get("reason", "")

        unit = self._repository.get_work_unit(work_id)

        if action == "retry":
            if unit.status in (WorkUnitStatus.FAILED, WorkUnitStatus.BLOCKED):
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"错误处理: 重试 - {reason}"
                )
                return {
                    "success": True,
                    "message": "已标记为重新执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }
        elif action == "skip":
            # 强制接受，跳过错误
            from dataclasses import replace

            new_unit = replace(unit, status=WorkUnitStatus.ACCEPTED)
            self._repository.save_work_unit(new_unit)
            return {
                "success": True,
                "message": "已跳过错误，强制接受",
                "work_id": work_id,
                "new_status": WorkUnitStatus.ACCEPTED.value,
            }
        elif action == "abort":
            # 保持失败状态
            return {
                "success": True,
                "message": "已中止执行",
                "work_id": work_id,
                "new_status": unit.status.value,
            }

        return {
            "success": True,
            "message": f"错误处理: {action}",
            "work_id": work_id,
            "new_status": unit.status.value,
        }

    def _handle_manual_intervention(self, work_id: str, payload: dict) -> dict[str, Any]:
        """处理人工干预。"""
        action = payload.get("action", "resume")  # resume|abort|block
        reason = payload.get("reason", "")

        unit = self._repository.get_work_unit(work_id)

        if action == "resume":
            if unit.status == WorkUnitStatus.BLOCKED:
                new_unit = self._repository.transition(
                    work_id, WorkUnitStatus.READY, actor_role="scheduler", reason=f"人工干预: 继续 - {reason}"
                )
                return {
                    "success": True,
                    "message": "已恢复执行",
                    "work_id": work_id,
                    "new_status": new_unit.status.value,
                }
        elif action == "abort":
            from dataclasses import replace

            new_unit = replace(unit, status=WorkUnitStatus.FAILED)
            self._repository.save_work_unit(new_unit)
            return {
                "success": True,
                "message": "已中止执行",
                "work_id": work_id,
                "new_status": WorkUnitStatus.FAILED.value,
            }

        return {
            "success": True,
            "message": f"人工干预: {action}",
            "work_id": work_id,
            "new_status": unit.status.value,
        }
