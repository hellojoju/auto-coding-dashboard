"""CommandConsumer：轮询 Repository 中的待处理命令并通过 CommandProcessor 消费。"""

from __future__ import annotations

import logging

from dashboard.command_processor import CommandProcessor
from dashboard.event_bus import EventBus
from dashboard.models import Command
from dashboard.state_repository import ProjectStateRepository

logger = logging.getLogger(__name__)


class CommandConsumer:
    """从 Repository 拉取 pending 命令，交给 CommandProcessor 处理，写回状态并发送事件。"""

    def __init__(
        self,
        repository: ProjectStateRepository,
        processor: CommandProcessor,
        event_bus: EventBus,
    ) -> None:
        self._repo = repository
        self._processor = processor
        self._event_bus = event_bus

    def process_once(self) -> int:
        """消费一轮所有 pending 命令，返回实际处理的命令数。"""
        pending = list(c for c in self._repo._commands.values() if c.status == "pending")
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
            "pause_run": "pause",
            "resume_run": "resume",
            "retry_feature": "retry",
            "skip_feature": "skip",
        }
        cmd_type = command_aliases.get(cmd.type, cmd.type)

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

    def _emit_event(self, event_type: str, **kwargs) -> None:
        self._event_bus.emit(event_type, **kwargs)
