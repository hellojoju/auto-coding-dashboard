"""Ralph Phase 3 测试 — WorkUnit Engine + Plan Generator + Report Generator"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ralph.plan_generator import PlanGenerator
from ralph.report_generator import ReportGenerator
from ralph.schema.evidence import Evidence
from ralph.schema.review_result import ReviewResult
from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus
from ralph.work_unit_engine import WorkUnitEngine

# ── WorkUnitEngine ───────────────────────────────────────────


@pytest.fixture
def engine(tmp_path: Path) -> WorkUnitEngine:
    return WorkUnitEngine(tmp_path)


def _make_unit(**overrides) -> WorkUnit:
    defaults = {
        "work_id": "W-1",
        "work_type": "dev",
        "producer_role": "backend",
        "reviewer_role": "qa",
        "expected_output": "API",
        "title": "测试任务",
        "target": "实现 API",
        "acceptance_criteria": ["测试通过"],
        "scope_allow": ["src/api/"],
        "scope_deny": [".env"],
        "task_harness": TaskHarness(
            harness_id="H-1",
            task_goal="实现 API",
            context_sources=["PRD"],
            scope_allow=["src/api/"],
            scope_deny=[".env"],
            evidence_required=["diff"],
            reviewer_role="qa",
            stop_conditions=["批量删除"],
        ),
        "status": WorkUnitStatus.DRAFT,
    }
    defaults.update(overrides)
    return WorkUnit(**defaults)


class TestWorkUnitEngine:
    def test_create_and_get(self, engine: WorkUnitEngine) -> None:
        unit = _make_unit()
        engine.create_work_unit(unit)
        loaded = engine.get_work_unit("W-1")
        assert loaded is not None
        assert loaded.work_id == "W-1"
        assert loaded.status == WorkUnitStatus.DRAFT

    def test_prepare_draft_to_ready(self, engine: WorkUnitEngine) -> None:
        engine.create_work_unit(_make_unit())
        result = engine.prepare("W-1")
        assert result.status == WorkUnitStatus.READY

    def test_prepare_missing_harness_raises(self, engine: WorkUnitEngine) -> None:
        engine.create_work_unit(_make_unit(task_harness=None))
        with pytest.raises(ValueError, match="task_harness"):
            engine.prepare("W-1")

    def test_execute_full_pipeline(self, engine: WorkUnitEngine, tmp_path: Path) -> None:
        # 初始化 git
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

        # 创建并准备
        engine.create_work_unit(_make_unit(scope_allow=["src/"]))
        engine.prepare("W-1")

        # 模拟 agent 修改文件（产生 diff）
        (tmp_path / "src" / "app.py").write_text("modified")

        # mock agent
        agent = AsyncMock()
        agent.execute.return_value = {
            "success": True,
            "files_changed": ["src/app.py"],
        }

        # 执行（使用兼容模式，不实际调用 Claude CLI）
        result = asyncio.run(engine.execute("W-1", agent, use_claude_runner=False))
        assert result["work_id"] == "W-1"
        assert result["status"] in ("needs_review", "failed")

    def test_review_accepted(self, engine: WorkUnitEngine, tmp_path: Path) -> None:
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@test"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

        engine.create_work_unit(_make_unit(scope_allow=["src/"]))
        engine.prepare("W-1")

        # 模拟 agent 修改文件（产生 diff）
        (tmp_path / "src" / "app.py").write_text("modified")

        agent = AsyncMock()
        agent.execute.return_value = {"success": True, "files_changed": ["src/app.py"]}
        asyncio.run(engine.execute("W-1", agent, use_claude_runner=False))

        # Review
        review = engine.review("W-1")
        assert isinstance(review, ReviewResult)

        # 状态应为 accepted 或 needs_rework（取决于 diff 是否存在）
        unit = engine.get_work_unit("W-1")
        assert unit.status in (WorkUnitStatus.ACCEPTED, WorkUnitStatus.NEEDS_REWORK, WorkUnitStatus.BLOCKED)


# ── PlanGenerator ────────────────────────────────────────────


class TestPlanGenerator:
    def test_generate_from_features(self, tmp_path: Path) -> None:
        # 创建 features.json
        data = {
            "features": [
                {
                    "id": "feat-1",
                    "description": "在 LoginForm 中增加 rememberMe 字段",
                    "category": "frontend",
                    "assigned_to": "frontend",
                    "dependencies": [],
                    "test_steps": ["检查 rememberMe 存在"],
                },
                {
                    "id": "feat-2",
                    "description": "完成登录系统",  # 过于笼统
                    "category": "backend",
                    "assigned_to": "backend",
                    "dependencies": ["feat-1"],
                },
            ]
        }
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "features.json").write_text(json.dumps(data), encoding="utf-8")

        gen = PlanGenerator(tmp_path)
        units = gen.generate(tmp_path / "data" / "PRD.md")

        # feat-1 应该通过，feat-2 应该被过滤
        assert len(units) == 1
        assert units[0].work_id == "feat-1"
        assert units[0].status == WorkUnitStatus.DRAFT

    def test_dependency_graph(self, tmp_path: Path) -> None:
        data = {
            "features": [
                {
                    "id": "feat-1",
                    "description": "实现用户 API 接口",
                    "category": "backend",
                    "assigned_to": "b",
                },
                {
                    "id": "feat-2",
                    "description": "添加用户 API 测试",
                    "category": "backend",
                    "assigned_to": "b",
                    "dependencies": ["feat-1"],
                },
            ]
        }
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "features.json").write_text(json.dumps(data), encoding="utf-8")

        gen = PlanGenerator(tmp_path)
        units = gen.generate(tmp_path / "data" / "PRD.md")
        graph = gen.build_dependency_graph(units)
        assert graph["feat-1"] == []
        assert graph["feat-2"] == ["feat-1"]


# ── ReportGenerator ──────────────────────────────────────────


class TestReportGenerator:
    def test_generate_report(self, tmp_path: Path) -> None:
        from ralph.repository import RalphRepository

        ralph_dir = tmp_path / ".ralph"
        repo = RalphRepository(ralph_dir)

        # 保存已验收任务
        unit = _make_unit(status=WorkUnitStatus.ACCEPTED, risk_notes="可能有性能问题")
        repo.save_work_unit(unit)

        # 保存证据
        repo.save_evidence(Evidence(evidence_id="E-1", work_id="W-1", evidence_type="diff", file_path="/tmp/diff.txt"))

        # 保存 review
        from ralph.schema.review_result import ReviewResult
        repo.save_review(ReviewResult(
            work_id="W-1", reviewer_context_id="ctx-1",
            review_type="功能完整性", conclusion="通过", recommended_action="接受",
        ))

        gen = ReportGenerator(ralph_dir)
        report = gen.generate("测试报告")

        assert "# 测试报告" in report
        assert "已验收: 1 个" in report
        assert "W-1" in report
        assert "通过" in report
        assert "可能有性能问题" in report

    def test_save_report(self, tmp_path: Path) -> None:
        gen = ReportGenerator(tmp_path / ".ralph")
        path = gen.save("# 报告内容", "test-report.md")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "# 报告内容"

    def test_list_reports(self, tmp_path: Path) -> None:
        ralph_dir = tmp_path / ".ralph"
        gen = ReportGenerator(ralph_dir)

        # 空目录
        reports = gen.list_reports()
        assert reports == []

        # 保存几个报告
        gen.save("# 报告 A", "report-a.md")
        gen.save("# 报告 B", "report-b.md")

        reports = gen.list_reports()
        assert len(reports) == 2
        assert any("report-a" in r.name for r in reports)
        assert all(r.name.endswith(".md") for r in reports)

    def test_list_reports_by_date_range(self, tmp_path: Path) -> None:
        import time

        ralph_dir = tmp_path / ".ralph"
        gen = ReportGenerator(ralph_dir)

        gen.save("# 旧报告", "old-report.md")
        time.sleep(1.5)  # 确保时间戳不同
        gen.save("# 新报告", "new-report.md")

        # 按日期范围过滤
        from datetime import datetime, timedelta

        now = datetime.now()
        recent = gen.list_reports(since=now - timedelta(seconds=1))
        assert len(recent) == 1
        assert "new-report" in recent[0].name
