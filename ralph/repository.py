"""Ralph State Repository — .ralph/ 状态持久化

文档依据：
- 实施方案 §4.1 State Repository — 唯一事实来源、原子写入、拒绝非法状态流转
- 实施方案 §6 "保留和加强: 状态仓库升级为系统唯一事实来源"
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ralph.schema.blocker import Blocker
from ralph.schema.evidence import Evidence
from ralph.schema.review_result import ReviewResult
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus
from ralph.state_machine import InvalidTransitionError, StateMachine

logger = logging.getLogger(__name__)


class RalphRepository:
    """Ralph 状态仓库。

    - 唯一事实来源
    - 原子写入（tmpfile + rename）
    - WorkUnit CRUD + 状态转换
    - Evidence、ReviewResult、Blocker 持久化
    - 和现有 ProjectStateRepository 共存
    """

    def __init__(self, ralph_dir: Path) -> None:
        self._ralph_dir = Path(ralph_dir)
        self._ralph_dir.mkdir(parents=True, exist_ok=True)
        self._state_machine = StateMachine(self._ralph_dir / "state")

        # 子目录
        self._work_units_dir = self._ralph_dir / "work_units"
        self._evidence_dir = self._ralph_dir / "evidence"
        self._reviews_dir = self._ralph_dir / "reviews"
        self._blockers_dir = self._ralph_dir / "blockers"
        for d in [self._work_units_dir, self._evidence_dir, self._reviews_dir, self._blockers_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ── WorkUnit CRUD ─────────────────────────────────────────

    def save_work_unit(self, unit: WorkUnit) -> None:
        """保存 WorkUnit（原子写入）。"""
        path = self._work_units_dir / f"{unit.work_id}.json"
        self._atomic_write(path, self._serialize_work_unit(unit))
        logger.info("保存 WorkUnit: %s", unit.work_id)

    def get_work_unit(self, work_id: str) -> WorkUnit | None:
        """读取 WorkUnit。"""
        path = self._work_units_dir / f"{work_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize_work_unit(data)

    def list_work_units(self, status: WorkUnitStatus | None = None) -> list[WorkUnit]:
        """列出所有 WorkUnit，可按状态过滤。"""
        units = []
        for path in sorted(self._work_units_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            unit = self._deserialize_work_unit(data)
            if status is None or unit.status == status:
                units.append(unit)
        return units

    def delete_work_unit(self, work_id: str) -> bool:
        """删除 WorkUnit。"""
        path = self._work_units_dir / f"{work_id}.json"
        if path.exists():
            path.unlink()
            logger.info("删除 WorkUnit: %s", work_id)
            return True
        return False

    # ── 状态转换 ──────────────────────────────────────────────

    def transition(
        self,
        work_id: str,
        new_status: WorkUnitStatus,
        actor_role: str = "",
        reason: str = "",
    ) -> WorkUnit:
        """执行状态转换并持久化。

        对齐实施方案 §4.1：拒绝非法状态流转。
        """
        unit = self.get_work_unit(work_id)
        if unit is None:
            raise ValueError(f"WorkUnit {work_id} 不存在")

        new_unit = self._state_machine.transition(unit, new_status, actor_role, reason)
        self.save_work_unit(new_unit)
        return new_unit

    # ── Evidence ──────────────────────────────────────────────

    def save_evidence(self, evidence: Evidence) -> None:
        """保存证据。"""
        path = self._evidence_dir / f"{evidence.evidence_id}.json"
        self._atomic_write(path, asdict(evidence))

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        """读取证据。"""
        path = self._evidence_dir / f"{evidence_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Evidence(**data)

    def list_evidence(self, work_id: str | None = None) -> list[Evidence]:
        """列出证据，可按 work_id 过滤。"""
        items = []
        for path in sorted(self._evidence_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if work_id is None or data.get("work_id") == work_id:
                items.append(Evidence(**data))
        return items

    # ── ReviewResult ──────────────────────────────────────────

    def save_review(self, review: ReviewResult) -> None:
        """保存审查结论。"""
        path = self._reviews_dir / f"{review.work_id}_{review.reviewer_context_id}.json"
        self._atomic_write(path, self._serialize_review(review))

    def get_review(self, work_id: str, reviewer_context_id: str) -> ReviewResult | None:
        """读取审查结论。"""
        path = self._reviews_dir / f"{work_id}_{reviewer_context_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize_review(data)

    def list_reviews(self, work_id: str | None = None) -> list[ReviewResult]:
        """列出审查结论。"""
        items = []
        for path in sorted(self._reviews_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if work_id is None or data.get("work_id") == work_id:
                items.append(self._deserialize_review(data))
        return items

    # ── Blocker ───────────────────────────────────────────────

    def save_blocker(self, blocker: Blocker) -> None:
        """保存阻塞项。"""
        path = self._blockers_dir / f"{blocker.blocker_id}.json"
        self._atomic_write(path, asdict(blocker))

    def get_blocker(self, blocker_id: str) -> Blocker | None:
        """读取阻塞项。"""
        path = self._blockers_dir / f"{blocker_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Blocker(**data)

    def list_blockers(self, work_id: str | None = None, resolved: bool | None = None) -> list[Blocker]:
        """列出阻塞项。"""
        items = []
        for path in sorted(self._blockers_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if work_id is not None and data.get("work_id") != work_id:
                continue
            if resolved is not None and data.get("resolved") != resolved:
                continue
            items.append(Blocker(**data))
        return items

    # ── 转换日志 ──────────────────────────────────────────────

    def get_transitions(self, work_id: str | None = None) -> list[dict]:
        """读取转换日志。"""
        return self._state_machine.get_transitions(work_id)

    # ── 原子写入 ──────────────────────────────────────────────

    @staticmethod
    def _atomic_write(path: Path, data: dict) -> None:
        """原子写入：先写临时文件，再 rename。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
        except Exception:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── 序列化辅助 ────────────────────────────────────────────

    @staticmethod
    def _serialize_work_unit(unit: WorkUnit) -> dict:
        """WorkUnit → dict（处理 Enum 和嵌套对象）。"""
        data = asdict(unit)
        data["status"] = unit.status.value
        if unit.task_harness:
            data["task_harness"] = asdict(unit.task_harness)
        if unit.context_pack:
            data["context_pack"] = asdict(unit.context_pack)
        if unit.evidence:
            data["evidence"] = [asdict(e) for e in unit.evidence]
        if unit.review_result:
            data["review_result"] = RalphRepository._serialize_review(unit.review_result)
        return data

    @staticmethod
    def _deserialize_work_unit(data: dict) -> WorkUnit:
        """dict → WorkUnit。"""
        from ralph.schema.context_pack import ContextPack
        from ralph.schema.task_harness import RetryPolicy, TaskHarness, TimeoutPolicy

        # 处理 status enum
        data["status"] = WorkUnitStatus(data["status"])

        # 处理嵌套 TaskHarness
        if data.get("task_harness"):
            th_data = data["task_harness"]
            if "retry_policy" in th_data and isinstance(th_data["retry_policy"], dict):
                th_data["retry_policy"] = RetryPolicy(**th_data["retry_policy"])
            if "timeout_policy" in th_data and isinstance(th_data["timeout_policy"], dict):
                th_data["timeout_policy"] = TimeoutPolicy(**th_data["timeout_policy"])
            data["task_harness"] = TaskHarness(**th_data)

        # 处理嵌套 ContextPack
        if data.get("context_pack"):
            data["context_pack"] = ContextPack(**data["context_pack"])

        # 处理 Evidence 列表
        if data.get("evidence"):
            data["evidence"] = [Evidence(**e) for e in data["evidence"]]

        # 处理 ReviewResult
        if data.get("review_result"):
            data["review_result"] = RalphRepository._deserialize_review(data["review_result"])

        return WorkUnit(**data)

    @staticmethod
    def _serialize_review(review: ReviewResult) -> dict:
        data = asdict(review)
        return data

    @staticmethod
    def _deserialize_review(data: dict) -> ReviewResult:
        from ralph.schema.review_result import CriterionResult, Issue

        if data.get("criteria_results"):
            data["criteria_results"] = [CriterionResult(**c) for c in data["criteria_results"]]
        if data.get("issues_found"):
            data["issues_found"] = [Issue(**i) for i in data["issues_found"]]
        return ReviewResult(**data)
