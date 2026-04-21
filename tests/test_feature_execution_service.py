"""测试 FeatureExecutionService"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.feature_execution_service import FeatureExecutionService


@pytest.fixture
def service(tmp_path):
    mock_pm = MagicMock()
    mock_pm.project_dir = tmp_path
    mock_pm._get_prd_summary.return_value = "Test PRD"
    mock_pm._get_deps_context.return_value = {"deps": []}
    mock_pool = MagicMock()
    mock_tracker = MagicMock()
    return FeatureExecutionService(mock_pm, mock_pool, mock_tracker)


def test_execute_feature_success(service):
    """测试 Agent 成功执行 Feature"""
    feature = MagicMock()
    feature.id = "feat-1"
    feature.description = "Test feature"
    feature.category = "backend"
    feature.priority = "P1"
    feature.test_steps = []
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {
        "success": True,
        "files_changed": ["src/a.py"],
    }

    result = service.execute(feature, mock_agent)
    assert result["success"] is True
    assert result["files_changed"] == ["src/a.py"]


def test_execute_feature_failure(service):
    """测试 Agent 执行失败"""
    feature = MagicMock()
    feature.id = "feat-1"
    feature.description = "Test feature"
    feature.category = "backend"
    feature.priority = "P1"
    feature.test_steps = []
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock()
    mock_agent.execute.side_effect = Exception("Connection error")

    result = service.execute(feature, mock_agent)
    assert result["success"] is False
    assert "Connection error" in result["error"]


def test_execute_feature_with_test_steps(service):
    """测试带测试步骤的 Feature"""
    feature = MagicMock()
    feature.id = "feat-2"
    feature.description = "Feature with tests"
    feature.category = "backend"
    feature.priority = "P0"
    feature.test_steps = ["step1", "step2"]
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {
        "success": True,
        "files_changed": ["src/b.py", "tests/test_b.py"],
    }

    result = service.execute(feature, mock_agent)
    assert result["success"] is True
    assert len(result["files_changed"]) == 2

    # 验证传递了正确的 test_steps
    call_args = mock_agent.execute.call_args[0][0]
    assert call_args["test_steps"] == ["step1", "step2"]


def test_execute_feature_empty_result(service):
    """测试 Agent 返回空结果时的默认值处理"""
    feature = MagicMock()
    feature.id = "feat-3"
    feature.description = "Empty result feature"
    feature.category = "frontend"
    feature.priority = "P2"
    feature.test_steps = []
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {}

    result = service.execute(feature, mock_agent)
    assert result["success"] is False
    assert result["files_changed"] == []
    assert result["error"] == ""


def test_execute_feature_passes_context(service, tmp_path):
    """验证执行上下文正确传递给 Agent"""
    feature = MagicMock()
    feature.id = "feat-4"
    feature.description = "Context test"
    feature.category = "database"
    feature.priority = "P1"
    feature.test_steps = ["verify schema"]
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {"success": True, "files_changed": []}

    service.execute(feature, mock_agent)

    call_args = mock_agent.execute.call_args[0][0]
    assert call_args["feature_id"] == "feat-4"
    assert call_args["description"] == "Context test"
    assert call_args["category"] == "database"
    assert call_args["priority"] == "P1"
    assert call_args["project_dir"] == str(tmp_path)
    assert call_args["prd_summary"] == "Test PRD"
    assert call_args["dependencies_context"] == {"deps": []}
