"""Feature追踪 - 管理features.json"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core.config import FEATURES_FILE
from core.progress_logger import progress


@dataclass
class Feature:
    id: str
    category: str
    description: str
    priority: str  # P0, P1, P2, P3
    assigned_to: str  # backend, frontend, database, qa, ui, security, docs
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, review, done, blocked
    passes: bool = False
    test_steps: list[str] = field(default_factory=list)
    error_log: list[str] = field(default_factory=list)
    completed_at: str | None = None
    # Dashboard 扩展字段
    assigned_instance: str = ""  # e.g. "backend-1"
    workspace_path: str = ""  # 该 Feature 涉及的文件路径
    files_changed: list[str] = field(default_factory=list)
    started_at: str | None = None
    blocking_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Feature":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class FeatureTracker:
    """管理Feature列表的增删改查"""

    def __init__(self, features_file: Path | None = None):
        self._features_file = features_file or FEATURES_FILE
        self._features: list[Feature] = []
        self._load()

    def _load(self) -> None:
        if self._features_file.exists():
            data = json.loads(self._features_file.read_text(encoding="utf-8"))
            self._features = [Feature.from_dict(f) for f in data.get("features", [])]

    def _save(self) -> None:
        self._features_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "features": [f.to_dict() for f in self._features],
            "summary": self.summary(),
        }
        self._features_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, feature: Feature) -> None:
        self._features.append(feature)
        self._save()

    def bulk_add(self, features: list[Feature]) -> None:
        self._features.extend(features)
        self._save()
        progress.log(f"批量导入 {len(features)} 个features")

    def get(self, feature_id: str) -> Feature | None:
        for f in self._features:
            if f.id == feature_id:
                return f
        return None

    def get_next_ready(self) -> Feature | None:
        """获取下一个可执行的feature（依赖全部完成、优先级最高）"""
        candidates = []
        for f in self._features:
            if f.status != "pending":
                continue
            deps_met = all(
                self.get(dep_id) and self.get(dep_id).status == "done"
                for dep_id in f.dependencies
            )
            if deps_met:
                candidates.append(f)

        if not candidates:
            return None

        # 按优先级排序 P0 > P1 > P2 > P3
        candidates.sort(key=lambda f: int(f.priority[1]))
        return candidates[0]

    def mark_in_progress(self, feature_id: str, instance_id: str = "", workspace_path: str = "") -> None:
        f = self.get(feature_id)
        if f:
            f.status = "in_progress"
            f.assigned_instance = instance_id
            f.workspace_path = workspace_path
            f.started_at = datetime.now().isoformat()
            self._save()
            progress.log(f"{feature_id} 开始开发: {f.description}")

    def mark_review(self, feature_id: str) -> None:
        f = self.get(feature_id)
        if f:
            f.status = "review"
            self._save()
            progress.log(f"{feature_id} 进入验收阶段")

    def mark_done(self, feature_id: str, files_changed: list[str] | None = None) -> None:
        f = self.get(feature_id)
        if f:
            f.status = "done"
            f.passes = True
            f.completed_at = datetime.now().isoformat()
            if files_changed:
                f.files_changed = files_changed
            self._save()
            progress.log(f"{feature_id} 完成: {f.description}")

    def mark_blocked(self, feature_id: str, reason: str) -> None:
        f = self.get(feature_id)
        if f:
            f.status = "blocked"
            f.error_log.append(reason)
            self._save()
            progress.log(f"{feature_id} 被阻塞: {reason}")

    def add_error(self, feature_id: str, error: str) -> None:
        f = self.get(feature_id)
        if f:
            f.error_log.append(error)
            self._save()

    def summary(self) -> dict:
        total = len(self._features)
        done = sum(1 for f in self._features if f.status == "done")
        in_progress = sum(1 for f in self._features if f.status == "in_progress")
        blocked = sum(1 for f in self._features if f.status == "blocked")
        pending = sum(1 for f in self._features if f.status == "pending")
        passing = sum(1 for f in self._features if f.passes)
        return {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "blocked": blocked,
            "pending": pending,
            "passing": passing,
        }

    def all_done(self) -> bool:
        return all(f.status == "done" for f in self._features) and len(self._features) > 0

    def all_features(self) -> list[Feature]:
        return list(self._features)
