"""测试 GitService"""
import subprocess

import pytest

from core.git_service import GitError, GitService


@pytest.fixture
def git_service(tmp_path):
    service = GitService(tmp_path)
    service.init()
    return service


@pytest.fixture
def configured_git(git_service, tmp_path):
    """配置 git 用户信息（测试用）"""
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    return git_service


def test_init_creates_git_dir(git_service, tmp_path):
    assert (tmp_path / ".git").exists()


def test_commit(configured_git, tmp_path):
    # 创建文件
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")

    configured_git.commit("feat: add test file")

    log = configured_git.log()
    assert len(log) >= 1
    assert "feat: add test file" in log[0]


def test_commit_no_changes(configured_git, tmp_path):
    result = configured_git.commit("nothing to commit")
    assert result is False


def test_create_branch(configured_git, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    configured_git.commit("initial commit")

    configured_git.create_branch("test-branch")
    branches = configured_git.list_branches()
    assert "test-branch" in branches


def test_list_branches_empty(git_service, tmp_path):
    """空仓库时尚无分支（分支在首次提交后才真正创建）"""
    branches = git_service.list_branches()
    # git init 后 git branch 返回空列表，因为分支尚未创建
    assert branches == []


def test_list_branches_multiple(configured_git, tmp_path):
    """多分支时正确列出"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    configured_git.commit("initial commit")

    configured_git.create_branch("branch-a")
    configured_git.create_branch("branch-b")

    branches = configured_git.list_branches()
    assert "branch-a" in branches
    assert "branch-b" in branches
    # 当前分支也应该在列表中
    assert len(branches) >= 3  # master/main + branch-a + branch-b


def test_log_limit(configured_git, tmp_path):
    """log 的 limit 参数"""
    test_file = tmp_path / "test.txt"
    for i in range(5):
        test_file.write_text(f"version {i}")
        configured_git.commit(f"commit {i}")

    # 限制 3 条
    logs = configured_git.log(limit=3)
    assert len(logs) == 3


def test_log_empty_repo(git_service, tmp_path):
    """空仓库 log 返回空"""
    logs = git_service.log()
    assert logs == []


def test_commit_empty_message_raises(git_service):
    """空提交消息应抛出 ValueError"""
    with pytest.raises(ValueError, match="commit message cannot be empty"):
        git_service.commit("")


def test_create_branch_empty_name_raises(git_service):
    """空分支名应抛出 ValueError"""
    with pytest.raises(ValueError, match="branch_name cannot be empty"):
        git_service.create_branch("")


def test_create_branch_invalid_name_raises(git_service):
    """非法分支名应抛出 ValueError"""
    with pytest.raises(ValueError, match="Invalid branch name"):
        git_service.create_branch("bad name with space")


def test_git_error_raised_on_failure(git_service):
    """失败 git 命令应抛出 GitError"""
    with pytest.raises(GitError):
        git_service._run(["git", "nonexistent-command"])
