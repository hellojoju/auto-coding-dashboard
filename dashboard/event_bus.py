"""EventBus: 内存队列 + 文件持久化，用于 Dashboard 实时推送。"""

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class Event:
    type: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    data: dict = field(default_factory=dict)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return {"type": self.type, "timestamp": self.timestamp, **self.data}


class AgentEventTypes:
    """Agent 集群事件类型常量。"""
    AGENT_STATUS_CHANGED = "agent_status_changed"        # Agent 状态变更
    AGENT_ACTIVITY = "agent_activity"                     # Agent 活动更新
    AGENT_SILENCE_WARNING = "agent_silence_warning"       # 静默警告
    AGENT_SILENCE_NOTIFY = "agent_silence_notify"         # 静默通知
    AGENT_SILENCE_INTERVENTION = "agent_silence_intervention"  # 静默干预
    TOOL_CALL = "tool_call"                               # 工具调用
    TOOL_OUTPUT = "tool_output"                           # 工具输出
    PM_COORDINATOR_START = "pm_coordinator_start"         # 协调器启动
    PM_COORDINATOR_STOP = "pm_coordinator_stop"           # 协调器停止


class EventBus:
    """线程安全的事件总线，支持内存队列 + 文件追加写入。"""

    def __init__(self, log_file: Path | None = None, max_queue: int = 1000):
        self._lock = threading.Lock()
        self._queue: deque[dict] = deque(maxlen=max_queue)
        self._log_file = log_file
        # 项目初始化时清空日志
        if self._log_file and self._log_file.exists():
            self.clear_log()

    def emit(self, event_type: str, **kwargs: Any) -> None:
        """发布事件到内存队列并追加到日志文件。"""
        event = Event(type=event_type, data=kwargs)
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        with self._lock:
            self._queue.append(event.to_dict())
            if self._log_file:
                self._log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(payload + "\n")

    def get_events(self) -> list[dict]:
        """获取当前内存队列中的所有事件。"""
        with self._lock:
            return list(self._queue)

    def get_events_since(self, timestamp: str) -> list[dict]:
        """获取指定时间戳之后的事件。"""
        with self._lock:
            return [e for e in self._queue if e["timestamp"] > timestamp]

    def load_recent_events(self, n: int = 100) -> list[dict]:
        """从日志文件加载最近 N 条事件。"""
        if not self._log_file or not self._log_file.exists():
            return []
        lines = self._log_file.read_text(encoding="utf-8").strip().split("\n")
        lines = [ln for ln in lines if ln.strip()]
        recent = lines[-n:]
        events = []
        for line in recent:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def clear_log(self) -> None:
        """清空日志文件。"""
        if self._log_file and self._log_file.exists():
            self._log_file.unlink()
