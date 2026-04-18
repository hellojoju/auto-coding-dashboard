"""StatusReporter - Agent 执行过程中上报状态到 EventBus。"""

from typing import Any


class StatusReporter:
    """封装 EventBus 调用，提供语义化的状态上报接口。"""

    def __init__(self, event_bus: Any, project_id: str):
        self._bus = event_bus
        self._project_id = project_id

    def report_status(self, agent_id: str, feature_id: str, old_status: str, new_status: str) -> None:
        """Agent 状态变化时调用。"""
        self._bus.emit(
            "agent_status_changed",
            agent_id=agent_id,
            feature_id=feature_id,
            old_status=old_status,
            new_status=new_status,
            project_id=self._project_id,
        )

    def report_log(self, agent_id: str, feature_id: str, message: str) -> None:
        """Agent 输出日志时调用。"""
        self._bus.emit(
            "agent_log",
            agent_id=agent_id,
            feature_id=feature_id,
            message=message,
            project_id=self._project_id,
        )

    def report_feature_completed(self, feature_id: str, files_changed: list[str], summary: str) -> None:
        """Feature 完成时调用。"""
        self._bus.emit(
            "feature_completed",
            feature_id=feature_id,
            files_changed=files_changed,
            summary=summary,
            project_id=self._project_id,
        )

    def report_error(self, feature_id: str, agent_id: str, error_message: str) -> None:
        """发生错误时调用。"""
        self._bus.emit(
            "error_occurred",
            feature_id=feature_id,
            agent_id=agent_id,
            error_message=error_message,
            project_id=self._project_id,
        )

    def report_pm_decision(self, decision: str, next_actions: list[str], requires_approval: bool = False) -> None:
        """PM 做出决策时调用。"""
        self._bus.emit(
            "pm_decision",
            decision=decision,
            next_actions=next_actions,
            requires_approval=requires_approval,
            project_id=self._project_id,
        )
