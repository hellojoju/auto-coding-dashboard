"""任务队列 - SQLite-backed任务管理

.. deprecated::
    Phase 3 重构后，TaskQueue 不再被 ProjectManager 使用。
    Feature 状态和命令由 ProjectStateRepository 统一管理。
    本模块仅保留以兼容可能的外部引用，将在未来版本中移除。
"""

import json
import sqlite3
import warnings
from datetime import datetime
from enum import Enum
from pathlib import Path

from core.config import TASK_DB


class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class TaskQueue:
    """基于SQLite的任务队列。

    .. deprecated::
        不再被 ProjectManager 使用。Feature 状态由 ProjectStateRepository 管理。
    """

    def __init__(self, db_path: Path | None = None):
        warnings.warn(
            "TaskQueue is deprecated. Use ProjectStateRepository for feature state management.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._db = db_path or TASK_DB
        self._init_db()

    def _init_db(self) -> None:
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    feature_id TEXT,
                    agent_type TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'queued',
                    priority INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_log TEXT DEFAULT '[]',
                    result TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    completed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    agent_type TEXT,
                    message TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            conn.commit()

    def enqueue(
        self,
        feature_id: str,
        agent_type: str,
        description: str,
        priority: int = 0,
    ) -> str:
        task_id = f"task-{feature_id}-{agent_type}"
        now = datetime.now().isoformat()
        with sqlite3.connect(str(self._db)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (id, feature_id, agent_type, description, status, priority, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)""",
                (task_id, feature_id, agent_type, description, priority, now, now),
            )
            conn.commit()
        return task_id

    def dequeue(self) -> dict | None:
        """取出优先级最高的queued任务"""
        with sqlite3.connect(str(self._db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM tasks
                   WHERE status = 'queued'
                   ORDER BY priority DESC, created_at ASC
                   LIMIT 1"""
            )
            row = cursor.fetchone()
            if not row:
                return None

            task = dict(row)
            task["error_log"] = json.loads(task["error_log"])
            conn.execute(
                """UPDATE tasks SET status = 'running', updated_at = ?
                   WHERE id = ?""",
                (datetime.now().isoformat(), task["id"]),
            )
            conn.commit()
            return task

    def complete(self, task_id: str, result: str) -> None:
        now = datetime.now().isoformat()
        with sqlite3.connect(str(self._db)) as conn:
            conn.execute(
                """UPDATE tasks SET status = 'completed', result = ?,
                   completed_at = ?, updated_at = ? WHERE id = ?""",
                (result, now, now, task_id),
            )
            conn.commit()

    def fail(self, task_id: str, error: str) -> bool:
        """失败，如果retry_count < max_retries则自动重试"""
        with sqlite3.connect(str(self._db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return False

            retry_count = row["retry_count"] + 1
            error_log = json.loads(row["error_log"])
            error_log.append({"error": error, "at": datetime.now().isoformat()})

            if retry_count < row["max_retries"]:
                conn.execute(
                    """UPDATE tasks SET status = 'queued', retry_count = ?,
                       error_log = ?, updated_at = ? WHERE id = ?""",
                    (retry_count, json.dumps(error_log), datetime.now().isoformat(), task_id),
                )
                conn.commit()
                return True  # 会自动重试
            else:
                conn.execute(
                    """UPDATE tasks SET status = 'failed', retry_count = ?,
                       error_log = ?, updated_at = ? WHERE id = ?""",
                    (retry_count, json.dumps(error_log), datetime.now().isoformat(), task_id),
                )
                conn.commit()
                return False  # 彻底失败

    def add_feedback(self, task_id: str, agent_type: str, message: str) -> None:
        with sqlite3.connect(str(self._db)) as conn:
            conn.execute(
                """INSERT INTO agent_feedback (task_id, agent_type, message, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (task_id, agent_type, message, datetime.now().isoformat()),
            )
            conn.commit()

    def get_feedback(self, task_id: str) -> list[dict]:
        with sqlite3.connect(str(self._db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM agent_feedback WHERE task_id = ? ORDER BY timestamp",
                (task_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def stats(self) -> dict:
        with sqlite3.connect(str(self._db)) as conn:
            cursor = conn.execute(
                """SELECT status, COUNT(*) as count FROM tasks GROUP BY status"""
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
