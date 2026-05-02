"""StatusReporter 测试"""

from unittest.mock import MagicMock

import pytest

from dashboard.status_reporter import StatusReporter


@pytest.fixture
def mock_bus():
    return MagicMock()


def test_report_status_change(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_status("backend-1", "F001", "idle", "busy")
    mock_bus.emit.assert_called_once_with(
        "agent_status_changed",
        agent_id="backend-1",
        feature_id="F001",
        old_status="idle",
        new_status="busy",
        project_id="proj-1",
    )


def test_report_log_message(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_log("backend-1", "F001", "created endpoint")
    mock_bus.emit.assert_called_once_with(
        "agent_log",
        agent_id="backend-1",
        feature_id="F001",
        message="created endpoint",
        project_id="proj-1",
    )


def test_report_feature_completed(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_feature_completed("F001", ["src/api/users.py"], "done")
    mock_bus.emit.assert_called_once_with(
        "feature_completed",
        feature_id="F001",
        files_changed=["src/api/users.py"],
        summary="done",
        project_id="proj-1",
    )


def test_report_error(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_error("F001", "backend-1", "connection timeout")
    mock_bus.emit.assert_called_once_with(
        "error_occurred",
        feature_id="F001",
        agent_id="backend-1",
        error_message="connection timeout",
        project_id="proj-1",
    )


def test_report_pm_decision(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_pm_decision("start_F007", ["F007"], requires_approval=True)
    mock_bus.emit.assert_called_once_with(
        "pm_decision",
        decision="start_F007",
        next_actions=["F007"],
        requires_approval=True,
        project_id="proj-1",
    )
