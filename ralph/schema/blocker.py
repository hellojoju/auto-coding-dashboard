"""Blocker — 阻塞项

文档依据：
- AI 协议 §11 阻塞机制（8 个触发条件）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Blocker:
    """阻塞项。"""

    blocker_id: str
    work_id: str
    reason: str
    blocker_type: str  # permission / dependency / tool_unavailable / scope_violation / review_failed
    resolution: str = ""
    resolved: bool = False
