from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ConfirmedFact:
    topic: str           # "目标用户", "核心功能", etc.
    fact: str            # the confirmed statement
    source_quote: str    # user's original words
    recorded_at: str = field(default_factory=_now_iso)


@dataclass
class OpenAssumption:
    question: str        # the question to resolve
    context: str         # why this matters
    status: str = "open"  # open | resolved | deferred
    resolved_answer: str = ""


@dataclass
class UserPath:
    name: str            # "新用户注册流程"
    steps: list[str] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)


@dataclass
class BrainstormRecord:
    record_id: str
    project_name: str
    round_number: int
    user_message: str
    system_questions: list[str] = field(default_factory=list)
    confirmed_facts: list[ConfirmedFact] = field(default_factory=list)
    open_assumptions: list[OpenAssumption] = field(default_factory=list)
    user_paths: list[UserPath] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def completeness_score(self) -> float:
        """需求完整度评分: 0.0-1.0"""
        checks = [
            len(self.confirmed_facts) >= 3,
            len(self.open_assumptions) == 0,
            len(self.user_paths) >= 1,
            any(f.topic == "目标用户" for f in self.confirmed_facts),
            any(f.topic == "核心功能" for f in self.confirmed_facts),
            any(f.topic == "验收标准" for f in self.confirmed_facts),
        ]
        return sum(checks) / len(checks)
