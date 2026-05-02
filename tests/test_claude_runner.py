"""Claude Code Runner 测试"""

import json
import subprocess
from pathlib import Path

from ralph.claude_runner import ClaudeCodeRunner, build_execution_prompt

# ── Prompt Builder ──────────────────────────────────────────


class TestBuildExecutionPrompt:
    def test_basic_prompt_structure(self) -> None:
        prompt = build_execution_prompt(
            work_id="W-1",
            context_pack_text="实现用户 API",
            harness_text="只修改 src/api/",
            scope_allow=["src/api/"],
            scope_deny=[".env"],
            acceptance_criteria=["测试通过"],
        )

        assert "W-1" in prompt
        assert "实现用户 API" in prompt
        assert "只修改 src/api/" in prompt
        assert "src/api/" in prompt
        assert ".env" in prompt
        assert "测试通过" in prompt
        assert "JSON" in prompt
        assert "files_created" in prompt
        assert "files_modified" in prompt

    def test_empty_scope_shows_no_limit(self) -> None:
        prompt = build_execution_prompt(
            work_id="W-2",
            context_pack_text="任务",
            harness_text="",
            scope_allow=[],
            scope_deny=[],
            acceptance_criteria=[],
        )

        assert "无限制" in prompt
        assert "无" in prompt

    def test_prompt_includes_execution_requirements(self) -> None:
        prompt = build_execution_prompt(
            work_id="W-3",
            context_pack_text="任务",
            harness_text="",
            scope_allow=["src/"],
            scope_deny=[".env"],
            acceptance_criteria=["pass"],
        )

        assert "只修改允许范围内的文件" in prompt
        assert "不要修改禁止范围内的任何内容" in prompt


# ── Permission Rules ────────────────────────────────────────


def test_permission_rules_constant() -> None:
    from ralph.claude_runner import PERMISSION_RULES

    assert ".env" in PERMISSION_RULES
    assert "DROP" in PERMISSION_RULES
    assert "TRUNCATE" in PERMISSION_RULES
    assert "批量删除" in PERMISSION_RULES


# ── ClaudeCodeRunner ────────────────────────────────────────


class TestClaudeCodeRunner:
    def test_init(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        assert runner._project_dir == tmp_path
        assert runner._timeout == 600

    def test_init_custom_timeout(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path, timeout=1200, claude_bin="/usr/local/bin/claude")
        assert runner._timeout == 1200
        assert runner._claude_bin == "/usr/local/bin/claude"

    def test_collect_git_diff_no_repo(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        created, modified, deleted = runner._collect_git_diff()
        assert created == []
        assert modified == []
        assert deleted == []

    def test_collect_git_diff_with_changes(self, tmp_path: Path) -> None:
        # 初始化 git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)

        (tmp_path / "test.txt").write_text("initial")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

        # 修改文件
        (tmp_path / "test.txt").write_text("modified")
        # 创建新文件
        (tmp_path / "new.txt").write_text("new")

        runner = ClaudeCodeRunner(tmp_path)
        created, modified, deleted = runner._collect_git_diff()

        assert "test.txt" in modified
        assert "new.txt" in created

    def test_collect_git_diff_detects_deletion(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)

        to_delete = tmp_path / "to_delete.txt"
        to_delete.write_text("will be deleted")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

        to_delete.unlink()

        runner = ClaudeCodeRunner(tmp_path)
        created, modified, deleted = runner._collect_git_diff()

        assert "to_delete.txt" in deleted

    def test_execute_claude_not_found(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path, claude_bin="nonexistent-claude-bin-12345")
        result = runner.execute(
            work_id="W-test",
            context_pack_text="任务",
            harness_text="",
            scope_allow=["src/"],
            scope_deny=[],
            acceptance_criteria=["测试通过"],
        )

        assert not result.success
        assert result.error is not None

    def test_read_structured_result(self, tmp_path: Path) -> None:
        # 写入结构化结果
        result_dir = tmp_path / ".ralph" / "execution_results"
        result_dir.mkdir(parents=True)
        (result_dir / "W-test.json").write_text(json.dumps({
            "files_created": ["new.py"],
            "files_modified": ["app.py"],
            "files_deleted": [],
            "scope_violations": [],
            "test_results": {"test_api": "pass"},
            "risks_observed": "无",
        }))

        runner = ClaudeCodeRunner(tmp_path)
        data = runner._read_structured_result("W-test")

        assert data["files_created"] == ["new.py"]
        assert data["files_modified"] == ["app.py"]
        assert data["test_results"]["test_api"] == "pass"

    def test_read_structured_result_missing(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        data = runner._read_structured_result("W-missing")
        assert data == {}

    def test_read_structured_result_invalid_json(self, tmp_path: Path) -> None:
        result_dir = tmp_path / ".ralph" / "execution_results"
        result_dir.mkdir(parents=True)
        (result_dir / "W-bad.json").write_text("not json")

        runner = ClaudeCodeRunner(tmp_path)
        data = runner._read_structured_result("W-bad")
        assert data == {}


class TestStreamParsing:
    """测试 _parse_stream_line 的流式解析逻辑。"""

    def test_parse_assistant_text(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        chunks: list[tuple[str, str]] = []

        line = json.dumps({"type": "assistant", "result": "正在分析代码..."})
        runner._parse_stream_line(line, lambda et, ct: chunks.append((et, ct)))

        assert chunks == [("text", "正在分析代码...")]

    def test_parse_result_event(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        chunks: list[tuple[str, str]] = []

        line = json.dumps({"type": "result", "subtype": "success"})
        runner._parse_stream_line(line, lambda et, ct: chunks.append((et, ct)))

        assert chunks == [("result", "执行完成: success")]

    def test_parse_system_event_ignored(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        chunks: list[tuple[str, str]] = []

        line = json.dumps({"type": "system", "subtype": "hook_started"})
        runner._parse_stream_line(line, lambda et, ct: chunks.append((et, ct)))

        assert chunks == []

    def test_parse_invalid_json_ignored(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        chunks: list[tuple[str, str]] = []

        runner._parse_stream_line("not json at all", lambda et, ct: chunks.append((et, ct)))
        assert chunks == []

    def test_parse_empty_line_ignored(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        chunks: list[tuple[str, str]] = []

        runner._parse_stream_line("", lambda et, ct: chunks.append((et, ct)))
        assert chunks == []

    def test_parse_assistant_no_result(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)
        chunks: list[tuple[str, str]] = []

        line = json.dumps({"type": "assistant", "subtype": "tool_use"})
        runner._parse_stream_line(line, lambda et, ct: chunks.append((et, ct)))

        assert chunks == []

    def test_parse_no_callback(self, tmp_path: Path) -> None:
        runner = ClaudeCodeRunner(tmp_path)

        line = json.dumps({"type": "assistant", "result": "hello"})
        runner._parse_stream_line(line, None)  # no crash
