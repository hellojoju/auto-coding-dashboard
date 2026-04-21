"""Feature 执行服务 — 从 ProjectManager 拆分的执行逻辑"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agents.pool import AgentPool
    from core.feature_tracker import Feature, FeatureTracker


@runtime_checkable
class ExecutableAgent(Protocol):
    """Agent 执行接口 — 任何拥有 async execute(ctx) -> dict 的对象均可注入。"""

    async def execute(self, context: dict) -> dict: ...

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
    ) -> dict:
        """执行单个 Feature，返回执行结果。

        Args:
            feature: 要执行的 Feature 对象
            agent: 负责执行的 Agent 实例
            prd_summary: PRD 摘要，由调用方提供以避免耦合私有方法
            dependencies_context: 依赖上下文，由调用方提供以避免耦合私有方法

        Returns:
            {"success": bool, "files_changed": list, "error": str (可选)}
        """
        try:
            result = await agent.execute(
                {
                    "feature_id": feature.id,
                    "description": feature.description,
                    "category": feature.category,
                    "priority": feature.priority,
                    "test_steps": getattr(feature, "test_steps", []),
                    "project_dir": str(self._pm.project_dir),
                    "workspace_dir": str(agent.workspace_path),
                    "prd_summary": prd_summary or "",
                    "dependencies_context": dependencies_context or {},
                }
            )
            if not isinstance(result, dict):
                logger.error("Agent.execute() returned non-dict for %s: %r", feature.id, result)
                return {"success": False, "files_changed": [], "error": "Agent returned non-dict result"}
            return {
                "success": result.get("success", False),
                "files_changed": result.get("files_changed", []),
                "error": result.get("error", ""),
            }
        except Exception as e:
            logger.error("Feature execution error for %s: %s", feature.id, e)
            return {"success": False, "files_changed": [], "error": str(e)}
