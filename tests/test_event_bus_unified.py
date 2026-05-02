"""EventBus 与 Repository 统一事件流测试。

验证 EventBus.emit() 在提供 repository 时将事件写入 Repository，
同时保持内存队列和向后兼容性。
"""

from pathlib import Path

import pytest

from dashboard.event_bus import EventBus
from dashboard.models import Event
from dashboard.state_repository import ProjectStateRepository


@pytest.fixture()
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(base_dir=tmp_path, project_id="test", run_id="r1")


@pytest.fixture()
def event_log(tmp_path: Path) -> Path:
    return tmp_path / "events.log"


class TestEventBusWithRepository:
    """EventBus 提供 repository 时的行为。"""

    def test_emit_writes_to_repository(self, repo: ProjectStateRepository) -> None:
        bus = EventBus(repository=repo)
        bus.emit("test_event", key="value")

        events = repo.get_events_after(0)
        assert len(events) == 1
        assert events[0].type == "test_event"
        assert events[0].payload == {"key": "value"}

    def test_emit_appends_to_queue(self, repo: ProjectStateRepository) -> None:
        bus = EventBus(repository=repo)
        bus.emit("event_a")
        bus.emit("event_b")

        queue_items = bus.get_events()
        assert len(queue_items) == 2
        assert queue_items[0]["type"] == "event_a"
        assert queue_items[1]["type"] == "event_b"

    def test_log_file_not_written_when_repository_provided(
        self, repo: ProjectStateRepository, event_log: Path
    ) -> None:
        bus = EventBus(log_file=event_log, repository=repo)
        bus.emit("test_event")

        # 有 repository 时不应写日志文件
        assert not event_log.exists()

    def test_get_events_since(self, repo: ProjectStateRepository) -> None:
        bus = EventBus(repository=repo)
        bus.emit("before")
        bus.emit("after")

        events = bus.get_events()
        # 取第二个事件的时间戳
        ts = events[-1]["timestamp"]
        after = bus.get_events_since(ts)
        assert len(after) == 0  # 严格大于

    def test_load_recent_empty(self, repo: ProjectStateRepository) -> None:
        bus = EventBus(repository=repo)
        # 没有日志文件时应返回空
        assert bus.load_recent_events() == []


class TestEventBusWithoutRepository:
    """EventBus 没有 repository 时的向后兼容行为。"""

    def test_emit_writes_to_log_file(self, event_log: Path) -> None:
        bus = EventBus(log_file=event_log)
        bus.emit("test_event", data=123)

        lines = event_log.read_text().strip().split("\n")
        assert len(lines) == 1
        import json
        parsed = json.loads(lines[0])
        assert parsed["type"] == "test_event"
        assert parsed["data"] == 123

    def test_emit_appends_to_queue(self, event_log: Path) -> None:
        bus = EventBus(log_file=event_log)
        bus.emit("event_a")
        bus.emit("event_b")

        queue_items = bus.get_events()
        assert len(queue_items) == 2

    def test_no_repository_fallback_gracefully(self) -> None:
        bus = EventBus()  # 无 log_file 无 repository
        bus.emit("orphan_event")
        # 不应报错，仅写入内存队列
        assert len(bus.get_events()) == 1
