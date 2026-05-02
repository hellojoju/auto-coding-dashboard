"""ProjectStateRepository Feature 查询方法测试。"""

import json
import tempfile
from pathlib import Path

import pytest

from dashboard.models import Feature
from dashboard.state_repository import ProjectStateRepository


@pytest.fixture()
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(base_dir=tmp_path, project_id="test", run_id="r1")


def make_feature(id: str, status: str = "pending", priority: str = "P1", deps: list[str] | None = None) -> Feature:
    return Feature(
        id=id,
        category="test",
        description=f"Feature {id}",
        priority=priority,
        assigned_to="backend",
        status=status,
        dependencies=deps or [],
    )


class TestGetFeature:
    def test_returns_existing_feature(self, repo: ProjectStateRepository) -> None:
        f = make_feature("f1")
        repo.upsert_feature(f)
        result = repo.get_feature("f1")
        assert result is not None
        assert result.id == "f1"
        assert result.description == "Feature f1"

    def test_returns_none_for_missing_feature(self, repo: ProjectStateRepository) -> None:
        assert repo.get_feature("nope") is None


class TestListFeatures:
    def test_lists_all_features(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1"))
        repo.upsert_feature(make_feature("f2"))
        assert len(repo.list_features()) == 2

    def test_filters_by_status(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="pending"))
        repo.upsert_feature(make_feature("f2", status="done"))
        repo.upsert_feature(make_feature("f3", status="pending"))
        pending = repo.list_features(status="pending")
        assert len(pending) == 2
        ids = {f.id for f in pending}
        assert ids == {"f1", "f3"}

    def test_empty_when_no_features(self, repo: ProjectStateRepository) -> None:
        assert repo.list_features() == []


class TestGetNextReadyFeature:
    def test_returns_highest_priority_ready(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", priority="P2", deps=[]))
        repo.upsert_feature(make_feature("f0", priority="P0", deps=[]))
        repo.upsert_feature(make_feature("f2", priority="P1", deps=[]))
        next_f = repo.get_next_ready_feature()
        assert next_f is not None
        assert next_f.id == "f0"

    def test_skips_non_pending(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="in_progress"))
        repo.upsert_feature(make_feature("f2", status="done"))
        assert repo.get_next_ready_feature() is None

    def test_skips_unmet_dependencies(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="pending"))
        repo.upsert_feature(make_feature("f2", deps=["f1"]))
        next_f = repo.get_next_ready_feature()
        assert next_f is not None
        assert next_f.id == "f1"

    def test_returns_when_deps_met(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="done"))
        repo.upsert_feature(make_feature("f2", deps=["f1"]))
        next_f = repo.get_next_ready_feature()
        assert next_f is not None
        assert next_f.id == "f2"

    def test_returns_none_when_no_candidates(self, repo: ProjectStateRepository) -> None:
        assert repo.get_next_ready_feature() is None


class TestFeatureSummary:
    def test_correct_counts(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="pending"))
        repo.upsert_feature(make_feature("f2", status="in_progress"))
        repo.upsert_feature(make_feature("f3", status="done"))
        repo.upsert_feature(make_feature("f4", status="blocked"))
        s = repo.feature_summary()
        assert s["total"] == 4
        assert s["pending"] == 1
        assert s["in_progress"] == 1
        assert s["done"] == 1
        assert s["blocked"] == 1

    def test_passing_count(self, repo: ProjectStateRepository) -> None:
        f1 = make_feature("f1", status="done")
        f1.passes = True
        repo.upsert_feature(f1)
        f2 = make_feature("f2", status="done")
        f2.passes = False
        repo.upsert_feature(f2)
        s = repo.feature_summary()
        assert s["passing"] == 1

    def test_empty_summary(self, repo: ProjectStateRepository) -> None:
        s = repo.feature_summary()
        assert s["total"] == 0


class TestAllFeaturesDone:
    def test_true_when_all_done(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="done"))
        repo.upsert_feature(make_feature("f2", status="done"))
        assert repo.all_features_done() is True

    def test_false_when_some_pending(self, repo: ProjectStateRepository) -> None:
        repo.upsert_feature(make_feature("f1", status="done"))
        repo.upsert_feature(make_feature("f2", status="pending"))
        assert repo.all_features_done() is False

    def test_false_when_empty(self, repo: ProjectStateRepository) -> None:
        assert repo.all_features_done() is False
