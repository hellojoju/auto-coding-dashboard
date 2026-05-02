"""SilenceDetector 测试。"""

import time

import pytest

from dashboard.silence_detector import SilenceDetector


def _make_detector(
    warning=0.5,
    notify=1.0,
    intervention=1.5,
    poll=0.1,
    **callbacks,
) -> SilenceDetector:
    """创建极低阈值的检测器，避免测试等待。"""
    return SilenceDetector(
        agent_id="test-agent-1",
        warning_threshold=warning,
        notify_threshold=notify,
        intervention_threshold=intervention,
        poll_interval=poll,
        **callbacks,
    )


def test_initial_state_is_active():
    detector = _make_detector()
    status = detector.get_status()
    assert status["level"] == "active"
    assert status["idle_seconds"] == pytest.approx(0, abs=0.01)
    assert not status["running"]


def test_record_activity_resets_idle():
    detector = _make_detector()
    time.sleep(0.3)
    detector.record_activity()
    assert detector.get_idle_seconds() == pytest.approx(0, abs=0.01)


def test_warning_callback_fires():
    events = []
    detector = _make_detector(on_warning=lambda aid, idle: events.append(("warning", aid, idle)))
    detector.start()
    try:
        time.sleep(0.8)
    finally:
        detector.stop()
    assert len(events) >= 1
    assert events[0][0] == "warning"
    assert events[0][1] == "test-agent-1"


def test_notify_callback_fires():
    events = []
    detector = _make_detector(on_notify=lambda aid, idle: events.append(("notify", aid, idle)))
    detector.start()
    try:
        time.sleep(1.3)
    finally:
        detector.stop()
    assert len(events) >= 1
    assert events[0][0] == "notify"


def test_intervention_callback_fires():
    events = []
    detector = _make_detector(on_intervention=lambda aid, idle: events.append(("intervention", aid, idle)))
    detector.start()
    try:
        time.sleep(1.8)
    finally:
        detector.stop()
    assert len(events) >= 1
    assert events[0][0] == "intervention"


def test_record_activity_during_warning_resets():
    """在 warning 级别前记录活动应重置为 active。"""
    events = []
    detector = _make_detector(
        warning=0.3,
        notify=0.6,
        intervention=0.9,
        poll=0.1,
        on_warning=lambda aid, idle: events.append("warning"),
        on_notify=lambda aid, idle: events.append("notify"),
    )
    detector.start()
    try:
        time.sleep(0.4)  # 超过 warning 阈值
        detector.record_activity()  # 重置
        time.sleep(0.4)  # 只到达 warning 以下
    finally:
        detector.stop()
    # warning 可能触发 0 或 1 次，但 notify 不应该触发（因为被重置了）
    assert "notify" not in events
