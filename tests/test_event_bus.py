import json
from pathlib import Path

import pytest

from dashboard.event_bus import Event, EventBus


@pytest.fixture
def tmp_log_file(tmp_path: Path) -> Path:
    return tmp_path / "events.log"


@pytest.fixture
def bus(tmp_log_file: Path) -> EventBus:
    return EventBus(log_file=tmp_log_file)


def test_emit_adds_to_queue(bus: EventBus):
    bus.emit("agent_status_changed", agent_id="backend-1", feature_id="F001")
    events = bus.get_events()
    assert len(events) == 1
    assert events[0]["type"] == "agent_status_changed"
    assert events[0]["agent_id"] == "backend-1"


def test_emit_appends_to_log_file(bus: EventBus, tmp_log_file: Path):
    bus.emit("agent_log", agent_id="backend-1", feature_id="F001", message="test")
    lines = tmp_log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "agent_log"
    assert event["message"] == "test"


def test_get_events_since_timestamp(bus: EventBus):
    import time
    bus.emit("type1", data="first")
    time.sleep(0.1)
    cutoff = Event.now_iso()
    time.sleep(0.1)
    bus.emit("type2", data="second")
    recent = bus.get_events_since(cutoff)
    assert len(recent) == 1
    assert recent[0]["type"] == "type2"


def test_clear_log_file(bus: EventBus, tmp_log_file: Path):
    bus.emit("type1")
    bus.clear_log()
    assert not tmp_log_file.exists() or tmp_log_file.read_text().strip() == ""


def test_load_events_from_file(bus: EventBus, tmp_log_file: Path):
    tmp_log_file.write_text(json.dumps({"type": "old_event"}) + "\n")
    events = bus.load_recent_events(n=10)
    assert len(events) == 1
    assert events[0]["type"] == "old_event"
