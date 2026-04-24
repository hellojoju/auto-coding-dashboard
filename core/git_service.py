"""Git 操作服务 — 从 ProjectManager 拆分"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Git 操作失败时抛出"""
    pass


class GitService:
    """封装所有 Git 操作"""

    def __init__(self, repo_dir: Path | str) -> None:
        self._repo_dir = Path(repo_dir).resolve()
        if not self._repo_dir:
            raise ValueError("repo_dir cannot be empty")

    def init(self) -> None:
        """初始化 git 仓库"""
        if not (self._repo_dir / ".git").exists():
            self._run(["git", "init"], cwd=self._repo_dir)

    def commit(self, message: str) -> bool:
        """提交变更。如果没有变更返回 False。"""
        if not message:
            raise ValueError("commit message cannot be empty")
        self._run(["git", "add", "-A"], cwd=self._repo_dir)
        # 检查是否有变更
        result = self._run(["git", "status", "--porcelain"], cwd=self._repo_dir, capture_output=True)
        if not result.stdout.strip():
            return False
        self._run(["git", "commit", "-m", message], cwd=self._repo_dir)
        return True

    def create_branch(self, branch_name: str) -> None:
        """创建分支"""
        if not branch_name:
            raise ValueError("branch_name cannot be empty")
        if re.search(r'[\s~^:?*[\]\\]', branch_name):
            raise ValueError(f"Invalid branch name: {branch_name}")
        self._run(["git", "branch", branch_name], cwd=self._repo_dir)

    def list_branches(self) -> list[str]:
        """列出本地分支"""
        result = self._run(["git", "branch"], cwd=self._repo_dir, capture_output=True)
        branches = []
        for b in result.stdout.strip().splitlines():
            if b.startswith("* "):
                branches.append(b[2:].strip())
            else:
                branches.append(b.strip())
        return branches

    def log(self, limit: int = 10) -> list[str]:
        """获取提交历史"""
        try:
            result = self._run(
                ["git", "log", f"--max-count={limit}", "--oneline"],
                cwd=self._repo_dir,
                capture_output=True,
            )
        except GitError:
            logger.debug("No commits in repository yet")
            return []
        return result.stdout.strip().splitlines() if result.stdout.strip() else []

    def _run(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        """执行 git 命令"""
        try:
            kwargs.setdefault("text", True)
            return subprocess.run(cmd, check=True, **kwargs)
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: {' '.join(cmd)}: {e.stderr}") from e
