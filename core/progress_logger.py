"""进度日志 - 持久化所有操作记录"""

import threading
from datetime import datetime
from pathlib import Path

from core.config import PROGRESS_FILE


class ProgressLogger:
    """线程安全的进度日志记录器"""

    def __init__(self, log_file: Path | None = None):
        self._lock = threading.Lock()
        self._log_file = log_file

    def log(self, message: str) -> None:
        """追加一行进度日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        log_file = self._log_file or PROGRESS_FILE
        with self._lock:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

    def read(self) -> str:
        """读取全部进度日志"""
        log_file = self._log_file or PROGRESS_FILE
        if not log_file.exists():
            return ""
        return log_file.read_text(encoding="utf-8")

    def tail(self, n: int = 20) -> list[str]:
        """读取最后N行"""
        log_file = self._log_file or PROGRESS_FILE
        if not log_file.exists():
            return []
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        return lines[-n:]


progress = ProgressLogger()
