"""ContextPack — 上下文包

文档依据：
- AI 协议 §9 上下文包规则（包含 8 项、不包含 5 项）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextPack:
    """最小上下文包 — 对齐 AI 协议 §9。

    包含什么（8 项）：
    1. 当前任务
    2. 相关 PRD 片段
    3. 相关接口合同
    4. 相关文件列表及摘要
    5. 上游任务结果摘要
    6. 已知风险和约束
    7. 验收标准
    8. 禁止修改范围

    不包含什么（5 项）：
    1. 无关历史聊天
    2. 全量 PRD
    3. 全量研发报告
    4. 执行 agent 自述
    5. 无关模块的代码
    """

    work_id: str  # 关联的工作单元 ID
    task_description: str = ""  # 当前任务描述
    prd_fragment: str = ""  # 相关 PRD 片段
    interface_contracts: list[str] = field(default_factory=list)  # 相关接口合同
    file_summaries: dict[str, str] = field(default_factory=dict)  # 文件路径 → 摘要
    upstream_results: list[str] = field(default_factory=list)  # 上游任务结果摘要
    risks_and_constraints: list[str] = field(default_factory=list)  # 已知风险和约束
    acceptance_criteria: list[str] = field(default_factory=list)  # 验收标准
    scope_deny: list[str] = field(default_factory=list)  # 禁止修改范围
    trusted_data: list[str] = field(default_factory=list)  # 受信数据来源
    untrusted_data: list[str] = field(default_factory=list)  # 非受信数据来源

    def estimate_tokens(self) -> int:
        """粗略估算上下文包的 token 数。"""
        total = len(self.task_description) + len(self.prd_fragment)
        total += sum(len(c) for c in self.interface_contracts)
        total += sum(len(k) + len(v) for k, v in self.file_summaries.items())
        total += sum(len(r) for r in self.upstream_results)
        total += sum(len(r) for r in self.risks_and_constraints)
        total += sum(len(c) for c in self.acceptance_criteria)
        total += sum(len(s) for s in self.scope_deny)
        # 粗略：1 token ≈ 4 字符（中英混合）
        return total // 4
