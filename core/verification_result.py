"""结构化验证和执行结果 — 对齐 AI 协议 §8.2

文档依据：
- AI 协议 §8.2 执行结果格式
- AI 协议 §8.3 审查结论格式
- MVP 清单 §9 开发执行验收清单
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerificationResult:
    """Feature 验收结果。

    实现 __bool__ 以保持向后兼容：`if service.verify(feature):` 继续有效。
    """

    passed: bool
    files_checked: list[str] = field(default_factory=list)
    syntax_errors: list[str] = field(default_factory=list)
    scope_violations: list[str] = field(default_factory=list)
    e2e_result: bool | None = None  # None = E2E runner 不可用
    diff_summary: str = ""
    evidence_files: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed


@dataclass(frozen=True)
class ExecutionResult:
    """Feature 执行结果 — 对齐 AI 协议 §8.2。"""

    work_id: str
    status: str  # completed / failed / blocked
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    scope_violations: list[str] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    evidence_files: list[str] = field(default_factory=list)
    harness_violations: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.status == "completed"

    @property
    def files_changed(self) -> list[str]:
        return self.files_created + self.files_modified + self.files_deleted
