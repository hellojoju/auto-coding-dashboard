"""Report Generator — 中文研发报告

文档依据：
- PRD §9.13 最终报告 — 必须生成中文研发报告
- AI 协议 §10.6 最终报告验收 — 追溯已完成任务、证据、测试、review、阻塞项
- MVP 清单 §26 中文研发报告
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from ralph.repository import RalphRepository
from ralph.schema.work_unit import WorkUnitStatus

logger = logging.getLogger(__name__)


class ReportGenerator:
    """中文研发报告生成器。

    - 汇总已完成 WorkUnit、evidence、blocker、review 结果
    - 生成中文报告，必须引用证据文件
    - 不能凭记忆总结
    """

    def __init__(self, ralph_dir: Path) -> None:
        self._ralph_dir = Path(ralph_dir)
        self._repository = RalphRepository(ralph_dir)

    def generate(self, title: str = "研发报告") -> str:
        """生成中文研发报告。

        报告内容：
        1. 完成内容
        2. 修改文件
        3. 测试结果
        4. Review 结论
        5. 阻塞项
        6. 风险
        """
        # 收集数据
        accepted = self._repository.list_work_units(WorkUnitStatus.ACCEPTED)
        blocked = self._repository.list_work_units(WorkUnitStatus.BLOCKED)
        failed = self._repository.list_work_units(WorkUnitStatus.FAILED)
        all_blockers = self._repository.list_blockers()

        lines: list[str] = [
            f"# {title}",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 任务完成情况",
            "",
            f"- 已验收: {len(accepted)} 个",
            f"- 阻塞中: {len(blocked)} 个",
            f"- 失败: {len(failed)} 个",
            "",
        ]

        if accepted:
            lines.extend(["## 已完成任务", ""])
            for unit in accepted:
                lines.append(f"### {unit.work_id}: {unit.title}")
                lines.append(f"- 目标: {unit.target}")
                lines.append(f"- 修改范围: {', '.join(unit.scope_allow)}")

                # 证据
                evidence = self._repository.list_evidence(unit.work_id)
                if evidence:
                    lines.append("- 证据:")
                    for ev in evidence:
                        lines.append(f"  - [{ev.evidence_type}] {ev.file_path}")

                # Review
                reviews = self._repository.list_reviews(unit.work_id)
                if reviews:
                    for r in reviews:
                        lines.append(f"- Review: {r.conclusion} ({r.recommended_action})")

                lines.append("")

        if blocked:
            lines.extend(["## 阻塞任务", ""])
            for unit in blocked:
                lines.append(f"- {unit.work_id}: {unit.title}")
            lines.append("")

        if all_blockers:
            lines.extend(["## 阻塞项", ""])
            for b in all_blockers:
                lines.append(f"- {b.blocker_id}: {b.reason} (类型: {b.blocker_type})")
            lines.append("")

        # 风险汇总
        lines.extend(["## 风险汇总", ""])
        for unit in accepted:
            if unit.risk_notes:
                lines.append(f"- {unit.work_id}: {unit.risk_notes}")
        if not any(u.risk_notes for u in accepted):
            lines.append("- 无记录风险")
        lines.append("")

        return "\n".join(lines)

    def save(self, content: str, filename: str = "report.md") -> Path:
        """保存报告到 .ralph/reports/。"""
        reports_dir = self._ralph_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.info("报告已保存: %s", path)
        return path

    def list_reports(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Path]:
        """列出已保存的报告，支持按日期范围过滤。"""
        reports_dir = self._ralph_dir / "reports"
        if not reports_dir.exists():
            return []

        reports = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if since:
            reports = [r for r in reports if datetime.fromtimestamp(r.stat().st_mtime) >= since]
        if until:
            reports = [r for r in reports if datetime.fromtimestamp(r.stat().st_mtime) <= until]
        return reports
