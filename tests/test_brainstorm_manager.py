import json
from pathlib import Path
from ralph.brainstorm_manager import BrainstormManager
from ralph.schema.brainstorm_record import ConfirmedFact, OpenAssumption, UserPath


def test_start_session_creates_record(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    record = mgr.start_session("TestProject", "我想做一个 todo app")
    assert record.project_name == "TestProject"
    assert record.round_number == 1
    assert (tmp_path / ".ralph" / "brainstorm" / f"{record.record_id}.json").is_file()


def test_generate_questions_covers_topics(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    record = mgr.start_session("Test", "hello")
    questions = mgr.generate_questions(record)
    assert len(questions) > 0
    assert len(questions) <= 5


def test_process_response_updates_record(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    record = mgr.start_session("Test", "hello")
    updated = mgr.process_response(record, "给程序员用的", [
        {"type": "confirmed", "topic": "目标用户", "fact": "程序员", "source_quote": "给程序员用的"},
    ])
    assert updated.round_number == 2
    assert len(updated.confirmed_facts) == 1
    assert updated.confirmed_facts[0].topic == "目标用户"


def test_is_complete_requires_80_percent(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    record = mgr.start_session("Test", "hello")
    record.confirmed_facts.append(ConfirmedFact(topic="目标用户", fact="dev", source_quote="dev"))
    assert not mgr.is_complete(record)


def test_is_complete_passes_with_full_data(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    record = mgr.start_session("Test", "hello")
    for topic in ["目标用户", "核心功能", "验收标准"]:
        record.confirmed_facts.append(ConfirmedFact(topic=topic, fact="done", source_quote=""))
    record.user_paths.append(UserPath(name="main", steps=["step1"], edge_cases=["edge1"]))
    record.open_assumptions = []
    assert mgr.is_complete(record)


def test_list_sessions(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    mgr.start_session("P1", "hello")
    mgr.start_session("P2", "world")
    sessions = mgr.list_sessions()
    assert len(sessions) == 2


def test_load_roundtrips(tmp_path: Path):
    mgr = BrainstormManager(tmp_path / ".ralph")
    record = mgr.start_session("Test", "hello")
    loaded = mgr.load(record.record_id)
    assert loaded is not None
    assert loaded.project_name == "Test"
