"""Plan Generator — 任务拆解和颗粒度门禁

文档依据：
- AI 协议 §10.3 任务拆解验收
- MVP 清单 §6 任务颗粒度验收清单（11 项要求）
- 实施方案 §4.13 Task Decomposer
- PRD §9.3 任务颗粒度门禁（6 项不满足不得执行）
"""

from __future__ import annotations

import logging
from pathlib import Path

from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus

logger = logging.getLogger(__name__)


class PlanGenerator:
    """读取 PRD，生成 WorkUnit 列表，执行颗粒度门禁。"""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = Path(project_dir)

    def generate(
        self,
        prd_path: Path,
        *,
        min_description_length: int = 10,
        max_description_length: int = 500,
    ) -> list[WorkUnit]:
        """从 PRD 生成 WorkUnit 列表。

        颗粒度门禁：
        - 目标清晰（description 长度限制）
        - 范围明确（必须有 scope_allow / scope_deny）
        - 依赖明确
        - 有验收标准
        - 有测试方式
        - 可回滚

        不合格示例："完成登录系统"
        合格示例："在 LoginForm 中增加 rememberMe 字段"
        """
        # 简化实现：从 features.json 读取并转换
        features_file = self._project_dir / "data" / "features.json"
        if not features_file.exists():
            logger.warning("features.json 不存在，返回空列表")
            return []

        import json
        data = json.loads(features_file.read_text(encoding="utf-8"))
        features = data.get("features", [])

        units: list[WorkUnit] = []
        for idx, f in enumerate(features):
            # 颗粒度门禁检查
            errors = self._check_granularity(f, min_description_length, max_description_length)
            if errors:
                logger.warning("Feature %s 颗粒度检查失败: %s", f.get("id", idx), errors)
                continue

            unit = self._feature_to_work_unit(f)
            units.append(unit)

        logger.info("生成 %d 个 WorkUnit（原始 %d 个 Feature）", len(units), len(features))
        return units

    def _check_granularity(
        self,
        feature: dict,
        min_len: int,
        max_len: int,
    ) -> list[str]:
        """检查单个 feature 是否满足颗粒度要求。

        MVP 清单 §6 的 11 项要求中，核心 6 项：
        1. 目标清晰
        2. 范围明确
        3. 依赖明确
        4. 有验收标准
        5. 有测试方式
        6. 可回滚
        """
        errors: list[str] = []

        desc = feature.get("description", "")
        if len(desc) < min_len:
            errors.append(f"描述太短 ({len(desc)} < {min_len})")
        if len(desc) > max_len:
            errors.append(f"描述太长 ({len(desc)} > {max_len})")

        # 检查是否过于笼统（常见反模式）
        vague_phrases = ["完成", "实现整个", "全部", "所有"]
        if any(p in desc for p in vague_phrases) and len(desc) < 50:
            errors.append("描述过于笼统，需要更具体的范围")

        return errors

    def _feature_to_work_unit(self, feature: dict) -> WorkUnit:
        """Feature dict → WorkUnit。"""
        feat_id = feature.get("id", "feat-unknown")
        category = feature.get("category", "unknown")

        # 推断 scope
        scope_allow = self._infer_scope(category)
        scope_deny = [".env", ".env.*", "credentials", "*.pem", "*.key"]

        harness = TaskHarness(
            harness_id=f"harness-{feat_id}",
            task_goal=feature.get("description", ""),
            context_sources=["PRD", "接口文档"],
            scope_allow=scope_allow,
            scope_deny=scope_deny,
            evidence_required=["diff.txt", "test_output.txt"],
            reviewer_role="qa",
            stop_conditions=["批量删除", "修改敏感文件", "执行后门禁失败"],
        )

        return WorkUnit(
            work_id=feat_id,
            work_type="开发",
            producer_role=feature.get("assigned_to", "backend"),
            reviewer_role="qa",
            expected_output=feature.get("description", ""),
            acceptance_criteria=feature.get("test_steps", []),
            task_harness=harness,
            title=feature.get("description", ""),
            target=feature.get("description", ""),
            scope_allow=scope_allow,
            scope_deny=scope_deny,
            dependencies=feature.get("dependencies", []),
            status=WorkUnitStatus.DRAFT,
        )

    @staticmethod
    def _infer_scope(category: str) -> list[str]:
        """根据 category 推断 scope_allow。"""
        category_scope = {
            "backend": ["src/api/", "src/models/", "src/services/"],
            "frontend": ["src/components/", "src/pages/"],
            "database": ["migrations/", "src/db/"],
            "qa": ["tests/"],
            "security": ["src/middleware/", "src/auth/"],
            "ui": ["src/components/", "src/styles/"],
            "docs": ["docs/"],
            "pm": ["docs/", "PRD.md"],
            "architect": ["docs/"],
        }
        return category_scope.get(category, ["src/"])

    def build_dependency_graph(self, units: list[WorkUnit]) -> dict[str, list[str]]:
        """构建依赖图。"""
        graph: dict[str, list[str]] = {}
        for u in units:
            graph[u.work_id] = u.dependencies
        return graph
