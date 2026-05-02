"""测试 BlockingTracker"""
import pytest

from core.blocking_tracker import BlockingIssueType, BlockingTracker


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    from dashboard.state_repository import ProjectStateRepository
    repo = ProjectStateRepository(base_dir=tmp_path, project_id="test")
    return BlockingTracker(repo)


def test_detect_missing_env(tracker):
    issue = tracker.detect_missing_env("feat-1", "OPENAI_API_KEY")
    assert issue is not None
    assert issue.issue_type == BlockingIssueType.MISSING_ENV.value
    assert issue.feature_id == "feat-1"


def test_detect_dependency_not_met(tracker):
    issue = tracker.detect_dependency_not_met("feat-1", "feat-0", "feat-0 is blocked")
    assert issue is not None
    assert issue.issue_type == BlockingIssueType.DEPENDENCY_NOT_MET.value


def test_resolve_issue(tracker):
    issue = tracker.detect_missing_env("feat-1", "API_KEY")
    assert tracker.resolve_issue(issue.issue_id, "Added key to .env") is True

    remaining = tracker.list_open_issues()
    assert len(remaining) == 0


def test_list_open_issues(tracker):
    tracker.detect_missing_env("feat-1", "KEY_A")
    tracker.detect_missing_env("feat-2", "KEY_B")
    tracker.detect_missing_env("feat-3", "KEY_C")

    issues = tracker.list_open_issues()
    assert len(issues) == 3

    # 解决一个后只剩两个
    tracker.resolve_issue(issues[0].issue_id, "Fixed")
    assert len(tracker.list_open_issues()) == 2
