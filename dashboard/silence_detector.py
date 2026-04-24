"""静默检测器：监控 Agent 活动间隔，分级触发警告/通知/干预。"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from core.config import (
    AGENT_POLL_INTERVAL,
    SILENCE_INTERVENTION_THRESHOLD,
    SILENCE_NOTIFY_THRESHOLD,
    SILENCE_WARNING_THRESHOLD,
)

logger = logging.getLogger(__name__)


class SilenceDetector:
    """监控单个 Agent 的活动间隔，按阈值分级触发回调。"""

    def __init__(
        self,
        agent_id: str,
        on_warning: Callable[[str, int], None] | None = None,
        on_notify: Callable[[str, int], None] | None = None,
        on_intervention: Callable[[str, int], None] | None = None,
        warning_threshold: float = SILENCE_WARNING_THRESHOLD,
        notify_threshold: float = SILENCE_NOTIFY_THRESHOLD,
        intervention_threshold: float = SILENCE_INTERVENTION_THRESHOLD,
        poll_interval: float = AGENT_POLL_INTERVAL,
    ) -> None:
        self.agent_id = agent_id
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()
        self._running = False
        self._thread: threading.Thread | None = None
        self._current_level = "active"  # active | warning | notify | intervention
        self._activity_reset = False  # 标记 record_activity 是否被调用

        self.on_warning = on_warning
        self.on_notify = on_notify
        self.on_intervention = on_intervention

        self.warning_threshold = warning_threshold
        self.notify_threshold = notify_threshold
        self.intervention_threshold = intervention_threshold
        self.poll_interval = poll_interval

    def record_activity(self) -> None:
        """记录一次活动，重置计时器。"""
        with self._lock:
            self._last_activity = time.monotonic()
            self._current_level = "active"
            self._activity_reset = True

    def get_idle_seconds(self) -> float:
        """获取空闲秒数。"""
        return time.monotonic() - self._last_activity

    def get_status(self) -> dict:
        """返回当前检测状态。"""
        return {
            "agent_id": self.agent_id,
            "idle_seconds": self.get_idle_seconds(),
            "level": self._current_level,
            "running": self._running,
        }

    def start(self) -> None:
        """启动后台轮询线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name=f"silence-detector-{self.agent_id}",
        )
        self._thread.start()

    def stop(self) -> None:
        """停止检测。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _poll_loop(self) -> None:
        """轮询循环，按顺序触发所有已过的级别。"""
        fired_warning = False
        fired_notify = False
        fired_intervention = False

        while self._running:
            idle = self.get_idle_seconds()

            # 从低到高检查，确保跨越多级阈值时每个级别都能触发
            if idle >= self.warning_threshold and not fired_warning:
                fired_warning = True
                self._current_level = "warning"
                if self.on_warning:
                    try:
                        self.on_warning(self.agent_id, idle)
                    except Exception:
                        logger.exception("on_warning callback error")

            if idle >= self.notify_threshold and not fired_notify:
                fired_notify = True
                self._current_level = "notify"
                if self.on_notify:
                    try:
                        self.on_notify(self.agent_id, idle)
                    except Exception:
                        logger.exception("on_notify callback error")

            if idle >= self.intervention_threshold and not fired_intervention:
                fired_intervention = True
                self._current_level = "intervention"
                if self.on_intervention:
                    try:
                        self.on_intervention(self.agent_id, idle)
                    except Exception:
                        logger.exception("on_intervention callback error")

            # 活动重置：record_activity 被调用时重置所有标记
            if self._activity_reset:
                self._activity_reset = False
                fired_warning = False
                fired_notify = False
                fired_intervention = False
                self._current_level = "active"

            time.sleep(self.poll_interval)
