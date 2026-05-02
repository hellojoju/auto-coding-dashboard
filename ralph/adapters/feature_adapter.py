"""Feature → WorkUnit 适配层

文档依据：
- 实施方案 §6 "保留和加强" — 现有 Feature 模型要能过渡到 WorkUnit
- jiaojie.md §7 "后续开发应从哪里开始" — 基于 auto-coding 开始制定重构任务

职责：
- Feature → WorkUnit 转换
- WorkUnit → Feature 回写（状态同步）
- 不破坏现有 FeatureTracker 功能
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus

if TYPE_CHECKING:
    from core.feature_tracker import Feature


# Feature.status → WorkUnitStatus 映射
_FEATURE_STATUS_MAP: dict[str, WorkUnitStatus] = {
    "pending": WorkUnitStatus.DRAFT,
    "in_progress": WorkUnitStatus.RUNNING,
    "review": WorkUnitStatus.NEEDS_REVIEW,
    "done": WorkUnitStatus.ACCEPTED,
    "blocked": WorkUnitStatus.BLOCKED,
}

# WorkUnitStatus → Feature.status 反向映射
_WORKUNIT_STATUS_MAP: dict[WorkUnitStatus, str] = {
    WorkUnitStatus.DRAFT: "pending",
    WorkUnitStatus.READY: "pending",
    WorkUnitStatus.RUNNING: "in_progress",
    WorkUnitStatus.NEEDS_REVIEW: "review",
    WorkUnitStatus.FAILED: "blocked",
    WorkUnitStatus.NEEDS_REWORK: "review",
    WorkUnitStatus.BLOCKED: "blocked",
    WorkUnitStatus.ACCEPTED: "done",
}

# Feature.category → scope_allow 推断
_CATEGORY_SCOPE_MAP: dict[str, list[str]] = {
    "backend": ["src/api/", "src/models/", "src/services/"],
    "frontend": ["src/components/", "src/pages/", "src/views/"],
    "database": ["migrations/", "src/models/", "src/db/"],
    "qa": ["tests/", "test/"],
    "security": ["src/middleware/", "src/auth/", "src/validators/"],
    "ui": ["src/components/", "src/styles/", "public/"],
    "docs": ["docs/", "README.md"],
    "pm": ["docs/", "PRD.md"],
    "architect": ["docs/"],
}


def feature_to_work_unit(feature: Feature) -> WorkUnit:
    """Feature → WorkUnit 转换。

    - test_steps → acceptance_criteria
    - category → scope_allow 推断
    - status 映射到 WorkUnitStatus
    """
    # 推断 scope_allow
    scope_allow = _CATEGORY_SCOPE_MAP.get(feature.category, ["src/"])

    # 推断 scope_deny（默认禁止修改敏感文件）
    scope_deny = [".env", ".env.*", "credentials", "*.pem", "*.key"]

    # 状态映射
    status = _FEATURE_STATUS_MAP.get(feature.status, WorkUnitStatus.DRAFT)

    # 构造 TaskHarness（最小化，后续由 HarnessManager 补全）
    harness = TaskHarness(
        harness_id=f"harness-{feature.id}",
        task_goal=feature.description,
        scope_allow=scope_allow,
        scope_deny=scope_deny,
        evidence_required=["diff.txt", "test_output.txt"],
        reviewer_role="qa",
        stop_conditions=["批量删除", "修改敏感文件"],
    )

    return WorkUnit(
        work_id=feature.id,
        work_type="开发",
        producer_role=feature.assigned_to or "backend",
        reviewer_role="qa",
        expected_output=feature.description,
        acceptance_criteria=feature.test_steps or [],
        task_harness=harness,
        title=feature.description,
        background="",
        target=feature.description,
        scope_allow=scope_allow,
        scope_deny=scope_deny,
        dependencies=feature.dependencies or [],
        test_command="",
        rollback_strategy="git revert",
        status=status,
    )


def work_unit_to_feature_status(status: WorkUnitStatus) -> str:
    """WorkUnitStatus → Feature.status 字符串。"""
    return _WORKUNIT_STATUS_MAP.get(status, "pending")
