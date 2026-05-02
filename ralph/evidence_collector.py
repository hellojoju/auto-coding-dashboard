"""Evidence Collector — 证据收集

文档依据：
- AI 协议 §8.2 执行结果格式 — evidence_files 字段
- MVP 清单 §9 开发执行验收清单 — 必须提交证据文件
- PRD §9.10 真实可用性验收 — diff、测试输出、Playwright 截图
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from ralph.schema.evidence import Evidence

logger = logging.getLogger(__name__)


class EvidenceCollector:
    """收集执行证据并保存到 .ralph/evidence/<work_id>/。"""

    def __init__(self, ralph_dir: Path) -> None:
        self._evidence_base = ralph_dir / "evidence"
        self._evidence_base.mkdir(parents=True, exist_ok=True)

    def collect(
        self,
        work_id: str,
        workspace_dir: Path,
        *,
        include_diff: bool = True,
        include_files_changed: bool = True,
        include_test_output: str = "",
    ) -> list[Evidence]:
        """收集证据。

        Args:
            work_id: 工作单元 ID
            workspace_dir: 工作目录
            include_diff: 是否收集 git diff
            include_files_changed: 是否收集文件变更清单
            include_test_output: 测试输出（如果提供则保存）

        Returns:
            收集到的 Evidence 列表
        """
        evidence_dir = self._evidence_base / work_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        items: list[Evidence] = []

        if include_diff:
            e = self._collect_diff(work_id, workspace_dir, evidence_dir)
            if e:
                items.append(e)

        if include_files_changed:
            e = self._collect_files_changed(work_id, workspace_dir, evidence_dir)
            if e:
                items.append(e)

        if include_test_output:
            e = self._save_test_output(work_id, include_test_output, evidence_dir)
            if e:
                items.append(e)

        logger.info("为 %s 收集了 %d 个证据", work_id, len(items))
        return items

    def _collect_diff(
        self, work_id: str, workspace_dir: Path, evidence_dir: Path
    ) -> Evidence | None:
        """收集 git diff --stat。"""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            content = result.stdout.strip()
            if not content:
                return None

            file_path = evidence_dir / "diff.txt"
            file_path.write_text(content, encoding="utf-8")

            return Evidence(
                evidence_id=f"{work_id}-diff",
                work_id=work_id,
                evidence_type="diff",
                file_path=str(file_path),
                description="git diff --stat HEAD",
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _collect_files_changed(
        self, work_id: str, workspace_dir: Path, evidence_dir: Path
    ) -> Evidence | None:
        """收集变更文件列表。"""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            content = result.stdout.strip()
            if not content:
                return None

            file_path = evidence_dir / "files_changed.txt"
            file_path.write_text(content, encoding="utf-8")

            return Evidence(
                evidence_id=f"{work_id}-files",
                work_id=work_id,
                evidence_type="files_changed",
                file_path=str(file_path),
                description="变更文件列表",
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def _save_test_output(
        self, work_id: str, output: str, evidence_dir: Path
    ) -> Evidence:
        """保存测试输出。"""
        file_path = evidence_dir / "test_output.txt"
        file_path.write_text(output, encoding="utf-8")

        return Evidence(
            evidence_id=f"{work_id}-test",
            work_id=work_id,
            evidence_type="test_output",
            file_path=str(file_path),
            description="测试输出",
        )
