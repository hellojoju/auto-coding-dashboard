"""Context Pack Manager — 上下文包组装

文档依据：
- AI 协议 §9 上下文包规则（包含 8 项、不包含 5 项）
- 实施方案 §4.7 Context Pack Manager
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ralph.schema.context_pack import ContextPack

if TYPE_CHECKING:
    from ralph.schema.work_unit import WorkUnit

logger = logging.getLogger(__name__)


class ContextPackManager:
    """为 WorkUnit 组装最小上下文包。

    包含什么（§9 八项）：
    1. 当前任务
    2. 相关 PRD 片段
    3. 相关接口合同
    4. 相关文件列表及摘要
    5. 上游任务结果摘要
    6. 已知风险和约束
    7. 验收标准
    8. 禁止修改范围

    不包含什么（§9 五项）：
    1. 无关历史聊天
    2. 全量 PRD
    3. 全量研发报告
    4. 执行 agent 自述
    5. 无关模块的代码
    """

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = Path(project_dir)

    def build(
        self,
        unit: WorkUnit,
        prd_fragment: str = "",
        interface_contracts: list[str] | None = None,
        upstream_results: list[str] | None = None,
        budget_tokens: int = 8000,
    ) -> ContextPack:
        """为 WorkUnit 组装上下文包。

        Args:
            unit: 工作单元
            prd_fragment: 相关的 PRD 片段（不是全量 PRD）
            interface_contracts: 相关接口合同
            upstream_results: 上游任务结果摘要
            budget_tokens: 上下文 token 预算

        Returns:
            ContextPack

        Raises:
            ValueError: 超出 budget
        """
        # 收集相关文件摘要
        file_summaries = self._collect_file_summaries(unit.scope_allow)

        # 组装风险和约束
        risks = []
        if unit.risk_notes:
            risks.append(unit.risk_notes)
        if unit.impact_if_wrong:
            risks.append(f"假设错误影响: {unit.impact_if_wrong}")
        risks.extend(unit.scope_deny)  # 禁止范围也是约束

        pack = ContextPack(
            work_id=unit.work_id,
            task_description=f"{unit.title}\n{unit.target}",
            prd_fragment=prd_fragment,
            interface_contracts=interface_contracts or [],
            file_summaries=file_summaries,
            upstream_results=upstream_results or [],
            risks_and_constraints=risks,
            acceptance_criteria=unit.acceptance_criteria,
            scope_deny=unit.scope_deny,
            trusted_data=["PRD 片段", "接口合同", "上游任务结果"],
            untrusted_data=["执行 agent 自述", "无关历史聊天"],
        )

        # 检查 budget
        estimated = pack.estimate_tokens()
        if estimated > budget_tokens:
            raise ValueError(
                f"上下文包超出 budget: {estimated} > {budget_tokens} tokens"
            )

        logger.info(
            "为 %s 组装上下文包: ~%d tokens, %d 文件",
            unit.work_id,
            estimated,
            len(file_summaries),
        )

        return pack

    def _collect_file_summaries(self, scope_allow: list[str]) -> dict[str, str]:
        """收集允许范围内的文件摘要。"""
        summaries: dict[str, str] = {}
        for pattern in scope_allow:
            # 简单实现：扫描目录下的文件
            if pattern.endswith("/"):
                dir_path = self._project_dir / pattern
                if dir_path.is_dir():
                    for f in dir_path.rglob("*.py"):
                        rel = str(f.relative_to(self._project_dir))
                        summaries[rel] = self._summarize_file(f)
            else:
                file_path = self._project_dir / pattern
                if file_path.is_file():
                    rel = str(file_path.relative_to(self._project_dir))
                    summaries[rel] = self._summarize_file(file_path)
        return summaries

    @staticmethod
    def _summarize_file(path: Path) -> str:
        """生成文件摘要（前几行）。"""
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")[:5]
            return "\n".join(lines)
        except (OSError, UnicodeDecodeError):
            return f"[无法读取: {path.name}]"
