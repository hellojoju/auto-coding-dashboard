"""Feature追踪 - 管理features.json

Phase 3 重构后，FeatureTracker 退化为 ProjectStateRepository 的薄适配层。
当传入 repository 参数时，所有读写委托给 Repository；否则回退到 features.json
（向后兼容旧代码）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import FEATURES_FILE
from core.progress_logger import progress
from dashboard.models import Feature  # 重新导出，保持向后兼容

if TYPE_CHECKING:
    from dashboard.state_repository import ProjectStateRepository


class FeatureTracker:
    """管理Feature列表的增删改查。

    当 repository 已提供时，所有操作委托给 Repository（唯一事实源）。
    否则回退到 features.json 文件（向后兼容）。
    """

    def __init__(
        self,
        features_file: Path | None = None,
        *,
        repository: ProjectStateRepository | None = None,
    ):
        self._features_file = features_file or FEATURES_FILE
        self._repository = repository
        self._features: list = []  # 仅在无 repository 时使用
        if self._repository is None:
            self._load()

    def _load(self) -> None:
        if self._repository is not None:
            return
        if self._features_file.exists():
            Feature = _get_core_feature_class()
            data = json.loads(self._features_file.read_text(encoding="utf-8"))
            self._features = [Feature.from_dict(f) for f in data.get("features", [])]

    def _save(self) -> None:
        if self._repository is not None:
            return
        self._features_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "features": [f.to_dict() for f in self._features],
            "summary": self.summary(),
        }
        self._features_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, feature) -> None:
        if self._repository is not None:
            self._repository.upsert_feature(feature)
        else:
            self._features.append(feature)
            self._save()

    def bulk_add(self, features: list) -> None:
        if self._repository is not None:
            for f in features:
                self._repository.upsert_feature(f)
        else:
            self._features.extend(features)
            self._save()
        progress.log(f"批量导入 {len(features)} 个features")

    def get(self, feature_id: str):
        if self._repository is not None:
            return self._repository.get_feature(feature_id)
        for f in self._features:
            if f.id == feature_id:
                return f
        return None

    def get_next_ready(self):
        """获取下一个可执行的feature（依赖全部完成、优先级最高）"""
        if self._repository is not None:
            return self._repository.get_next_ready_feature()

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

        candidates.sort(key=lambda f: int(f.priority[1]))
        return candidates[0]

    def _update_feature(self, feature_id: str, **updates: str) -> None:
        """更新 feature 字段。Repository 模式下深拷贝后写入，否则就地修改。"""
        if self._repository is not None:
            existing = self._repository.get_feature(feature_id)
            if existing is None:
                return
            for key, value in updates.items():
                setattr(existing, key, value)
            self._repository.upsert_feature(existing, event_type="feature_updated")
        else:
            f = self.get(feature_id)
            if f:
                for key, value in updates.items():
                    setattr(f, key, value)
                self._save()

    def mark_in_progress(self, feature_id: str, instance_id: str = "", workspace_path: str = "") -> None:
        updates = {
            "status": "in_progress",
            "assigned_instance": instance_id,
            "workspace_path": workspace_path,
            "started_at": datetime.now().isoformat(),
        }
        self._update_feature(feature_id, **updates)
        f = self.get(feature_id)
        if f:
            progress.log(f"{feature_id} 开始开发: {f.description}")

    def mark_review(self, feature_id: str) -> None:
        self._update_feature(feature_id, status="review")
        progress.log(f"{feature_id} 进入验收阶段")

    def mark_done(self, feature_id: str, files_changed: list[str] | None = None) -> None:
        updates = {
            "status": "done",
            "passes": True,
            "completed_at": datetime.now().isoformat(),
        }
        if files_changed:
            updates["files_changed"] = files_changed
        self._update_feature(feature_id, **updates)
        f = self.get(feature_id)
        if f:
            progress.log(f"{feature_id} 完成: {f.description}")

    def mark_blocked(self, feature_id: str, reason: str) -> None:
        # Repository 模式下先获取现有 feature 再追加 error_log
        if self._repository is not None:
            f = self.get(feature_id)
            if f:
                error_log = list(getattr(f, "error_log", []))
                error_log.append(reason)
                self._update_feature(
                    feature_id,
                    status="blocked",
                    error_log=error_log,
                )
                progress.log(f"{feature_id} 被阻塞: {reason}")
        else:
            f = self.get(feature_id)
            if f:
                f.status = "blocked"
                f.error_log.append(reason)
                self._save()
                progress.log(f"{feature_id} 被阻塞: {reason}")

    def add_error(self, feature_id: str, error: str) -> None:
        if self._repository is not None:
            f = self.get(feature_id)
            if f:
                error_log = list(getattr(f, "error_log", []))
                error_log.append(error)
                self._update_feature(feature_id, error_log=error_log)
        else:
            f = self.get(feature_id)
            if f:
                f.error_log.append(error)
                self._save()

    def summary(self) -> dict:
        features = self.all_features()
        total = len(features)
        done = sum(1 for f in features if f.status == "done")
        in_progress = sum(1 for f in features if f.status == "in_progress")
        blocked = sum(1 for f in features if f.status == "blocked")
        pending = sum(1 for f in features if f.status == "pending")
        passing = sum(1 for f in features if getattr(f, "passes", False))
        return {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "blocked": blocked,
            "pending": pending,
            "passing": passing,
        }

    def all_done(self) -> bool:
        features = self.all_features()
        return all(f.status == "done" for f in features) and len(features) > 0

    def all_features(self) -> list:
        if self._repository is not None:
            return self._repository.list_features()
        return list(self._features)
