"""CommandConsumer：轮询 Repository 中的待处理命令并通过 CommandProcessor 消费。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dashboard.command_processor import CommandProcessor
from dashboard.event_bus import EventBus
from dashboard.models import Command
from dashboard.state_repository import ProjectStateRepository
from ralph.command_handler import RalphCommandHandler

logger = logging.getLogger(__name__)

# Ralph 命令类型集合
RALPH_COMMAND_TYPES = {
    "accept_review",
    "request_rework",
    "override_accept",
    "expand_scope",
    "scope_expansion_confirm",
    "dangerous_op_confirm",
    "review_dispute_resolve",
    "missing_dep_resolve",
    "execution_error_handle",
    "manual_intervention",
}


class CommandConsumer:
    """从 Repository 拉取 pending 命令，交给 CommandProcessor 处理，写回状态并发送事件。"""

    def __init__(
        self,
        repository: ProjectStateRepository,
        processor: CommandProcessor,
        event_bus: EventBus,
        ralph_handler: RalphCommandHandler | None = None,
    ) -> None:
        self._repo = repository
        self._processor = processor
        self._event_bus = event_bus
        self._ralph_handler = ralph_handler

    def process_once(self) -> int:
        """消费一轮所有 pending 命令，返回实际处理的命令数。"""
        pending = self._repo.list_pending_commands()
        if not pending:
            return 0

        processed = 0
        for cmd in pending:
            try:
                self._process_command(cmd)
            except Exception:
                # 标记为失败，不中断后续命令
                cmd.status = "failed"
                self._repo.save_command(cmd)
                self._emit_event("command_failed", command_id=cmd.command_id, error="unexpected error")
            processed += 1
        return processed

    def _process_command(self, cmd: Command) -> None:
        """处理单条命令。"""
        # 命令别名映射：前端发送类型 → 后端标准类型
        command_aliases = {
            "approve_decision": "approve",
            "reject_decision": "reject",
            "pause_run": "pause",
            "resume_run": "resume",
            "retry_feature": "retry",
            "skip_feature": "skip",
        }
        cmd_type = command_aliases.get(cmd.type, cmd.type)

        # 检查是否为 Ralph 命令
        if cmd_type in RALPH_COMMAND_TYPES:
            self._process_ralph_command(cmd, cmd_type)
            return

        if cmd_type == "approve":
            self._processor.accept(cmd)
            self._processor.apply(cmd, {})
            self._repo.save_command(cmd)
            self._emit_event("command_applied", command_id=cmd.command_id)
        elif cmd_type == "reject":
            self._processor.reject(cmd, reason="rejected by PM")
            self._repo.save_command(cmd)
            self._emit_event("command_rejected", command_id=cmd.command_id)
        elif cmd_type in ("pause", "resume", "retry", "skip"):
            cmd.status = "applied"
            self._repo.save_command(cmd)
            self._emit_event("command_applied", command_id=cmd.command_id)
        else:
            cmd.status = "failed"
            self._repo.save_command(cmd)
            self._emit_event("command_failed", command_id=cmd.command_id, error=f"unknown type: {cmd.type}")

    def _process_ralph_command(self, cmd: Command, cmd_type: str) -> None:
        """处理 Ralph WorkUnit 相关命令。"""
        # 如果没有提供 ralph_handler，尝试创建一个
        if self._ralph_handler is None:
            # 从项目目录推断 ralph 目录
            project_dir = getattr(self._repo, "_base", None)
            if project_dir:
                ralph_dir = Path(project_dir) / ".ralph"
                self._ralph_handler = RalphCommandHandler(ralph_dir)
            else:
                logger.error("无法确定 Ralph 目录，无法处理 Ralph 命令: %s", cmd_type)
                cmd.status = "failed"
                self._repo.save_command(cmd)
                self._emit_event("command_failed", command_id=cmd.command_id, error="ralph handler not available")
                return

        try:
            result = self._ralph_handler.handle(cmd)

            if result.get("success"):
                cmd.status = "applied"
                cmd.result = result
                self._repo.save_command(cmd)
                self._emit_event(
                    "command_applied",
                    command_id=cmd.command_id,
                    work_id=result.get("work_id"),
                    new_status=result.get("new_status"),
                )
            else:
                cmd.status = "failed"
                cmd.result = result
                self._repo.save_command(cmd)
                self._emit_event(
                    "command_failed",
                    command_id=cmd.command_id,
                    error=result.get("message", "unknown error"),
                )
        except Exception as e:
            logger.exception("处理 Ralph 命令失败: %s", cmd_type)
            cmd.status = "failed"
            cmd.result = {"success": False, "message": str(e)}
            self._repo.save_command(cmd)
            self._emit_event("command_failed", command_id=cmd.command_id, error=str(e))

    def _emit_event(self, event_type: str, **kwargs) -> None:
        self._event_bus.emit(event_type, **kwargs)
