"""Feature 执行服务 — 从 ProjectManager 拆分的执行逻辑"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.pool import AgentPool
    from core.feature_tracker import Feature, FeatureTracker

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
        self._tracker = tracker

    def execute(self, feature: Feature, agent) -> dict:
        """执行单个 Feature，返回执行结果。

        Args:
            feature: 要执行的 Feature 对象
            agent: 负责执行的 Agent 实例

        Returns:
            {"success": bool, "files_changed": list, "error": str (可选)}
        """
        try:
            result = asyncio.run(agent.execute({
                "feature_id": feature.id,
                "description": feature.description,
                "category": feature.category,
                "priority": feature.priority,
                "test_steps": getattr(feature, "test_steps", []),
                "project_dir": str(self._pm.project_dir),
                "workspace_dir": str(getattr(agent, "workspace_path", "")),
                "prd_summary": self._pm._get_prd_summary(),
                "dependencies_context": self._pm._get_deps_context(feature),
            }))
            return {
                "success": result.get("success", False),
                "files_changed": result.get("files_changed", []),
                "error": result.get("error", ""),
            }
        except Exception as e:
            logger.error(f"Feature execution error for {feature.id}: {e}")
            return {"success": False, "files_changed": [], "error": str(e)}
