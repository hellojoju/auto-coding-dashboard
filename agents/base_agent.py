"""Agent基类 - 所有角色的统一接口"""

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.config import PROMPTS_DIR
from core.progress_logger import progress


class BaseAgent(ABC):
    """所有Agent的基类"""

    role: str = "base"
    prompt_file: str = ""
    event_bus: Any = None  # 由 ProjectManager 注入

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)  # 确保是 Path 对象
        self.system_prompt = self._load_prompt()

    @property
    def workspace_path(self) -> str:
        """供 FeatureExecutionService 读取的工作目录"""
        return str(self.project_dir)

    def _report_status(self, status: str, feature_id: str = "", message: str = "", **extra: Any) -> None:
        """上报执行状态到 EventBus（如果已注入）。"""
        if self.event_bus is None:
            return
        payload = {
            "agent_role": self.role,
            "feature_id": feature_id,
            "status": status,
            "message": message,
            **extra,
        }
        self.event_bus.emit("agent_status_changed", **payload)

    def _load_prompt(self) -> str:
        """加载prompt模板"""
        prompt_file = self.prompt_file or f"{self.role}.md"
        if not prompt_file.endswith(".md"):
            prompt_file += ".md"
        prompt_path = PROMPTS_DIR / prompt_file
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return f"你是一个{self.role}。请用中文回答。"

    @abstractmethod
    def _build_prompt(self, task: dict) -> str:
        """
        构建完整的执行 prompt。
        子类必须实现，结合 system_prompt + task 描述 + 执行要求。

        Args:
            task: 任务字典，包含 feature_id, description, context 等

        Returns:
            完整的 prompt 字符串，直接传给 claude -p
        """
        ...

    async def execute(self, task: dict, workspace_dir: Path | None = None) -> dict:
        """
        执行任务。默认实现：构建 prompt → 调用 Claude CLI → 解析结果。
        子类一般只需覆盖 _build_prompt()。

        Args:
            task: 任务字典
            workspace_dir: 可选的工作目录，AgentPool 传入隔离的 workspace，不传则使用 project_dir
        """
        feature_id = task.get("feature_id", "unknown")
        description = task.get("description", "")[:100]
        self._log(f"开始{self.role}任务: {feature_id} - {description}")
        self._report_status("running", feature_id=feature_id, message=f"开始执行: {description}")

        prompt = self._build_prompt(task)
        result = self._run_with_claude(prompt, workspace_dir=workspace_dir)

        files_changed = self._extract_files_changed(workspace_dir=workspace_dir)

        if result["success"]:
            self._report_status("completed", feature_id=feature_id, message="任务执行完成")
            return {
                "success": True,
                "message": f"{self.role}任务 {feature_id} 执行完成",
                "files_changed": files_changed,
                "needs_review": True,
            }
        else:
            error = result.get("error", "未知错误")
            self._report_status("failed", feature_id=feature_id, message=f"任务执行失败: {error}")
            return {
                "success": False,
                "message": f"{self.role}任务 {feature_id} 执行失败",
                "files_changed": [],
                "needs_review": False,
                "error": error,
            }

    def _log(self, message: str) -> None:
        progress.log(f"[{self.role}] {message}")

    def _git_commit(self, message: str) -> bool:
        """执行git提交"""
        import subprocess
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.project_dir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.project_dir,
                capture_output=True,
                check=True,
            )
            self._log(f"git commit: {message}")
            return True
        except subprocess.CalledProcessError as e:
            self._log(f"git commit 失败: {e.stderr.decode()}")
            return False

    def _run_with_claude(self, prompt: str, timeout: int = 600, workspace_dir: Path | None = None) -> dict:
        """
        通过 Claude CLI 执行任务。

        Args:
            prompt: 完整的 prompt（包含 system prompt + task description）
            timeout: 超时时间（秒），默认 10 分钟
            workspace_dir: 工作目录，不传则使用 self.project_dir

        Returns:
            {"success": bool, "stdout": str, "stderr": str, "error": str (optional)}
        """
        # 写入临时任务文件，方便调试和追溯
        target_dir = workspace_dir or self.project_dir
        tasks_dir = target_dir / ".tasks"
        tasks_dir.mkdir(exist_ok=True)
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix="task-",
            suffix=".md",
            dir=tasks_dir,
            delete=False,
        ) as f:
            f.write(prompt)
            _task_file = f.name

        cmd = [
            "claude",
            "-p", prompt,
            "--dangerously-skip-permissions",
        ]

        cwd = workspace_dir or self.project_dir
        self._log(f"claude -p 执行目录: {cwd}")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                timeout=timeout,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            if result.returncode == 0:
                self._log(f"任务执行成功, 输出 {len(stdout)} 字符")
                return {"success": True, "stdout": stdout, "stderr": stderr}
            else:
                error = stderr or stdout
                self._log(f"任务执行失败: {error[:200]}")
                return {"success": False, "error": error}

        except subprocess.TimeoutExpired:
            self._log(f"任务执行超时({timeout}秒)")
            return {"success": False, "error": f"执行超时({timeout}秒)"}
        except FileNotFoundError:
            self._log("claude CLI未找到")
            return {"success": False, "error": "claude CLI未找到，请先安装Claude Code CLI"}

    def _extract_files_changed(self, workspace_dir: Path | None = None) -> list[str]:
        """通过 git diff 检测本次执行修改了哪些文件"""
        cwd = workspace_dir or self.project_dir
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            return [f for f in result.stdout.strip().split("\n") if f]
        except subprocess.CalledProcessError:
            return []
