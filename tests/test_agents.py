"""Tests for Agent architecture"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agents import AGENT_REGISTRY, AGENT_ROLES, get_agent
from agents.base_agent import BaseAgent


class TestAgentRegistry:
    def test_all_roles_registered(self):
        """所有角色都在注册表中"""
        expected_roles = {
            "backend", "frontend", "qa", "product", "ui_designer",
            "database", "security", "docs", "architect",
        }
        assert set(AGENT_REGISTRY.keys()) == expected_roles

    def test_all_roles_have_names(self):
        """所有角色都有中文名称"""
        for role in AGENT_REGISTRY:
            assert role in AGENT_ROLES, f"角色 {role} 缺少中文名称"

    def test_get_agent_returns_instance(self, tmp_path):
        """get_agent 返回正确的 Agent 实例"""
        for role in AGENT_REGISTRY:
            agent = get_agent(role, tmp_path)
            assert isinstance(agent, BaseAgent)
            assert agent.role == role

    def test_get_agent_unknown_role(self, tmp_path):
        """未知角色抛出 ValueError"""
        with pytest.raises(ValueError, match="未知的Agent角色"):
            get_agent("unknown_role", tmp_path)


def _make_subprocess_side_effect(claude_rc=0, claude_stdout=b"done", claude_stderr=b""):
    """为 subprocess.run 创建 side_effect"""
    def side_effect(*args, **kwargs):
        _cmd = args[0] if args else kwargs.get("cmd") if kwargs else None
        if isinstance(_cmd, list) and _cmd and _cmd[0] == "claude":
            mock_result = MagicMock()
            mock_result.returncode = claude_rc
            mock_result.stdout = claude_stdout
            mock_result.stderr = claude_stderr
            return mock_result
        else:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result
    return side_effect


class TestBaseAgent:
    def test_load_prompt_from_file(self, tmp_path):
        """从文件加载 prompt"""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "backend_dev.md").write_text("你是后端开发工程师，负责后端开发工作。", encoding="utf-8")

        with patch("agents.base_agent.PROMPTS_DIR", prompts_dir):
            agent = get_agent("backend", tmp_path)
            assert "后端开发工程师" in agent.system_prompt

    def test_load_prompt_fallback(self, tmp_path):
        """找不到文件时使用 fallback"""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        with patch("agents.base_agent.PROMPTS_DIR", prompts_dir):
            agent = get_agent("backend", tmp_path)
            # 文件存在，应该加载成功
            assert len(agent.system_prompt) > 0

    def test_build_prompt_includes_task_info(self, tmp_path):
        """_build_prompt 包含任务关键信息"""
        agent = get_agent("backend", tmp_path)
        task = {
            "feature_id": "F001",
            "description": "创建用户注册API",
            "category": "auth",
            "test_steps": ["测试注册", "验证响应"],
            "prd_summary": "PRD摘要",
            "dependencies_context": "无依赖",
            "project_dir": str(tmp_path),
        }
        prompt = agent._build_prompt(task)
        assert "F001" in prompt
        assert "创建用户注册API" in prompt
        assert "auth" in prompt
        assert "PRD摘要" in prompt

    def test_execute_success_with_mocked_claude(self, tmp_path):
        """execute 在 claude 成功时返回 success"""
        with patch("subprocess.run", side_effect=_make_subprocess_side_effect()):
            agent = get_agent("backend", tmp_path)
            import asyncio
            result = asyncio.run(agent.execute({
                "feature_id": "F001",
                "description": "测试任务",
                "category": "auth",
                "test_steps": [],
                "prd_summary": "",
                "dependencies_context": "",
                "project_dir": str(tmp_path),
            }))
            assert result["success"] is True
            assert "F001" in result["message"]

    def test_execute_failure_with_mocked_claude(self, tmp_path):
        """execute 在 claude 失败时返回 failure"""
        with patch("subprocess.run", side_effect=_make_subprocess_side_effect(
            claude_rc=1, claude_stdout=b"", claude_stderr=b"error: something went wrong"
        )):
            agent = get_agent("backend", tmp_path)
            import asyncio
            result = asyncio.run(agent.execute({
                "feature_id": "F002",
                "description": "失败任务",
                "category": "auth",
                "test_steps": [],
                "prd_summary": "",
                "dependencies_context": "",
                "project_dir": str(tmp_path),
            }))
            assert result["success"] is False
            assert "error" in result

    def test_execute_claude_not_found(self, tmp_path):
        """claude CLI 不存在时的错误处理"""
        call_count = {"n": 0}
        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise FileNotFoundError
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        with patch("subprocess.run", side_effect=side_effect):
            agent = get_agent("backend", tmp_path)
            import asyncio
            result = asyncio.run(agent.execute({
                "feature_id": "F003",
                "description": "测试",
                "category": "auth",
                "test_steps": [],
                "prd_summary": "",
                "dependencies_context": "",
                "project_dir": str(tmp_path),
            }))
            assert result["success"] is False
            assert "claude CLI未找到" in result["error"]

    def test_execute_timeout(self, tmp_path):
        """超时错误处理"""
        call_count = {"n": 0}
        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise subprocess.TimeoutExpired(cmd="claude", timeout=600)
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        with patch("subprocess.run", side_effect=side_effect):
            agent = get_agent("backend", tmp_path)
            import asyncio
            result = asyncio.run(agent.execute({
                "feature_id": "F004",
                "description": "超时任务",
                "category": "auth",
                "test_steps": [],
                "prd_summary": "",
                "dependencies_context": "",
                "project_dir": str(tmp_path),
            }))
            assert result["success"] is False
            assert "超时" in result["error"]

    def test_git_commit_success(self, tmp_path):
        """git commit 成功"""
        # 初始化 git
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)

        # 创建文件
        (tmp_path / "test.py").write_text("print('hello')", encoding="utf-8")

        agent = get_agent("backend", tmp_path)
        result = agent._git_commit("test: commit message")
        assert result is True

    def test_git_commit_no_changes(self, tmp_path):
        """git commit 无变更时返回 False"""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)

        agent = get_agent("backend", tmp_path)
        result = agent._git_commit("test: no changes")
        # --allow-empty 不在 base_agent 中，所以无变更时会失败
        assert result is False

    def test_extract_files_changed(self, tmp_path):
        """提取变更文件列表"""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)

        # 创建并 commit 文件
        (tmp_path / "test.py").write_text("print('hello')", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        # 修改文件
        (tmp_path / "test.py").write_text("print('world')", encoding="utf-8")

        agent = get_agent("backend", tmp_path)
        changed = agent._extract_files_changed()
        assert "test.py" in changed


class TestAllAgentSubclasses:
    """测试所有 Agent 子类都能正确实例化"""

    @pytest.mark.parametrize("role", list(AGENT_REGISTRY.keys()))
    def test_agent_instantiation(self, role, tmp_path):
        """每个 Agent 都能成功实例化"""
        agent = get_agent(role, tmp_path)
        assert agent is not None
        assert agent.system_prompt is not None
        assert len(agent.system_prompt) > 10  # prompt 应该有内容

    @pytest.mark.parametrize("role", list(AGENT_REGISTRY.keys()))
    def test_agent_build_prompt(self, role, tmp_path):
        """每个 Agent 的 _build_prompt 都能正常工作"""
        agent = get_agent(role, tmp_path)
        task = {
            "feature_id": "F001",
            "description": f"测试{role}任务",
            "category": role,
            "test_steps": ["步骤1"],
            "prd_summary": "测试PRD",
            "dependencies_context": "无依赖",
            "project_dir": str(tmp_path),
        }
        prompt = agent._build_prompt(task)
        assert "F001" in prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 50  # prompt 应该包含足够的信息
