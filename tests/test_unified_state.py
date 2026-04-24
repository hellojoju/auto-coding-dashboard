"""测试 StateRepository 的 BlockingIssue 功能"""

import pytest

from dashboard.models import BlockingIssue
from dashboard.state_repository import ProjectStateRepository


@pytest.fixture
def repo(tmp_path):
    return ProjectStateRepository(base_dir=tmp_path, project_id="test-project")


def test_create_blocking_issue(repo):
    issue = BlockingIssue(
        feature_id="feat-1",
        issue_type="missing_env",
        detected_by="agent",
        description="Missing OPENAI_API_KEY",
    )
    saved = repo.create_blocking_issue(issue)
    assert saved.issue_id != ""

    retrieved = repo.get_blocking_issue(saved.issue_id)
    assert retrieved is not None
    assert retrieved.feature_id == "feat-1"
    assert retrieved.resolved is False


def test_resolve_blocking_issue(repo):
    issue = BlockingIssue(
        feature_id="feat-1",
        issue_type="missing_env",
        detected_by="agent",
        description="Missing key",
    )
    saved = repo.create_blocking_issue(issue)
    assert repo.resolve_blocking_issue(saved.issue_id, "Added to .env") is True

    resolved = repo.get_blocking_issue(saved.issue_id)
    assert resolved.resolved is True
    assert resolved.resolution == "Added to .env"


def test_list_blocking_issues_filtering(repo):
    issue1 = repo.create_blocking_issue(BlockingIssue(
        feature_id="feat-1", issue_type="missing_env", detected_by="agent", description="Missing key"
    ))
    _ = repo.create_blocking_issue(BlockingIssue(
        feature_id="feat-2", issue_type="dependency_not_met", detected_by="coordinator", description="Dep not met"
    ))

    all_issues = repo.list_blocking_issues()
    assert len(all_issues) == 2

    feat1_issues = repo.list_blocking_issues(feature_id="feat-1")
    assert len(feat1_issues) == 1

    repo.resolve_blocking_issue(issue1.issue_id, "Fixed")
    unresolved = repo.list_blocking_issues(resolved=False)
    assert len(unresolved) == 1


def test_blocking_issue_persistence(repo):
    """重启 repository 后 blocking_issues 仍然可恢复。"""
    issue = BlockingIssue(
        feature_id="feat-1",
        issue_type="external_service_down",
        detected_by="verification",
        description="API is down",
    )
    saved = repo.create_blocking_issue(issue)

    # 新建一个 repository 实例，从磁盘恢复
    repo2 = ProjectStateRepository(base_dir=repo._base, project_id="test-project")
    restored = repo2.get_blocking_issue(saved.issue_id)
    assert restored is not None
    assert restored.feature_id == "feat-1"
    assert restored.issue_type == "external_service_down"


def test_blocking_issue_to_dict_and_from_dict():
    issue = BlockingIssue(
        issue_id="issue-001",
        issue_type="code_error",
        feature_id="feat-1",
        detected_by="coordinator",
        description="Test error",
        context={"error": "ValueError"},
        resolved=False,
    )
    d = issue.to_dict()
    assert d["issue_id"] == "issue-001"
    assert d["context"] == {"error": "ValueError"}

    restored = BlockingIssue.from_dict(d)
    assert restored.issue_id == "issue-001"
    assert restored.feature_id == "feat-1"


def test_feature_has_blocking_issues(repo):
    """Feature 上的 blocking_issues 字段可持久化。"""
    from dashboard.models import Feature
    feature = Feature(
        id="feat-1",
        category="backend",
        description="Add user auth",
        blocking_issues=["issue-001", "issue-002"],
    )
    saved = repo.upsert_feature(feature)
    assert saved.blocking_issues == ["issue-001", "issue-002"]

    # 从磁盘恢复
    repo2 = ProjectStateRepository(base_dir=repo._base, project_id="test-project")
    restored = repo2.get_features_by_workspace("")
    assert len(restored) == 1
    assert restored[0].blocking_issues == ["issue-001", "issue-002"]


def test_load_snapshot_includes_blocking_issues(repo):
    """load_snapshot 返回的 Snapshot 应包含 blocking_issues。"""
    from dashboard.models import BlockingIssue
    issue = BlockingIssue(
        feature_id="feat-1",
        issue_type="resource_exhausted",
        detected_by="agent",
        description="Out of memory",
    )
    repo.create_blocking_issue(issue)

    snapshot = repo.load_snapshot()
    assert len(snapshot.blocking_issues) == 1
    assert snapshot.blocking_issues[0].feature_id == "feat-1"
