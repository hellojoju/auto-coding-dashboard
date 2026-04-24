"""BlockingIssue 追踪器 — 作为一等公民管理阻塞问题"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from dashboard.models import BlockingIssue

if TYPE_CHECKING:
    from dashboard.state_repository import ProjectStateRepository


class BlockingIssueType(StrEnum):
    MISSING_ENV = "missing_env"
    MISSING_CREDENTIALS = "missing_credentials"
    EXTERNAL_SERVICE_DOWN = "external_service_down"
    DEPENDENCY_NOT_MET = "dependency_not_met"
    CODE_ERROR = "code_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"


class BlockingTracker:
    """阻塞问题的高级追踪器，封装 StateRepository 的 issue CRUD。"""

    def __init__(self, repo: ProjectStateRepository) -> None:
        self._repo = repo

    def detect_missing_env(self, feature_id: str, variable: str) -> BlockingIssue:
        """检测缺失环境变量"""
        return self._create_issue(
            issue_type=BlockingIssueType.MISSING_ENV,
            feature_id=feature_id,
            description=f"Missing environment variable: {variable}",
            context={"variable": variable},
            detected_by="agent",
        )

    def detect_dependency_not_met(
        self, feature_id: str, dep_id: str, reason: str
    ) -> BlockingIssue:
        """检测依赖未满足"""
        return self._create_issue(
            issue_type=BlockingIssueType.DEPENDENCY_NOT_MET,
            feature_id=feature_id,
            description=f"Dependency {dep_id} not met: {reason}",
            context={"dependency": dep_id, "reason": reason},
            detected_by="coordinator",
        )

    def detect_code_error(self, feature_id: str, error: str) -> BlockingIssue:
        """检测代码执行错误"""
        return self._create_issue(
            issue_type=BlockingIssueType.CODE_ERROR,
            feature_id=feature_id,
            description=f"Code execution failed: {error}",
            context={"error": error},
            detected_by="agent",
        )

    def resolve_issue(self, issue_id: str, resolution: str) -> bool:
        """解决阻塞问题"""
        return self._repo.resolve_blocking_issue(issue_id, resolution)

    def list_open_issues(self, *, feature_id: str | None = None) -> list[BlockingIssue]:
        """列出所有未解决的阻塞问题"""
        return self._repo.list_blocking_issues(feature_id=feature_id, resolved=False)

    def get_issue(self, issue_id: str) -> BlockingIssue | None:
        """获取单个阻塞问题"""
        return self._repo.get_blocking_issue(issue_id)

    def _create_issue(
        self,
        *,
        issue_type: BlockingIssueType,
        feature_id: str,
        description: str,
        context: dict,
        detected_by: str,
    ) -> BlockingIssue:
        issue = BlockingIssue(
            issue_type=issue_type.value,
            feature_id=feature_id,
            description=description,
            context=context,
            detected_by=detected_by,
        )
        return self._repo.create_blocking_issue(issue)
