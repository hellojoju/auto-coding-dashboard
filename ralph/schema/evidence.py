"""Evidence — 证据

文档依据：
- AI 协议 §8.2 执行结果格式 — evidence_files 字段
- MVP 清单 §9 开发执行验收清单 — 必须提交证据文件
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Evidence:
    """执行证据。"""

    evidence_id: str
    work_id: str
    evidence_type: str  # diff / test_output / lint_output / screenshot / log
    file_path: str  # 证据文件路径
    description: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at", datetime.now().isoformat())
