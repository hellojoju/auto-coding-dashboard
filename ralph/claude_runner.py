"""Claude Code Runner — 结构化 Claude CLI 执行器

文档依据：
- AI 协议 §6.4 harness 不是提示词 — 必须以结构化数据保存
- PRD §8.1 系统负责长期控制 — Claude Code 只执行带 context_pack 和 task_harness 的短任务
- 实施方案 §4.14 Claude Code Runner

职责：
- 从 ContextPack + TaskHarness 构造结构化 prompt
- 调用 claude -p --permission-mode acceptEdits
- 解析执行结果，提取结构化 ExecutionResult
- 执行后收集 git diff 作为结果的一部分
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ==================== 结构化执行结果 ====================

@dataclass(frozen=True)
class ExecutionResult:
    """Claude Code 执行的结构化结果（对齐 AI 协议 §8.2）"""
    work_id: str
    success: bool
    stdout: str
    stderr: str
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    scope_violations: list[str] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    evidence_files: list[str] = field(default_factory=list)
    harness_violations: list[str] = field(default_factory=list)
    risks_observed: str = ""
    error: str | None = None


# ==================== Prompt 构建 ====================

def build_execution_prompt(
    work_id: str,
    context_pack_text: str,
    harness_text: str,
    scope_allow: list[str],
    scope_deny: list[str],
    acceptance_criteria: list[str],
) -> str:
    """从 ContextPack + TaskHarness 构造执行 prompt。

    结构：
    1. 任务目标
    2. 上下文包（最小必要信息）
    3. 任务 Harness 约束（允许/禁止的范围、工具、门禁）
    4. 验收标准
    5. 输出格式要求（结构化 JSON）
    """
    scope_allow_text = "\n".join(f"- {p}" for p in scope_allow) if scope_allow else "无限制"
    scope_deny_text = "\n".join(f"- {p}" for p in scope_deny) if scope_deny else "无限制"
    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria) if acceptance_criteria else "无"

    return f"""# WorkUnit: {work_id}

## 任务目标

{context_pack_text}

## 任务 Harness 约束

{harness_text}

## 修改范围

允许修改：
{scope_allow_text}

禁止修改：
{scope_deny_text}

## 验收标准

{criteria_text}

## 执行要求

1. 只修改允许范围内的文件
2. 不要修改禁止范围内的任何内容
3. 执行完成后，在修改的文件中写入一个 JSON 格式的总结，格式如下：
```json
{{
  "files_created": ["新建的文件路径"],
  "files_modified": ["修改的文件路径"],
  "files_deleted": ["删除的文件路径"],
  "scope_violations": ["如果有越界修改，列出路径"],
  "test_results": {{"test_name": "pass/fail"}},
  "risks_observed": "观察到的任何风险或注意事项"
}}
```
4. 将这个 JSON 总结写入 `.ralph/execution_results/{work_id}.json`
"""


# ==================== 权限规则提示 ====================

PERMISSION_RULES = """
## 安全规则

- 不要删除项目目录外的任何文件
- 不要修改 .env 文件或任何包含密钥的文件
- 不要执行数据库 DROP/TRUNCATE 操作
- 不要运行发布命令
- 如果需要对 5 个或更多文件执行批量删除，请停止并请求人工批准
"""


# ==================== Claude Code Runner ====================

class ClaudeCodeRunner:
    """Claude Code 结构化执行器。

    封装 Claude CLI 调用，提供结构化输入输出。
    """

    def __init__(
        self,
        project_dir: Path,
        timeout: int = 600,
        claude_bin: str = "claude",
    ) -> None:
        self._project_dir = Path(project_dir)
        self._timeout = timeout
        self._claude_bin = claude_bin

    def execute(
        self,
        work_id: str,
        context_pack_text: str,
        harness_text: str,
        scope_allow: list[str],
        scope_deny: list[str],
        acceptance_criteria: list[str],
    ) -> ExecutionResult:
        """同步执行一个 WorkUnit（内部调用 execute_streaming）。"""
        return asyncio.run(self.execute_streaming(
            work_id=work_id,
            context_pack_text=context_pack_text,
            harness_text=harness_text,
            scope_allow=scope_allow,
            scope_deny=scope_deny,
            acceptance_criteria=acceptance_criteria,
            stream_callback=None,
        ))

    async def execute_streaming(
        self,
        work_id: str,
        context_pack_text: str,
        harness_text: str,
        scope_allow: list[str],
        scope_deny: list[str],
        acceptance_criteria: list[str],
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> ExecutionResult:
        """异步执行一个 WorkUnit，支持流式输出。

        Args:
            work_id: WorkUnit ID
            context_pack_text: 上下文包文本
            harness_text: Harness 约束文本
            scope_allow: 允许修改的路径列表
            scope_deny: 禁止修改的路径列表
            acceptance_criteria: 验收标准列表
            stream_callback: 可选的流式回调，签名 (event_type, chunk_text)

        Returns:
            ExecutionResult 结构化执行结果
        """
        prompt = build_execution_prompt(
            work_id=work_id,
            context_pack_text=context_pack_text,
            harness_text=harness_text,
            scope_allow=scope_allow,
            scope_deny=scope_deny,
            acceptance_criteria=acceptance_criteria,
        )
        prompt += PERMISSION_RULES

        cmd = [
            self._claude_bin,
            "-p", prompt,
            "--permission-mode", "acceptEdits",
            "--output-format", "stream-json",
            "--verbose",
        ]

        logger.info("Claude 流式执行: %s", work_id)

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self._project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # 并发读取 stdout 和 stderr
            async def _read_stdout() -> None:
                assert proc.stdout is not None
                async for raw_line in proc.stdout:
                    line = raw_line.decode("utf-8", errors="replace")
                    stdout_parts.append(line)
                    self._parse_stream_line(line, stream_callback)

            async def _read_stderr() -> None:
                assert proc.stderr is not None
                async for raw_line in proc.stderr:
                    line = raw_line.decode("utf-8", errors="replace")
                    stderr_parts.append(line)

            # 并发读取 + 等待进程退出
            await asyncio.gather(
                _read_stdout(),
                _read_stderr(),
            )
            return_code = await proc.wait()

        except FileNotFoundError:
            logger.error("claude CLI 未找到")
            return ExecutionResult(
                work_id=work_id,
                success=False,
                stdout="",
                stderr="",
                error="claude CLI 未找到，请先安装 Claude Code CLI",
            )
        except asyncio.TimeoutError:
            logger.error("任务执行超时(%d秒)", self._timeout)
            return ExecutionResult(
                work_id=work_id,
                success=False,
                stdout="",
                stderr="",
                error=f"执行超时({self._timeout}秒)",
            )

        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)

        if return_code != 0:
            error = stderr or stdout
            logger.error("Claude 执行失败: %s", error[:500])
            return ExecutionResult(
                work_id=work_id,
                success=False,
                stdout=stdout,
                stderr=stderr,
                error=error,
            )

        logger.info("任务执行成功, 输出 %d 字符", len(stdout))

        # 收集 git diff 结果
        files_created, files_modified, files_deleted = self._collect_git_diff()

        # 尝试读取结构化结果
        structured_result = self._read_structured_result(work_id)

        return ExecutionResult(
            work_id=work_id,
            success=True,
            stdout=stdout,
            stderr=stderr,
            files_created=files_created,
            files_modified=files_modified,
            files_deleted=files_deleted,
            test_results=structured_result.get("test_results", {}),
            scope_violations=structured_result.get("scope_violations", []),
            risks_observed=structured_result.get("risks_observed", ""),
        )

    def _parse_stream_line(
        self,
        line: str,
        stream_callback: Callable[[str, str], None] | None,
    ) -> None:
        """解析 stream-json 输出的一行，提取有用内容并触发回调。"""
        line = line.strip()
        if not line:
            return
        try:
            obj = json.loads(line)
            event_type = obj.get("type", "")

            # 提取 assistant 消息文本
            if event_type == "assistant":
                result_text = obj.get("result", "")
                if result_text and stream_callback:
                    stream_callback("text", result_text)
            elif event_type == "result":
                # 最终结果
                if stream_callback:
                    status = obj.get("subtype", "unknown")
                    stream_callback("result", f"执行完成: {status}")
        except json.JSONDecodeError:
            # 非 JSON 行，忽略（可能是调试输出）
            pass

    def _collect_git_diff(self) -> tuple[list[str], list[str], list[str]]:
        """通过 git diff 收集文件变更。

        Returns:
            (files_created, files_modified, files_deleted)
        """
        try:
            # 新增文件（untracked）
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self._project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            files_created = [f for f in untracked.stdout.strip().split("\n") if f]

            # 修改文件
            modified_result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self._project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            files_modified = [f for f in modified_result.stdout.strip().split("\n") if f]

            # 删除文件
            deleted_result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=D", "HEAD"],
                cwd=self._project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            files_deleted = [f for f in deleted_result.stdout.strip().split("\n") if f]

            return files_created, files_modified, files_deleted
        except subprocess.CalledProcessError:
            return [], [], []

    def _read_structured_result(self, work_id: str) -> dict[str, Any]:
        """读取 Claude 写入的结构化执行结果。"""
        result_path = self._project_dir / ".ralph" / "execution_results" / f"{work_id}.json"
        if result_path.exists():
            try:
                content = result_path.read_text(encoding="utf-8")
                return json.loads(content)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("解析结构化结果失败: %s", e)
        return {}
