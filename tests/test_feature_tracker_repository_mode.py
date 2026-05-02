"""FeatureTracker 在 Repository 模式下的行为测试。

验证当 FeatureTracker 传入 repository 参数时，所有读写操作委托给 Repository，
features.json 不再被直接写入。
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from dashboard.models import Feature
from dashboard.state_repository import ProjectStateRepository


@pytest.fixture()
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(base_dir=tmp_path, project_id="test", run_id="r1")


@pytest.fixture()
def features_file(tmp_path: Path) -> Path:
    return tmp_path / "features.json"


def make_feature(id: str, status: str = "pending", priority: str = "P1") -> Feature:
    return Feature(
        id=id,
        category="test",
        description=f"Feature {id}",
        priority=priority,
        assigned_to="backend",
        status=status,
    )


class TestFeatureTrackerRepositoryMode:
    """FeatureTracker 以 repository 模式运行时的测试。"""

    def test_add_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        tracker = FeatureTracker(features_file, repository=repo)
        f = make_feature("f1")
        tracker.add(f)

        assert repo.get_feature("f1") is not None

    def test_bulk_add_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        tracker = FeatureTracker(features_file, repository=repo)
        features = [make_feature(f"f{i}") for i in range(3)]
        tracker.bulk_add(features)

        assert len(repo.list_features()) == 3

    def test_get_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        tracker = FeatureTracker(features_file, repository=repo)
        result = tracker.get("f1")
        assert result is not None
        assert result.id == "f1"

    def test_get_returns_none_for_missing(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        tracker = FeatureTracker(features_file, repository=repo)
        assert tracker.get("nope") is None

    def test_get_next_ready_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1", priority="P1"))
        repo.upsert_feature(make_feature("f0", priority="P0"))
        tracker = FeatureTracker(features_file, repository=repo)
        result = tracker.get_next_ready()
        assert result is not None
        assert result.id == "f0"

    def test_all_features_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        repo.upsert_feature(make_feature("f2"))
        tracker = FeatureTracker(features_file, repository=repo)
        assert len(tracker.all_features()) == 2

    def test_summary_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1", status="pending"))
        repo.upsert_feature(make_feature("f2", status="done"))
        tracker = FeatureTracker(features_file, repository=repo)
        s = tracker.summary()
        assert s["total"] == 2
        assert s["pending"] == 1
        assert s["done"] == 1

    def test_all_done_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1", status="done"))
        repo.upsert_feature(make_feature("f2", status="done"))
        tracker = FeatureTracker(features_file, repository=repo)
        assert tracker.all_done() is True

    def test_all_done_false_when_pending(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1", status="done"))
        repo.upsert_feature(make_feature("f2", status="pending"))
        tracker = FeatureTracker(features_file, repository=repo)
        assert tracker.all_done() is False

    def test_mark_in_progress_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        tracker = FeatureTracker(features_file, repository=repo)
        tracker.mark_in_progress("f1", instance_id="backend-1")
        f = repo.get_feature("f1")
        assert f is not None
        assert f.status == "in_progress"
        assert f.assigned_instance == "backend-1"

    def test_mark_done_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        tracker = FeatureTracker(features_file, repository=repo)
        tracker.mark_done("f1", files_changed=["a.py"])
        f = repo.get_feature("f1")
        assert f is not None
        assert f.status == "done"
        assert f.passes is True
        assert f.files_changed == ["a.py"]

    def test_mark_blocked_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        tracker = FeatureTracker(features_file, repository=repo)
        tracker.mark_blocked("f1", reason="missing env")
        f = repo.get_feature("f1")
        assert f is not None
        assert f.status == "blocked"
        assert "missing env" in f.error_log

    def test_mark_review_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        tracker = FeatureTracker(features_file, repository=repo)
        tracker.mark_review("f1")
        f = repo.get_feature("f1")
        assert f is not None
        assert f.status == "review"

    def test_add_error_delegates_to_repository(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        repo.upsert_feature(make_feature("f1"))
        tracker = FeatureTracker(features_file, repository=repo)
        tracker.add_error("f1", "boom")
        f = repo.get_feature("f1")
        assert f is not None
        assert "boom" in f.error_log

    def test_features_file_not_written_in_repository_mode(
        self, repo: ProjectStateRepository, features_file: Path
    ) -> None:
        from core.feature_tracker import FeatureTracker

        tracker = FeatureTracker(features_file, repository=repo)
        f = make_feature("f1")
        tracker.add(f)
        tracker.mark_in_progress("f1")
        tracker.mark_done("f1")

        # features.json should not have been created or written
        assert not features_file.exists() or features_file.stat().st_size == 0
