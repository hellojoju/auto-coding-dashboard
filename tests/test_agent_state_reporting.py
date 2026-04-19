"""Agent 执行过程状态上报到 EventBus 的测试。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.backend_dev import BackendDeveloper
from dashboard.event_bus import EventBus


@pytest.fixture
def event_bus(tmp_path: Path) -> EventBus:
    return EventBus(log_file=tmp_path / "events.log")


@pytest.fixture
def agent(tmp_path: Path) -> BackendDeveloper:
    return BackendDeveloper(project_dir=tmp_path)


class TestAgentStateReporting:
    def test_agent_has_event_bus_slot(self, agent: BackendDeveloper) -> None:
        """Agent 实例应有 event_bus 属性（可由外部注入）。"""
        assert hasattr(agent, "event_bus")
        assert agent.event_bus is None

    def test_agent_reports_status_when_event_bus_injected(
        self, agent: BackendDeveloper, event_bus: EventBus
    ) -> None:
        """注入 event_bus 后，Agent 应能上报状态。"""
        agent.event_bus = event_bus
        agent._report_status("running", feature_id="F001", message="开始执行")

        events = event_bus.get_events()
        assert len(events) == 1
        evt = events[0]
        assert evt["type"] == "agent_status_changed"
        assert evt["agent_role"] == "backend"
        assert evt["feature_id"] == "F001"
        assert evt["status"] == "running"
        assert evt["message"] == "开始执行"

    def test_agent_does_not_report_when_no_event_bus(
        self, agent: BackendDeveloper
    ) -> None:
        """未注入 event_bus 时，_report_status 不应抛出异常。"""
        agent._report_status("running", feature_id="F001", message="test")
        # 无异常即通过

    def test_agent_reports_completed_and_failed_states(
        self, agent: BackendDeveloper, event_bus: EventBus
    ) -> None:
        """Agent 应能上报 completed 和 failed 状态。"""
        agent.event_bus = event_bus
        agent._report_status("completed", feature_id="F001", message="done")
        agent._report_status("failed", feature_id="F002", message="error")

        events = event_bus.get_events()
        assert len(events) == 2
        assert events[0]["status"] == "completed"
        assert events[1]["status"] == "failed"

    @patch.object(BackendDeveloper, "_run_with_claude")
    def test_execute_reports_start_and_end_status(
        self, mock_claude: MagicMock, agent: BackendDeveloper, event_bus: EventBus
    ) -> None:
        """execute() 应在开始和结束时上报状态。"""
        import asyncio
        mock_claude.return_value = {"success": True, "stdout": "", "stderr": ""}
        agent.event_bus = event_bus

        result = asyncio.run(
            agent.execute({"feature_id": "F001", "description": "test feature"})
        )

        assert result["success"] is True
        events = event_bus.get_events()
        statuses = [e.get("status") for e in events if e["type"] == "agent_status_changed"]
        assert "running" in statuses
        assert "completed" in statuses

    @patch.object(BackendDeveloper, "_run_with_claude")
    def test_execute_reports_failure(
        self, mock_claude: MagicMock, agent: BackendDeveloper, event_bus: EventBus
    ) -> None:
        """execute() 失败时应上报 failed 状态。"""
        import asyncio
        mock_claude.return_value = {"success": False, "error": "boom"}
        agent.event_bus = event_bus

        result = asyncio.run(
            agent.execute({"feature_id": "F002", "description": "fail feature"})
        )

        assert result["success"] is False
        events = event_bus.get_events()
        statuses = [e.get("status") for e in events if e["type"] == "agent_status_changed"]
        assert "failed" in statuses
