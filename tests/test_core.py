"""Tests for core infrastructure"""

import json
from unittest.mock import patch

from core.feature_tracker import Feature, FeatureTracker
from core.progress_logger import ProgressLogger
from core.task_queue import TaskQueue


class TestFeatureTracker:
    def test_create_and_save(self, tmp_path):
        features_file = tmp_path / "features.json"
        with patch("core.feature_tracker.FEATURES_FILE", features_file):
            tracker = FeatureTracker()
            feature = Feature(
                id="F001",
                category="auth",
                description="用户注册",
                priority="P0",
                assigned_to="backend",
                test_steps=["打开注册页", "填写表单", "提交"],
            )
            tracker.add(feature)
            assert len(tracker.all_features()) == 1
            assert features_file.exists()

            # Verify file content
            data = json.loads(features_file.read_text())
            assert len(data["features"]) == 1
            assert data["features"][0]["description"] == "用户注册"

    def test_get_next_ready(self, tmp_path):
        features_file = tmp_path / "features.json"
        with patch("core.feature_tracker.FEATURES_FILE", features_file):
            tracker = FeatureTracker()
            tracker.add(Feature(
                id="F001", category="auth", description="用户注册",
                priority="P0", assigned_to="backend", test_steps=["step1"],
            ))
            tracker.add(Feature(
                id="F002", category="auth", description="用户登录",
                priority="P1", assigned_to="backend",
                test_steps=["step1"], dependencies=["F001"],
            ))

            next_feature = tracker.get_next_ready()
            assert next_feature.id == "F001"

            tracker.mark_done("F001")
            next_feature = tracker.get_next_ready()
            assert next_feature.id == "F002"

    def test_status_summary(self, tmp_path):
        features_file = tmp_path / "features.json"
        with patch("core.feature_tracker.FEATURES_FILE", features_file):
            tracker = FeatureTracker()
            tracker.add(Feature(
                id="F001", category="auth", description="注册",
                priority="P0", assigned_to="backend", test_steps=["step"],
            ))
            tracker.add(Feature(
                id="F002", category="auth", description="登录",
                priority="P1", assigned_to="frontend", test_steps=["step"],
            ))
            tracker.mark_done("F001")
            tracker.mark_in_progress("F002")

            summary = tracker.summary()
            assert summary["total"] == 2
            assert summary["done"] == 1
            assert summary["in_progress"] == 1
            assert summary["pending"] == 0

    def test_bulk_add(self, tmp_path):
        features_file = tmp_path / "features.json"
        with patch("core.feature_tracker.FEATURES_FILE", features_file):
            tracker = FeatureTracker()
            features = [
                Feature(
                    id=f"F{i:03d}", category="test",
                    description=f"Feature {i}", priority="P0",
                    assigned_to="backend", test_steps=["step"],
                )
                for i in range(1, 6)
            ]
            tracker.bulk_add(features)
            assert len(tracker.all_features()) == 5


class TestTaskQueue:
    def test_enqueue_dequeue(self, tmp_path):
        db_path = tmp_path / "test_tasks.db"
        with patch("core.task_queue.TASK_DB", db_path):
            queue = TaskQueue()
            queue.enqueue("F001", "backend", "实现注册API", priority=1)
            queue.enqueue("F002", "frontend", "注册页面", priority=2)

            task = queue.dequeue()
            assert task is not None
            assert task["feature_id"] == "F002"  # higher priority first

    def test_complete_and_fail(self, tmp_path):
        db_path = tmp_path / "test_tasks.db"
        with patch("core.task_queue.TASK_DB", db_path):
            queue = TaskQueue()
            task_id = queue.enqueue("F001", "backend", "实现API")
            queue.complete(task_id, json.dumps({"files": ["api.py"]}))

            stats = queue.stats()
            assert stats["completed"] == 1

    def test_auto_retry(self, tmp_path):
        db_path = tmp_path / "test_tasks.db"
        with patch("core.task_queue.TASK_DB", db_path):
            queue = TaskQueue()
            task_id = queue.enqueue("F001", "backend", "实现API")
            queue.fail(task_id, "some error")

            # Should be re-queued (max_retries=3 by default)
            task = queue.dequeue()
            assert task is not None
            assert task["retry_count"] == 1


class TestProgressLogger:
    def test_log_and_read(self, tmp_path):
        log_file = tmp_path / "test_progress.txt"
        with patch("core.progress_logger.PROGRESS_FILE", log_file):
            logger = ProgressLogger()
            logger.log("项目启动")
            logger.log("需求分析完成")
            logger.log("F001 完成")

            lines = logger.tail(10)
            assert len(lines) == 3
            assert "项目启动" in lines[0]

    def test_tail(self, tmp_path):
        log_file = tmp_path / "test_progress.txt"
        with patch("core.progress_logger.PROGRESS_FILE", log_file):
            logger = ProgressLogger()
            for i in range(20):
                logger.log(f"进度 {i}")

            last_5 = logger.tail(5)
            assert len(last_5) == 5
            assert "进度 19" in last_5[-1]

    def test_empty_log(self, tmp_path):
        log_file = tmp_path / "test_progress.txt"
        with patch("core.progress_logger.PROGRESS_FILE", log_file):
            logger = ProgressLogger()
            lines = logger.tail(10)
            assert lines == []
