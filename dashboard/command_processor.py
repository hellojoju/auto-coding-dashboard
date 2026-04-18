"""CommandProcessor：命令状态机，消费命令 → 产出事实事件。"""

from __future__ import annotations

from typing import Any, Callable

from dashboard.models import Command, Event


class InvalidTransition(ValueError):
    """非法的命令状态转换。"""


VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "rejected", "cancelled"},
    "accepted": {"applied", "failed"},
}


class CommandProcessor:
    """命令状态机，每次状态转换时通过 on_event 回调产出事实事件。"""

    def __init__(
        self,
        on_event: Callable[[Event], None] | None = None,
    ) -> None:
        self._on_event = on_event

    def accept(self, cmd: Command) -> None:
        self._transition(cmd, "accepted")
        self._emit("command_accepted", command_id=cmd.command_id)

    def reject(self, cmd: Command, reason: str) -> None:
        self._transition(cmd, "rejected")
        cmd.result = {"reason": reason}
        self._emit("command_rejected", command_id=cmd.command_id, reason=reason)

    def apply(self, cmd: Command, result: dict[str, Any]) -> None:
        self._transition(cmd, "applied")
        cmd.result = result
        self._emit("command_applied", command_id=cmd.command_id)

    def fail(self, cmd: Command, reason: str) -> None:
        self._transition(cmd, "failed")
        cmd.result = {"reason": reason}
        self._emit("command_failed", command_id=cmd.command_id, reason=reason)

    def cancel(self, cmd: Command) -> None:
        self._transition(cmd, "cancelled")
        self._emit("command_cancelled", command_id=cmd.command_id)

    def _transition(self, cmd: Command, new_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(cmd.status, set())
        if new_status not in allowed:
            raise InvalidTransition(
                f"Invalid transition: {cmd.status} -> {new_status}"
            )
        cmd.status = new_status

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        if self._on_event:
            self._on_event(Event(type=event_type, payload=dict(kwargs)))
