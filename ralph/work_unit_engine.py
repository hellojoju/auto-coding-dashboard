"""WorkUnit Engine — 新编排器

文档依据：
- 实施方案 §4.2 Work Unit Engine
- AI 协议 §7.2 状态修改权限
- MVP 清单 §13 MVP 完成定义

职责：
- 替代 ProjectManager 的执行循环
- 流程：创建 WorkUnit → preflight check → 生成 Harness → 生成 ContextPack
  → 执行前门禁 → 调用 Claude Runner → 收集 Evidence → 执行后门禁
  → 独立 Review → 状态决策
- 和 PMCoordinator 共存，通过 feature flag 切换
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

from ralph.claude_runner import ClaudeCodeRunner, ExecutionResult
from ralph.context_pack_manager import ContextPackManager
from ralph.evidence_collector import EvidenceCollector
from ralph.harness_manager import HarnessManager
from ralph.repository import RalphRepository
from ralph.review_manager import ReviewManager, ReviewRequest
from ralph.schema.review_result import ReviewResult
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus

logger = logging.getLogger(__name__)


class WorkUnitEngine:
    """WorkUnit 编排引擎。

    完整闭环：
    draft → ready → running → needs_review → accepted/failed/blocked
    """

    def __init__(self, project_dir: Path, event_bus: Any = None) -> None:
        self._project_dir = Path(project_dir)
        ralph_dir = self._project_dir / ".ralph"
        self._repository = RalphRepository(ralph_dir)
        self._harness_mgr = HarnessManager()
        self._context_mgr = ContextPackManager(self._project_dir)
        self._evidence_collector = EvidenceCollector(ralph_dir)
        self._review_mgr = ReviewManager()
        self._runner = ClaudeCodeRunner(self._project_dir)
        self._event_bus = event_bus

    def _emit_event(self, event_type: str, **kwargs: Any) -> None:
        """发送 Ralph 事件到 Dashboard（如果有 event_bus）。"""
        if self._event_bus is not None:
            self._event_bus.emit(event_type, **kwargs)

    def create_work_unit(self, unit: WorkUnit) -> WorkUnit:
        """创建并保存 WorkUnit（初始状态 draft）。"""
        self._repository.save_work_unit(unit)
        logger.info("创建 WorkUnit: %s", unit.work_id)
        return unit

    def prepare(self, work_id: str) -> WorkUnit:
        """准备工作单元：draft → ready。

        检查：
        1. harness 校验通过
        2. ready 条件满足
        """
        unit = self._repository.get_work_unit(work_id)
        if unit is None:
            raise ValueError(f"WorkUnit {work_id} 不存在")

        # harness 校验
        if unit.task_harness:
            harness_errors = self._harness_mgr.validate_harness(unit.task_harness)
            if harness_errors:
                logger.error("harness 校验失败: %s", harness_errors)
                raise ValueError(f"harness 校验失败: {harness_errors}")

        # ready 条件
        ready_errors = unit.validate_ready()
        if ready_errors:
            logger.error("ready 条件不满足: %s", ready_errors)
            raise ValueError(f"ready 条件不满足: {ready_errors}")

        result = self._repository.transition(
            work_id, WorkUnitStatus.READY, actor_role="scheduler", reason="通过预检"
        )
        self._emit_event("ralph_work_unit_ready", work_id=work_id, status=WorkUnitStatus.READY.value)
        return result

    async def execute(
        self,
        work_id: str,
        agent: Any = None,
        prd_summary: str = "",
        use_claude_runner: bool = True,
    ) -> dict:
        """执行 WorkUnit：ready → running → needs_review/failed/blocked。

        Args:
            work_id: WorkUnit ID
            agent: 执行 agent（use_claude_runner=False 时使用旧接口）
            prd_summary: PRD 摘要
            use_claude_runner: 是否使用 Claude Code Runner 执行

        Returns:
            执行结果 dict
        """
        unit = self._repository.get_work_unit(work_id)
        if unit is None:
            raise ValueError(f"WorkUnit {work_id} 不存在")

        # ready → running
        unit = self._repository.transition(
            work_id, WorkUnitStatus.RUNNING, actor_role="scheduler"
        )
        self._emit_event("ralph_work_unit_running", work_id=work_id, status=WorkUnitStatus.RUNNING.value)

        # 生成 ContextPack
        try:
            context_pack = self._context_mgr.build(unit, prd_fragment=prd_summary)
        except ValueError as e:
            logger.error("上下文包超出 budget: %s", e)
            unit = self._repository.transition(
                work_id, WorkUnitStatus.BLOCKED, reason=f"上下文包超出 budget: {e}"
            )
            return {"success": False, "status": "blocked", "error": str(e), "work_id": work_id}

        # 执行前门禁
        preflight = self._harness_mgr.preflight(unit)
        if not preflight.passed:
            logger.error("执行前门禁失败: %s", preflight.failures)
            unit = self._repository.transition(
                work_id, WorkUnitStatus.BLOCKED, reason=f"preflight 失败: {preflight.failures}"
            )
            return {"success": False, "status": "blocked", "error": str(preflight.failures), "work_id": work_id}

        # 开始执行中记录
        self._harness_mgr.start_inflight(work_id)

        # 调用执行器
        if use_claude_runner:
            exec_result = await self._execute_with_claude(unit, context_pack, prd_summary)
        else:
            exec_result = await self._execute_with_agent(agent, unit, context_pack, prd_summary)

        if not exec_result.success:
            logger.error("执行失败: %s", exec_result.error)
            unit = self._repository.transition(
                work_id, WorkUnitStatus.FAILED, actor_role="executor", reason=exec_result.error
            )
            return {
                "success": False,
                "status": "failed",
                "error": exec_result.error,
                "work_id": work_id,
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
            }

        # 记录执行中变更
        self._harness_mgr.record_inflight(
            work_id,
            files_modified=exec_result.files_modified + exec_result.files_created,
        )

        # 收集证据
        evidence_items = self._evidence_collector.collect(
            work_id,
            self._project_dir,
            include_test_output=str(exec_result.test_results),
        )
        for ev in evidence_items:
            self._repository.save_evidence(ev)

        # 执行后门禁
        all_changed = exec_result.files_created + exec_result.files_modified + exec_result.files_deleted
        postflight = self._harness_mgr.postflight(
            unit,
            files_changed=all_changed,
            evidence_files=[e.file_path for e in evidence_items],
            test_passed=bool(exec_result.test_results),
            review_completed=True,
        )

        if not postflight.passed:
            logger.error("执行后门禁失败: %s", postflight.failures)
            unit = self._repository.transition(
                work_id, WorkUnitStatus.FAILED, actor_role="executor", reason=f"postflight 失败: {postflight.failures}"
            )
            return {"success": False, "status": "failed", "error": str(postflight.failures), "work_id": work_id}

        # running → needs_review
        unit = self._repository.transition(
            work_id, WorkUnitStatus.NEEDS_REVIEW, actor_role="executor"
        )
        self._emit_event("ralph_work_unit_needs_review", work_id=work_id, status=WorkUnitStatus.NEEDS_REVIEW.value)

        return {
            "success": True,
            "status": "needs_review",
            "work_id": work_id,
            "files_changed": all_changed,
            "evidence_files": [e.file_path for e in evidence_items],
            "exec_result": exec_result,
        }

    async def _execute_with_claude(
        self,
        unit: WorkUnit,
        context_pack: Any,
        prd_summary: str,
    ) -> ExecutionResult:
        """通过 Claude Code Runner 执行（流式模式）。"""
        harness = unit.task_harness
        harness_text = str(harness) if harness else ""

        scope_allow = unit.scope_allow or (harness.scope_allow if harness else [])
        scope_deny = unit.scope_deny or (harness.scope_deny if harness else [])
        acceptance_criteria = unit.acceptance_criteria or []

        context_text = str(context_pack)

        def _stream_cb(event_type: str, chunk: str) -> None:
            self._emit_event("ralph_stream_chunk", work_id=unit.work_id, chunk_type=event_type, text=chunk)

        return await self._runner.execute_streaming(
            work_id=unit.work_id,
            context_pack_text=context_text,
            harness_text=harness_text,
            scope_allow=scope_allow,
            scope_deny=scope_deny,
            acceptance_criteria=acceptance_criteria,
            stream_callback=_stream_cb,
        )

    async def _execute_with_agent(
        self,
        agent: Any,
        unit: WorkUnit,
        context_pack: Any,
        prd_summary: str,
    ) -> ExecutionResult:
        """通过旧版 agent 接口执行（兼容模式）。"""
        try:
            agent_result = await agent.execute(
                {
                    "feature_id": unit.work_id,
                    "description": unit.target,
                    "prd_summary": prd_summary,
                    "context_pack": str(context_pack),
                },
                workspace_dir=self._project_dir,
            )

            files_changed = agent_result.get("files_changed", [])
            return ExecutionResult(
                work_id=unit.work_id,
                success=agent_result.get("success", False),
                stdout="",
                stderr="",
                files_created=[f for f in files_changed if f],
                files_modified=[],
                files_deleted=[],
                test_results={"agent_test": "pass"} if agent_result.get("success") else {},
                error=agent_result.get("error"),
            )
        except Exception as e:
            return ExecutionResult(
                work_id=unit.work_id,
                success=False,
                stdout="",
                stderr="",
                error=str(e),
            )

    def review(self, work_id: str) -> ReviewResult:
        """独立审查：needs_review → accepted/needs_rework/blocked。

        由调度 agent 调用，根据审查结论做状态决策。
        """
        unit = self._repository.get_work_unit(work_id)
        if unit is None:
            raise ValueError(f"WorkUnit {work_id} 不存在")
        if unit.status != WorkUnitStatus.NEEDS_REVIEW:
            raise ValueError(f"WorkUnit {work_id} 当前状态为 {unit.status.value}，不能执行 review")

        # 收集 diff 和 evidence
        evidence_list = self._repository.list_evidence(work_id)
        diff_stat = ""
        for ev in evidence_list:
            if ev.evidence_type == "diff":
                with contextlib.suppress(OSError):
                    diff_stat = Path(ev.file_path).read_text(encoding="utf-8")

        # 构建审查请求
        request = ReviewRequest(
            work_id=work_id,
            diff_summary=diff_stat,
            acceptance_criteria=unit.acceptance_criteria,
            evidence_files=[e.file_path for e in evidence_list],
            task_description=unit.target,
            scope_allow=unit.scope_allow,
            scope_deny=unit.scope_deny,
        )

        # 独立审查
        review = self._review_mgr.review(request)
        self._repository.save_review(review)

        # 状态决策
        if review.conclusion == "通过":
            self._repository.transition(
                work_id, WorkUnitStatus.ACCEPTED, actor_role="scheduler", reason="审查通过"
            )
        elif review.recommended_action == "返工":
            self._repository.transition(
                work_id, WorkUnitStatus.NEEDS_REWORK, actor_role="scheduler", reason="审查不通过，需返工"
            )
        else:
            self._repository.transition(
                work_id, WorkUnitStatus.BLOCKED, actor_role="scheduler", reason=f"审查结论: {review.recommended_action}"
            )

        return review

    def get_work_unit(self, work_id: str) -> WorkUnit | None:
        return self._repository.get_work_unit(work_id)

    def list_work_units(self, status: WorkUnitStatus | None = None) -> list[WorkUnit]:
        return self._repository.list_work_units(status)
