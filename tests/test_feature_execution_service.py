"""测试 FeatureExecutionService"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.feature_execution_service import FeatureExecutionService


def _make_feature(
    feature_id: str = "feat-1",
    description: str = "Test feature",
    category: str = "backend",
    priority: str = "P1",
    test_steps: list | None = None,
    dependencies: list | None = None,
):
    """Factory: 创建用于测试的 Feature mock 对象。"""
    feature = MagicMock()
    feature.id = feature_id
    feature.description = description
    feature.category = category
    feature.priority = priority
    feature.test_steps = test_steps or []
    feature.dependencies = dependencies or []
    return feature


@pytest.fixture
def service(tmp_path):
    mock_pm = MagicMock()
    mock_pm.project_dir = tmp_path
    mock_pool = MagicMock()
    mock_tracker = MagicMock()
    return FeatureExecutionService(mock_pm, mock_pool, mock_tracker)


@pytest.mark.unit
async def test_execute_feature_success(service):
    """测试 Agent 成功执行 Feature"""
    feature = _make_feature()

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {
        "success": True,
        "files_changed": ["src/a.py"],
    }

    result = await service.execute(feature, mock_agent)
    assert result["success"] is True
    assert result["files_changed"] == ["src/a.py"]


@pytest.mark.unit
async def test_execute_feature_failure(service):
    """测试 Agent 执行失败"""
    feature = _make_feature()

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.side_effect = Exception("Connection error")

    result = await service.execute(feature, mock_agent)
    assert result["success"] is False
    assert "Connection error" in result["error"]


@pytest.mark.unit
async def test_execute_feature_with_test_steps(service):
    """测试带测试步骤的 Feature"""
    feature = _make_feature(
        feature_id="feat-2",
        description="Feature with tests",
        priority="P0",
        test_steps=["step1", "step2"],
    )

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {
        "success": True,
        "files_changed": ["src/b.py", "tests/test_b.py"],
    }

    result = await service.execute(feature, mock_agent)
    assert result["success"] is True
    assert len(result["files_changed"]) == 2

    # 验证传递了正确的 test_steps
    call_args = mock_agent.execute.call_args[0][0]
    assert call_args["test_steps"] == ["step1", "step2"]


@pytest.mark.unit
async def test_execute_feature_empty_result(service):
    """测试 Agent 返回空结果时的默认值处理"""
    feature = _make_feature(
        feature_id="feat-3",
        description="Empty result feature",
        category="frontend",
        priority="P2",
    )

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {}

    result = await service.execute(feature, mock_agent)
    assert result["success"] is False
    assert result["files_changed"] == []
    assert result["error"] == ""


@pytest.mark.unit
async def test_execute_feature_passes_context(service, tmp_path):
    """验证执行上下文正确传递给 Agent"""
    feature = _make_feature(
        feature_id="feat-4",
        description="Context test",
        category="database",
        test_steps=["verify schema"],
    )

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {"success": True, "files_changed": []}

    await service.execute(
        feature,
        mock_agent,
        prd_summary="Test PRD",
        dependencies_context={"deps": []},
    )

    call_args = mock_agent.execute.call_args[0][0]
    assert call_args["feature_id"] == "feat-4"
    assert call_args["description"] == "Context test"
    assert call_args["category"] == "database"
    assert call_args["priority"] == "P1"
    assert call_args["project_dir"] == str(tmp_path)
    assert call_args["prd_summary"] == "Test PRD"
    assert call_args["dependencies_context"] == {"deps": []}


@pytest.mark.unit
async def test_execute_feature_default_context_is_empty(service):
    """验证未传入 prd_summary/dependencies_context 时使用空默认值"""
    feature = _make_feature()

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {"success": True, "files_changed": []}

    await service.execute(feature, mock_agent)

    call_args = mock_agent.execute.call_args[0][0]
    assert call_args["prd_summary"] == ""
    assert call_args["dependencies_context"] == {}


@pytest.mark.unit
async def test_execute_feature_without_test_steps_attr(service):
    """验证 Feature 没有 test_steps 属性时使用空列表 fallback"""
    feature = MagicMock(spec=["id", "description", "category", "priority"])
    feature.id = "feat-5"
    feature.description = "No test steps"
    feature.category = "backend"
    feature.priority = "P2"
    # 刻意不设置 test_steps 属性

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = {"success": True, "files_changed": []}

    await service.execute(feature, mock_agent)

    call_args = mock_agent.execute.call_args[0][0]
    assert call_args["test_steps"] == []


@pytest.mark.unit
async def test_execute_feature_agent_returns_none(service):
    """验证 Agent 返回 None 时返回结构化错误"""
    feature = _make_feature()

    mock_agent = MagicMock()
    mock_agent.workspace_path = "/workspace"
    mock_agent.execute = AsyncMock()
    mock_agent.execute.return_value = None

    result = await service.execute(feature, mock_agent)
    assert result["success"] is False
    assert result["error"] == "Agent returned non-dict result"
