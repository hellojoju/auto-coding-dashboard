"""Shared test fixtures"""

from unittest.mock import MagicMock, patch

import pytest

from core.feature_tracker import Feature, FeatureTracker
from core.progress_logger import ProgressLogger
from core.task_queue import TaskQueue


@pytest.fixture
def tmp_data_dir(tmp_path):
    """创建临时数据目录"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def feature_tracker(tmp_data_dir):
    """FeatureTracker with patched file paths"""
    features_file = tmp_data_dir / "features.json"
    with patch("core.feature_tracker.FEATURES_FILE", features_file):
        tracker = FeatureTracker()
        yield tracker


@pytest.fixture
def progress_logger(tmp_data_dir):
    """ProgressLogger with patched file path"""
    log_file = tmp_data_dir / "progress.txt"
    with patch("core.progress_logger.PROGRESS_FILE", log_file):
        logger = ProgressLogger()
        yield logger


@pytest.fixture
def task_queue(tmp_data_dir):
    """TaskQueue with patched db path"""
    db_path = tmp_data_dir / "tasks.db"
    with patch("core.task_queue.TASK_DB", db_path):
        queue = TaskQueue()
        yield queue


@pytest.fixture
def sample_feature():
    """Sample feature for testing"""
    return Feature(
        id="F001",
        category="auth",
        description="用户注册功能",
        priority="P0",
        assigned_to="backend",
        dependencies=[],
        test_steps=["访问注册页面", "填写表单", "提交成功"],
    )


@pytest.fixture
def sample_features():
    """Sample feature list"""
    return [
        Feature(
            id="F001", category="auth", description="用户注册",
            priority="P0", assigned_to="backend", test_steps=["step1"],
        ),
        Feature(
            id="F002", category="auth", description="用户登录",
            priority="P1", assigned_to="backend",
            dependencies=["F001"], test_steps=["step1"],
        ),
        Feature(
            id="F003", category="ui", description="登录页面",
            priority="P1", assigned_to="frontend", test_steps=["step1"],
        ),
    ]


@pytest.fixture
def mock_project_dir(tmp_path):
    """创建模拟项目目录"""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "src").mkdir()
    (project_dir / "src" / "api").mkdir()
    (project_dir / "tests").mkdir()
    return project_dir


@pytest.fixture
def mock_claude_run():
    """Mock subprocess.run for claude CLI calls"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = b'{"success": true}'
    mock_result.stderr = b""

    with patch("subprocess.run", return_value=mock_result) as mock:
        yield mock
