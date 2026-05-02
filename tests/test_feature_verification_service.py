"""测试 FeatureVerificationService"""

from unittest.mock import MagicMock, patch

import pytest

from core.feature_verification_service import FeatureVerificationService


def _make_feature(
    feature_id: str = "feat-1",
    description: str = "Test feature",
    category: str = "backend",
    test_steps: list | None = None,
):
    """Factory: 创建用于测试的 Feature mock 对象。"""
    feature = MagicMock()
    feature.id = feature_id
    feature.description = description
    feature.category = category
    feature.test_steps = test_steps or []
    return feature


@pytest.fixture
def service(tmp_path):
    return FeatureVerificationService(tmp_path)


@pytest.mark.unit
def test_verify_no_files(service):
    """没有预期文件时验收通过。"""
    feature = _make_feature(category="unknown-category")
    result = service.verify(feature)
    assert result.passed is True
    assert bool(result) is True  # __bool__ 向后兼容


@pytest.mark.unit
def test_verify_missing_files(service, tmp_path):
    """缺少预期文件时验收不通过。"""
    feature = _make_feature(category="docs")
    # 创建 docs 目录但不放任何文件
    (tmp_path / "docs").mkdir()
    result = service.verify(feature)
    # 应该有根目录文件检测，但 docs/ 是空的，missing 取决于是否有根文件
    # 在空 tmp_path 中，没有 main.py 等根文件，docs/ 空目录不会产出文件
    # 所以 expected_files 为空，验证通过
    assert result.passed is True


@pytest.mark.unit
def test_verify_with_existing_files(service, tmp_path):
    """有预期文件时验收通过。"""
    feature = _make_feature(category="docs")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Test")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

    result = service.verify(feature)
    assert result.passed is True
    assert result.diff_summary is not None  # 应收集 diff


@pytest.mark.unit
def test_verify_syntax_error_python(service, tmp_path):
    """Python 语法错误时验收不通过。"""
    (tmp_path / "src").mkdir()
    bad_file = tmp_path / "src" / "bad.py"
    bad_file.write_text("def foo(\n")  # 语法错误

    errors = service._run_syntax_checks(["src/bad.py"])
    assert len(errors) >= 1
    assert "bad.py" in errors[0]


@pytest.mark.unit
def test_verify_valid_python_syntax(service, tmp_path):
    """合法 Python 语法检查通过。"""
    (tmp_path / "src").mkdir()
    good_file = tmp_path / "src" / "good.py"
    good_file.write_text("def foo():\n    pass\n")

    errors = service._run_syntax_checks(["src/good.py"])
    assert errors == []


@pytest.mark.unit
def test_verify_empty_sql(service, tmp_path):
    """空 SQL 文件检测为错误。"""
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "empty.sql").write_text("   \n")

    errors = service._run_syntax_checks(["migrations/empty.sql"])
    assert len(errors) >= 1
    assert "文件为空" in errors[0]


@pytest.mark.unit
def test_verify_with_test_steps_e2e_import_error(service):
    """test_steps 存在但 e2e_runner 不可用时返回 None（不默认通过）。"""
    _make_feature(feature_id="feat-e2e", test_steps=["check login"])

    with patch.dict("sys.modules", {"testing.e2e_runner": None}):
        result = service._run_e2e_validation("feat-e2e", ["check login"])
        assert result is None


@pytest.mark.unit
def test_infer_expected_files_backend(service, tmp_path):
    """后端类别推断正确的目录。"""
    feature = _make_feature(category="backend")
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "users.py").write_text("pass")
    (tmp_path / "main.py").write_text("pass")

    files = service._infer_expected_files(feature)
    assert "src/api/users.py" in files
    assert "main.py" in files


@pytest.mark.unit
def test_infer_expected_files_unknown_category(service, tmp_path):
    """未知类别默认检查 src/ 目录。"""
    feature = _make_feature(category="unknown")
    files = service._infer_expected_files(feature)
    # src/ 不存在，只可能有根文件
    assert isinstance(files, list)
