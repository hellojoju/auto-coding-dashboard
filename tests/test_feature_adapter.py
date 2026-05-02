"""Feature → WorkUnit 适配层测试"""

from unittest.mock import MagicMock

import pytest

from ralph.adapters.feature_adapter import feature_to_work_unit, work_unit_to_feature_status
from ralph.schema.work_unit import WorkUnitStatus


def _make_feature(**overrides) -> MagicMock:
    feature = MagicMock()
    feature.id = overrides.get("id", "feat-1")
    feature.description = overrides.get("description", "实现用户注册")
    feature.category = overrides.get("category", "backend")
    feature.assigned_to = overrides.get("assigned_to", "backend")
    feature.dependencies = overrides.get("dependencies", [])
    feature.status = overrides.get("status", "pending")
    feature.test_steps = overrides.get("test_steps", ["访问页面", "填写表单"])
    return feature


class TestFeatureToWorkUnit:
    def test_basic_conversion(self) -> None:
        feature = _make_feature()
        unit = feature_to_work_unit(feature)
        assert unit.work_id == "feat-1"
        assert unit.title == "实现用户注册"
        assert unit.producer_role == "backend"
        assert unit.status == WorkUnitStatus.DRAFT

    def test_test_steps_to_acceptance_criteria(self) -> None:
        feature = _make_feature(test_steps=["步骤1", "步骤2"])
        unit = feature_to_work_unit(feature)
        assert unit.acceptance_criteria == ["步骤1", "步骤2"]

    def test_category_to_scope_allow(self) -> None:
        feature = _make_feature(category="frontend")
        unit = feature_to_work_unit(feature)
        assert "src/components/" in unit.scope_allow
        assert "src/pages/" in unit.scope_allow

    def test_scope_deny_contains_sensitive_files(self) -> None:
        feature = _make_feature()
        unit = feature_to_work_unit(feature)
        assert ".env" in unit.scope_deny
        assert "*.pem" in unit.scope_deny

    def test_dependencies_preserved(self) -> None:
        feature = _make_feature(dependencies=["feat-0", "feat-pre"])
        unit = feature_to_work_unit(feature)
        assert unit.dependencies == ["feat-0", "feat-pre"]

    def test_harness_created(self) -> None:
        feature = _make_feature()
        unit = feature_to_work_unit(feature)
        assert unit.task_harness is not None
        assert unit.task_harness.harness_id == "harness-feat-1"
        assert unit.task_harness.reviewer_role == "qa"

    def test_status_mapping(self) -> None:
        cases = [
            ("pending", WorkUnitStatus.DRAFT),
            ("in_progress", WorkUnitStatus.RUNNING),
            ("review", WorkUnitStatus.NEEDS_REVIEW),
            ("done", WorkUnitStatus.ACCEPTED),
            ("blocked", WorkUnitStatus.BLOCKED),
        ]
        for feat_status, expected in cases:
            feature = _make_feature(status=feat_status)
            unit = feature_to_work_unit(feature)
            assert unit.status == expected, f"{feat_status} → {expected}"

    def test_unknown_category_default_scope(self) -> None:
        feature = _make_feature(category="unknown")
        unit = feature_to_work_unit(feature)
        assert unit.scope_allow == ["src/"]

    def test_unknown_status_defaults_to_draft(self) -> None:
        feature = _make_feature(status="some_weird_status")
        unit = feature_to_work_unit(feature)
        assert unit.status == WorkUnitStatus.DRAFT


class TestWorkUnitToFeatureStatus:
    def test_all_statuses_mapped(self) -> None:
        for status in WorkUnitStatus:
            result = work_unit_to_feature_status(status)
            assert isinstance(result, str)
            assert result in ["pending", "in_progress", "review", "done", "blocked"]

    def test_accepted_maps_to_done(self) -> None:
        assert work_unit_to_feature_status(WorkUnitStatus.ACCEPTED) == "done"

    def test_running_maps_to_in_progress(self) -> None:
        assert work_unit_to_feature_status(WorkUnitStatus.RUNNING) == "in_progress"
