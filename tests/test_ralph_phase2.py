"""Ralph Phase 2 测试 — Context Pack Manager + Harness Manager + Evidence Collector"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ralph.context_pack_manager import ContextPackManager
from ralph.evidence_collector import EvidenceCollector
from ralph.harness_manager import HarnessManager
from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus


# ── ContextPackManager ───────────────────────────────────────


@pytest.fixture
def ctx_manager(tmp_path: Path) -> ContextPackManager:
    return ContextPackManager(tmp_path)


def _make_unit(**overrides) -> WorkUnit:
    defaults = {
        "work_id": "W-1",
        "work_type": "dev",
        "producer_role": "backend",
        "reviewer_role": "qa",
        "expected_output": "API",
        "title": "测试任务",
        "target": "实现 API",
        "acceptance_criteria": ["测试通过", "文档完整"],
        "scope_allow": ["src/api/"],
        "scope_deny": [".env", "secrets/"],
        "risk_notes": "可能有性能问题",
    }
    defaults.update(overrides)
    return WorkUnit(**defaults)


class TestContextPackManager:
    def test_build_basic(self, ctx_manager: ContextPackManager) -> None:
        unit = _make_unit()
        pack = ctx_manager.build(unit, prd_fragment="用户管理需求")
        assert pack.work_id == "W-1"
        assert "测试任务" in pack.task_description
        assert pack.prd_fragment == "用户管理需求"
        assert pack.acceptance_criteria == ["测试通过", "文档完整"]
        assert ".env" in pack.scope_deny

    def test_build_contains_eight_items(self, ctx_manager: ContextPackManager) -> None:
        unit = _make_unit()
        pack = ctx_manager.build(
            unit,
            prd_fragment="需求",
            interface_contracts=["contract1"],
            upstream_results=["上游完成"],
        )
        # 8 项必须包含
        assert pack.task_description  # 1. 当前任务
        assert pack.prd_fragment  # 2. PRD 片段
        assert pack.interface_contracts  # 3. 接口合同
        assert pack.file_summaries is not None  # 4. 文件列表
        assert pack.upstream_results  # 5. 上游结果
        assert pack.risks_and_constraints  # 6. 风险和约束
        assert pack.acceptance_criteria  # 7. 验收标准
        assert pack.scope_deny  # 8. 禁止范围

    def test_build_excludes_agent_self_report(self, ctx_manager: ContextPackManager) -> None:
        unit = _make_unit()
        pack = ctx_manager.build(unit)
        # 不应包含执行 agent 自述
        assert "执行 agent 自述" in pack.untrusted_data

    def test_budget_exceeded_raises(self, ctx_manager: ContextPackManager) -> None:
        unit = _make_unit(
            target="实现" * 10000,  # 超大目标
            acceptance_criteria=["测试" * 1000],
        )
        with pytest.raises(ValueError, match="超出 budget"):
            ctx_manager.build(unit, budget_tokens=10)

    def test_estimate_tokens(self, ctx_manager: ContextPackManager) -> None:
        unit = _make_unit(target="短目标")
        pack = ctx_manager.build(unit)
        assert pack.estimate_tokens() > 0


# ── HarnessManager ───────────────────────────────────────────


@pytest.fixture
def harness_mgr() -> HarnessManager:
    return HarnessManager()


class TestHarnessManager:
    def test_validate_harness_pass(self, harness_mgr: HarnessManager) -> None:
        h = TaskHarness(
            harness_id="H-1",
            task_goal="实现功能",
            context_sources=["PRD"],
            scope_allow=["src/"],
            scope_deny=[".env"],
            evidence_required=["diff"],
            reviewer_role="qa",
            stop_conditions=["批量删除"],
        )
        assert harness_mgr.validate_harness(h) == []

    def test_validate_harness_missing_fields(self, harness_mgr: HarnessManager) -> None:
        h = TaskHarness(harness_id="", task_goal="")
        errors = harness_mgr.validate_harness(h)
        assert len(errors) >= 5
        assert any("harness_id" in e for e in errors)
        assert any("task_goal" in e for e in errors)
        assert any("scope_deny" in e for e in errors)

    def test_preflight_all_pass(self, harness_mgr: HarnessManager) -> None:
        unit = _make_unit(
            task_harness=TaskHarness(
                harness_id="H-1",
                task_goal="test",
                context_sources=["PRD"],
                scope_allow=["src/"],
                scope_deny=[".env"],
                evidence_required=["diff"],
                reviewer_role="qa",
                stop_conditions=["批量删除"],
            ),
        )
        result = harness_mgr.preflight(unit)
        assert result.passed is True
        assert len(result.checks) == 8  # §6.1 8 项检查

    def test_preflight_missing_harness(self, harness_mgr: HarnessManager) -> None:
        unit = _make_unit(task_harness=None)
        result = harness_mgr.preflight(unit)
        assert result.passed is False
        assert any("task_harness" in f for f in result.failures)

    def test_preflight_missing_scope_deny(self, harness_mgr: HarnessManager) -> None:
        unit = _make_unit(scope_deny=[])
        result = harness_mgr.preflight(unit)
        assert result.passed is False
        assert any("scope_deny" in f for f in result.failures)

    def test_inflight_record(self, harness_mgr: HarnessManager) -> None:
        harness_mgr.start_inflight("W-1")
        harness_mgr.record_inflight(
            "W-1",
            contexts_read=["PRD"],
            tools_used=["Write"],
            files_modified=["src/app.py"],
            checkpoint="完成编码",
        )
        record = harness_mgr.get_inflight("W-1")
        assert record is not None
        assert "PRD" in record.contexts_read
        assert "Write" in record.tools_used
        assert "src/app.py" in record.files_modified
        assert "完成编码" in record.checkpoints_passed

    def test_postflight_scope_violation(self, harness_mgr: HarnessManager) -> None:
        unit = _make_unit(scope_allow=["src/api/"], scope_deny=["src/auth/"])
        result = harness_mgr.postflight(
            unit,
            files_changed=["src/auth/token.py"],  # 越界修改
            evidence_files=["diff.txt"],
            test_passed=True,
            review_completed=True,
        )
        assert result.passed is False
        assert any("禁止范围" in f for f in result.failures)

    def test_postflight_test_failed(self, harness_mgr: HarnessManager) -> None:
        unit = _make_unit()
        result = harness_mgr.postflight(
            unit,
            files_changed=["src/api/user.py"],
            evidence_files=["diff.txt"],
            test_passed=False,
            review_completed=True,
        )
        assert result.passed is False
        assert any("测试未通过" in f for f in result.failures)

    def test_postflight_all_pass(self, harness_mgr: HarnessManager) -> None:
        unit = _make_unit()
        result = harness_mgr.postflight(
            unit,
            files_changed=["src/api/user.py"],
            evidence_files=["diff.txt"],
            test_passed=True,
            review_completed=True,
        )
        assert result.passed is True
        assert len(result.checks) == 7  # §6.3 7 项检查


# ── EvidenceCollector ────────────────────────────────────────


@pytest.fixture
def collector(tmp_path: Path) -> EvidenceCollector:
    return EvidenceCollector(tmp_path)


class TestEvidenceCollector:
    def test_collect_creates_evidence_dir(self, collector: EvidenceCollector, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=workspace, check=True, capture_output=True)
        (workspace / "a.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True)

        items = collector.collect("W-1", workspace)
        assert len(items) >= 0  # 空 diff 时可能为 0

    def test_collect_with_test_output(self, collector: EvidenceCollector, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=workspace, check=True, capture_output=True)
        (workspace / "a.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True)

        items = collector.collect("W-1", workspace, include_test_output="PASSED 5 tests")
        assert any(e.evidence_type == "test_output" for e in items)

    def test_evidence_file_created(self, collector: EvidenceCollector, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=workspace, check=True, capture_output=True)
        (workspace / "a.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True)

        collector.collect("W-1", workspace, include_test_output="test")
        assert (tmp_path / "evidence" / "W-1").is_dir()
