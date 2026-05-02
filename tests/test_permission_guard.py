"""Permission Guard 单元测试

覆盖：SafetyLevel、check_prompt、check_diff、backup_file、PERMISSION_RULES_PROMPT
"""

import subprocess
from pathlib import Path

import pytest

from core.permission_guard import (
    BULK_DELETE_THRESHOLD,
    PERMISSION_RULES_PROMPT,
    PermissionCheckResult,
    PermissionGuard,
    PermissionViolation,
    SafetyLevel,
)


@pytest.fixture
def guard(tmp_path: Path) -> PermissionGuard:
    return PermissionGuard(tmp_path)


# ── SafetyLevel ──────────────────────────────────────────────


class TestSafetyLevel:
    def test_three_levels(self) -> None:
        assert SafetyLevel.ALLOWED.value == "allowed"
        assert SafetyLevel.PROTECTED.value == "protected"
        assert SafetyLevel.BLOCKED.value == "blocked"


# ── PermissionViolation ──────────────────────────────────────


class TestPermissionViolation:
    def test_frozen(self) -> None:
        v = PermissionViolation(
            level=SafetyLevel.BLOCKED,
            operation="test_op",
            detail="test detail",
        )
        with pytest.raises(AttributeError):
            v.level = SafetyLevel.ALLOWED  # type: ignore[misc]

    def test_default_files_empty(self) -> None:
        v = PermissionViolation(
            level=SafetyLevel.ALLOWED,
            operation="test",
            detail="detail",
        )
        assert v.files == []


# ── PermissionCheckResult ────────────────────────────────────


class TestPermissionCheckResult:
    def test_allowed_no_violations(self) -> None:
        r = PermissionCheckResult(allowed=True)
        assert r.blocked_violations == []
        assert r.protected_violations == []

    def test_blocked_violations_filter(self) -> None:
        v_blocked = PermissionViolation(
            level=SafetyLevel.BLOCKED, operation="op", detail="d"
        )
        v_protected = PermissionViolation(
            level=SafetyLevel.PROTECTED, operation="op", detail="d"
        )
        r = PermissionCheckResult(
            allowed=False, violations=[v_blocked, v_protected]
        )
        assert len(r.blocked_violations) == 1
        assert len(r.protected_violations) == 1


# ── check_prompt ─────────────────────────────────────────────


class TestCheckPrompt:
    def test_safe_prompt_allowed(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("请在 src/app.py 中添加一个新函数")
        assert result.allowed is True
        assert result.violations == []

    def test_rm_rf_blocked(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("运行 rm -rf /tmp/test")
        assert result.allowed is False
        assert len(result.blocked_violations) == 1
        assert "rm" in result.blocked_violations[0].detail

    def test_drop_table_blocked(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("执行 DROP TABLE users")
        assert result.allowed is False

    def test_git_push_force_blocked(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("git push origin main --force")
        assert result.allowed is False

    def test_npm_publish_blocked(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("运行 npm publish 发布包")
        assert result.allowed is False

    def test_deploy_command_blocked(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("执行 vercel deploy 部署")
        assert result.allowed is False

    def test_case_insensitive(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("DROP TABLE users")
        assert result.allowed is False

    def test_multiple_violations(self, guard: PermissionGuard) -> None:
        result = guard.check_prompt("rm -rf / && DROP TABLE users")
        assert result.allowed is False
        assert len(result.blocked_violations) >= 2


# ── check_diff ───────────────────────────────────────────────


class TestCheckDiff:
    def test_no_git_repo_allowed(self, guard: PermissionGuard, tmp_path: Path) -> None:
        """非 git 目录应返回 allowed=True（降级处理）"""
        non_git = tmp_path / "non_git"
        non_git.mkdir()
        result = guard.check_diff(non_git)
        assert result.allowed is True

    def test_empty_diff_allowed(
        self, guard: PermissionGuard, git_repo: Path
    ) -> None:
        result = guard.check_diff(git_repo)
        assert result.allowed is True

    def test_normal_file_change_allowed(
        self, guard: PermissionGuard, git_repo: Path
    ) -> None:
        (git_repo / "src" / "app.py").write_text("print('hello')")
        result = guard.check_diff(git_repo)
        assert result.allowed is True

    def test_dangerous_file_modify_blocked(
        self, guard: PermissionGuard, git_repo: Path
    ) -> None:
        (git_repo / ".env").write_text("SECRET=abc")
        subprocess.run(["git", "add", ".env"], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add env"], cwd=git_repo, check=True, capture_output=True
        )
        # 修改已追踪的 .env 文件
        (git_repo / ".env").write_text("SECRET=xyz")
        result = guard.check_diff(git_repo)
        assert result.allowed is False
        assert any(
            v.operation == "dangerous_file_modify" for v in result.violations
        )

    def test_single_file_delete_protected(
        self, guard: PermissionGuard, git_repo: Path
    ) -> None:
        # 先创建并提交 old.py
        (git_repo / "src" / "old.py").write_text("# old file")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add old.py"], cwd=git_repo, check=True, capture_output=True
        )
        # 然后删除
        (git_repo / "src" / "old.py").unlink()
        result = guard.check_diff(git_repo)
        assert result.allowed is True  # PROTECTED 不阻塞
        assert len(result.protected_violations) == 1
        assert result.protected_violations[0].operation == "single_file_delete"

    def test_bulk_delete_blocked(
        self, guard: PermissionGuard, git_repo: Path
    ) -> None:
        # 创建并提交超过阈值的文件，然后删除
        src = git_repo / "src"
        for i in range(BULK_DELETE_THRESHOLD + 1):
            (src / f"file_{i}.py").write_text(f"# file {i}")
        import subprocess

        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add files"], cwd=git_repo, check=True
        )
        for i in range(BULK_DELETE_THRESHOLD + 1):
            (src / f"file_{i}.py").unlink()
        result = guard.check_diff(git_repo)
        assert result.allowed is False
        assert any(v.operation == "bulk_delete" for v in result.violations)


# ── backup_file ──────────────────────────────────────────────


class TestBackupFile:
    def test_backup_creates_copy(
        self, guard: PermissionGuard, tmp_path: Path
    ) -> None:
        src = tmp_path / "test.py"
        src.write_text("print('hello')")
        backup = guard.backup_file(src, tmp_path)
        assert backup is not None
        assert backup.exists()
        assert backup.read_text() == "print('hello')"

    def test_backup_nonexistent_returns_none(
        self, guard: PermissionGuard, tmp_path: Path
    ) -> None:
        src = tmp_path / "nonexistent.py"
        result = guard.backup_file(src, tmp_path)
        assert result is None

    def test_backup_avoids_overwrite(
        self, guard: PermissionGuard, tmp_path: Path
    ) -> None:
        src = tmp_path / "test.py"
        src.write_text("v1")
        b1 = guard.backup_file(src, tmp_path)
        src.write_text("v2")
        b2 = guard.backup_file(src, tmp_path)
        assert b1 is not None and b2 is not None
        assert b1 != b2
        assert b1.read_text() == "v1"
        assert b2.read_text() == "v2"


# ── PERMISSION_RULES_PROMPT ──────────────────────────────────


class TestPermissionRulesPrompt:
    def test_not_empty(self) -> None:
        assert len(PERMISSION_RULES_PROMPT) > 100

    def test_contains_key_rules(self) -> None:
        assert "禁止" in PERMISSION_RULES_PROMPT
        assert "允许" in PERMISSION_RULES_PROMPT
        assert "谨慎" in PERMISSION_RULES_PROMPT

    def test_mentions_dangerous_ops(self) -> None:
        assert "批量删除" in PERMISSION_RULES_PROMPT
        assert ".env" in PERMISSION_RULES_PROMPT
        assert "DROP" in PERMISSION_RULES_PROMPT


# ── git_repo fixture ─────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """创建一个有提交历史的临时 git 仓库"""
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # 创建初始文件并提交
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hello')")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path
