"""自举验证 — Ralph 系统完整闭环测试

文档依据：
- 实施方案 §5.1 阶段一必须实现的 6-12 项
- MVP 清单 §13 MVP 完成定义
- 计划 3.4 自举验证

目标：用一个实际的 Ralph 改进任务验证完整闭环：
  harness → 执行 → 证据 → review → 报告
"""

import asyncio
import subprocess
from pathlib import Path

import pytest

from ralph.claude_runner import ExecutionResult
from ralph.report_generator import ReportGenerator
from ralph.repository import RalphRepository
from ralph.schema.task_harness import TaskHarness
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus
from ralph.work_unit_engine import WorkUnitEngine


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """初始化一个带 git 的临时项目目录。"""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ralph@test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Ralph"], cwd=tmp_path, check=True, capture_output=True)

    # 创建基本项目结构
    (tmp_path / "ralph").mkdir()
    (tmp_path / "ralph" / "__init__.py").write_text("")
    (tmp_path / "ralph" / "test_module.py").write_text('"""测试模块"""\n\ndef hello() -> str:\n    return "hello"\n')
    (tmp_path / "ralph" / "state_machine.py").write_text('"""状态机"""\n')

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    return tmp_path


@pytest.fixture
def engine(project_dir: Path) -> WorkUnitEngine:
    return WorkUnitEngine(project_dir)


def _make_harness() -> TaskHarness:
    return TaskHarness(
        harness_id="H-bootstrap",
        task_goal="为 ralph/test_module.py 增加 goodbye 函数",
        context_sources=["PRD"],
        scope_allow=["ralph/test_module.py"],
        scope_deny=[".env", "*.key"],
        evidence_required=["diff.txt", "files_changed.txt", "test_output.txt"],
        reviewer_role="qa",
        stop_conditions=["批量删除", "修改 .env"],
    )


def _make_work_unit(work_id: str = "W-bootstrap-1") -> WorkUnit:
    return WorkUnit(
        work_id=work_id,
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="ralph/test_module.py 增加 goodbye 函数及测试",
        acceptance_criteria=[
            "goodbye 函数存在",
            "返回 'goodbye' 字符串",
            "有对应的单元测试",
        ],
        task_harness=_make_harness(),
        title="为 test_module 增加 goodbye 函数",
        target="在 ralph/test_module.py 中增加 goodbye() 函数，返回 'goodbye'",
        scope_allow=["ralph/test_module.py", "ralph/"],
        scope_deny=[".env", "*.key"],
        status=WorkUnitStatus.DRAFT,
    )


class TestBootstrapVerification:
    """任务 3.4 自举验证 — 完整闭环测试。"""

    def test_full_pipeline_with_mock_claude_runner(self, engine: WorkUnitEngine, project_dir: Path) -> None:
        """完整流程：create → prepare → execute → review → report。

        使用 mock Claude runner 模拟执行结果，验证各模块串联正确。
        """
        # 1. 创建 WorkUnit
        unit = _make_work_unit()
        engine.create_work_unit(unit)
        assert engine.get_work_unit("W-bootstrap-1") is not None

        # 2. 准备（draft → ready）
        result = engine.prepare("W-bootstrap-1")
        assert result.status == WorkUnitStatus.READY

        # 3. 模拟 Claude runner 执行（添加 goodbye 函数）
        target_file = project_dir / "ralph" / "test_module.py"
        original_content = target_file.read_text()
        new_content = original_content + '\n\ndef goodbye() -> str:\n    return "goodbye"\n'
        target_file.write_text(new_content)

        # mock Claude runner
        def mock_execute(**kwargs):
            return ExecutionResult(
                work_id="W-bootstrap-1",
                success=True,
                stdout="done",
                stderr="",
                files_created=["ralph/test_test_module.py"],
                files_modified=["ralph/test_module.py"],
                files_deleted=[],
                test_results={"test_goodbye": "pass"},
            )

        engine._runner.execute = mock_execute

        # 4. 执行（ready → running → needs_review）
        exec_result = asyncio.run(engine.execute("W-bootstrap-1", use_claude_runner=True))
        assert exec_result["success"] is True
        assert exec_result["status"] == "needs_review"
        assert "ralph/test_module.py" in exec_result["files_changed"]

        unit = engine.get_work_unit("W-bootstrap-1")
        assert unit.status == WorkUnitStatus.NEEDS_REVIEW

        # 5. 独立审查（needs_review → accepted）
        review = engine.review("W-bootstrap-1")
        assert review.conclusion in ("通过", "不通过")

        unit = engine.get_work_unit("W-bootstrap-1")
        assert unit.status == WorkUnitStatus.ACCEPTED

        # 6. 生成报告
        ralph_dir = project_dir / ".ralph"
        gen = ReportGenerator(ralph_dir)
        report = gen.generate("自举验证报告")

        assert "# 自举验证报告" in report
        assert "已验收: 1 个" in report
        assert "W-bootstrap-1" in report

        # 7. 保存报告
        path = gen.save(report, "bootstrap-report.md")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == report

    def test_full_pipeline_with_real_git_diff(self, engine: WorkUnitEngine, project_dir: Path) -> None:
        """使用真实 git diff 验证证据收集链路。

        不调用 Claude runner，直接修改文件并提交，验证引擎能正确收集证据。
        """
        # 创建并准备
        unit = _make_work_unit(work_id="W-bootstrap-2")
        engine.create_work_unit(unit)
        engine.prepare("W-bootstrap-2")

        # 直接修改文件
        target_file = project_dir / "ralph" / "test_module.py"
        new_content = target_file.read_text() + '\n\ndef goodbye() -> str:\n    return "goodbye"\n'
        target_file.write_text(new_content)

        # mock runner
        def mock_execute(**kwargs):
            return ExecutionResult(
                work_id="W-bootstrap-2",
                success=True,
                stdout="done",
                stderr="",
                files_created=[],
                files_modified=["ralph/test_module.py"],
                files_deleted=[],
                test_results={"test_goodbye": "pass"},
            )

        engine._runner.execute = mock_execute

        # 执行
        exec_result = asyncio.run(engine.execute("W-bootstrap-2", use_claude_runner=True))
        assert exec_result["success"] is True
        assert exec_result["status"] == "needs_review"

        # 验证 evidence 已收集
        repo = RalphRepository(project_dir / ".ralph")
        evidence = repo.list_evidence("W-bootstrap-2")
        assert len(evidence) > 0

        # 验证 evidence 包含必要类型
        evidence_types = {e.evidence_type for e in evidence}
        assert "diff" in evidence_types

        # 审查
        engine.review("W-bootstrap-2")
        unit = engine.get_work_unit("W-bootstrap-2")
        assert unit.status in (WorkUnitStatus.ACCEPTED, WorkUnitStatus.NEEDS_REWORK, WorkUnitStatus.BLOCKED)

    def test_failed_execution_transitions_to_failed(self, engine: WorkUnitEngine, project_dir: Path) -> None:
        """执行失败时状态应正确流转到 failed。"""
        unit = _make_work_unit(work_id="W-bootstrap-3")
        engine.create_work_unit(unit)
        engine.prepare("W-bootstrap-3")

        # mock 失败执行
        def mock_execute(**kwargs):
            return ExecutionResult(
                work_id="W-bootstrap-3",
                success=False,
                stdout="",
                stderr="error: something went wrong",
                files_created=[],
                files_modified=[],
                files_deleted=[],
                test_results={},
                error="执行出错",
            )

        engine._runner.execute = mock_execute

        exec_result = asyncio.run(engine.execute("W-bootstrap-3", use_claude_runner=True))
        assert exec_result["success"] is False
        assert exec_result["status"] == "failed"

        unit = engine.get_work_unit("W-bootstrap-3")
        assert unit.status == WorkUnitStatus.FAILED

    def test_blocked_execution_transitions_to_blocked(self, engine: WorkUnitEngine, project_dir: Path) -> None:
        """执行前门禁失败时应流转到 blocked。"""
        # 创建没有 scope_allow 的 WorkUnit（preflight 会失败）
        unit = WorkUnit(
            work_id="W-bootstrap-4",
            work_type="开发",
            producer_role="backend",
            reviewer_role="qa",
            expected_output="test",
            acceptance_criteria=["pass"],
            task_harness=_make_harness(),
            title="空 scope 任务",
            target="test",
            scope_allow=[],  # 空 scope
            scope_deny=[".env"],
            status=WorkUnitStatus.DRAFT,
        )
        engine.create_work_unit(unit)
        engine.prepare("W-bootstrap-4")

        # 任何执行都会被拦截（因为 scope 为空）
        def mock_execute(**kwargs):
            return ExecutionResult(
                work_id="W-bootstrap-4",
                success=True,
                stdout="",
                stderr="",
                files_created=[],
                files_modified=[],
                files_deleted=[],
                test_results={},
            )

        engine._runner.execute = mock_execute

        exec_result = asyncio.run(engine.execute("W-bootstrap-4", use_claude_runner=True))
        # preflight 失败 → blocked
        assert exec_result["status"] == "blocked"

    def test_evidence_chain_is_complete(self, engine: WorkUnitEngine, project_dir: Path) -> None:
        """验证证据链完整性。"""
        unit = _make_work_unit(work_id="W-bootstrap-5")
        engine.create_work_unit(unit)
        engine.prepare("W-bootstrap-5")

        target_file = project_dir / "ralph" / "test_module.py"
        target_file.write_text(target_file.read_text() + "\n# modified\n")

        def mock_execute(**kwargs):
            return ExecutionResult(
                work_id="W-bootstrap-5",
                success=True,
                stdout="done",
                stderr="",
                files_created=[],
                files_modified=["ralph/test_module.py"],
                files_deleted=[],
                test_results={"test_all": "pass"},
            )

        engine._runner.execute = mock_execute

        asyncio.run(engine.execute("W-bootstrap-5", use_claude_runner=True))

        # 收集证据
        repo = RalphRepository(project_dir / ".ralph")
        evidence = repo.list_evidence("W-bootstrap-5")

        # 验证证据链
        evidence_types = {e.evidence_type for e in evidence}
        assert "diff" in evidence_types

        # 验证证据文件可读
        for ev in evidence:
            if ev.evidence_type == "diff":
                content = Path(ev.file_path).read_text(encoding="utf-8")
                assert "test_module.py" in content or "modified" in content

    def test_report_traces_to_evidence(self, engine: WorkUnitEngine, project_dir: Path) -> None:
        """验证报告能追溯到证据文件。"""
        unit = _make_work_unit(work_id="W-bootstrap-6")
        engine.create_work_unit(unit)
        engine.prepare("W-bootstrap-6")

        target_file = project_dir / "ralph" / "test_module.py"
        target_file.write_text(target_file.read_text() + "\n# trace test\n")

        def mock_execute(**kwargs):
            return ExecutionResult(
                work_id="W-bootstrap-6",
                success=True,
                stdout="done",
                stderr="",
                files_created=[],
                files_modified=["ralph/test_module.py"],
                files_deleted=[],
                test_results={"test_trace": "pass"},
            )

        engine._runner.execute = mock_execute

        asyncio.run(engine.execute("W-bootstrap-6", use_claude_runner=True))
        engine.review("W-bootstrap-6")

        # 生成报告
        ralph_dir = project_dir / ".ralph"
        gen = ReportGenerator(ralph_dir)
        report = gen.generate("端到端验证报告")

        # 验证报告内容
        assert "# 端到端验证报告" in report
        assert "W-bootstrap-6" in report
        assert "证据:" in report
        assert ".ralph/" in report  # 证据路径引用
