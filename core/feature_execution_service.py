"""Feature 执行服务 — 从 ProjectManager 拆分的执行逻辑"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.verification_result import ExecutionResult

if TYPE_CHECKING:
    from agents.pool import AgentPool
    from core.feature_tracker import Feature, FeatureTracker


@runtime_checkable
class ExecutableAgent(Protocol):
    """Agent 执行接口 — 任何拥有 async execute(ctx) -> dict 的对象均可注入。"""

    async def execute(self, context: dict, *, workspace_dir: Path | None = None) -> dict: ...

    @property
    def workspace_path(self) -> str: ...


logger = logging.getLogger(__name__)


class FeatureExecutionService:
    """负责单个 Feature 的执行流程。"""

    def __init__(
        self,
        project_manager,
        pool: AgentPool,
        tracker: FeatureTracker,
    ) -> None:
        self._pm = project_manager
        self._pool = pool
        self._tracker = tracker  # Reserved for execution run tracking

    async def execute(
        self,
        feature: Feature,
        agent: ExecutableAgent,
        *,
        prd_summary: str | None = None,
        dependencies_context: dict | None = None,
        workspace_dir: Path | str | None = None,
    ) -> dict:
        """执行单个 Feature，返回执行结果。

        Args:
            feature: 要执行的 Feature 对象
            agent: 负责执行的 Agent 实例
            prd_summary: PRD 摘要，由调用方提供以避免耦合私有方法
            dependencies_context: 依赖上下文，由调用方提供以避免耦合私有方法
            workspace_dir: Agent 隔离工作目录

        Returns:
            {"success": bool, "files_changed": list, "error": str (可选)}
        """
        try:
            ws_dir = Path(workspace_dir) if workspace_dir else None
            result = await agent.execute(
                {
                    "feature_id": feature.id,
                    "description": feature.description,
                    "category": feature.category,
                    "priority": feature.priority,
                    "test_steps": getattr(feature, "test_steps", []),
                    "project_dir": str(self._pm.project_dir),
                    "workspace_dir": str(ws_dir) if ws_dir else "",
                    "prd_summary": prd_summary or "",
                    "dependencies_context": dependencies_context or {},
                },
                workspace_dir=ws_dir,
            )
            if not isinstance(result, dict):
                logger.error("Agent.execute() returned non-dict for %s: %r", feature.id, result)
                return {"success": False, "files_changed": [], "error": "Agent returned non-dict result"}

            files_changed = result.get("files_changed", [])
            diff_stat = self._collect_diff_stat(ws_dir)

            return {
                "success": result.get("success", False),
                "files_changed": files_changed,
                "error": result.get("error", ""),
                "diff_stat": diff_stat,
                "work_id": feature.id,
                "status": "completed" if result.get("success") else "failed",
            }
        except Exception as e:
            logger.error("Feature execution error for %s: %s", feature.id, e)
            return {"success": False, "files_changed": [], "error": str(e), "status": "failed", "work_id": feature.id}

    @staticmethod
    def _collect_diff_stat(workspace_dir: Path | None) -> str:
        """收集 git diff --stat 作为执行证据。"""
        if workspace_dir is None:
            return ""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return ""
