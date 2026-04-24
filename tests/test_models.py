import pytest
from dashboard.models import AgentInstance, ApprovalRequest, ChatMessage, Command, DashboardState


def test_agent_instance_roundtrip():
    agent = AgentInstance(
        id="backend-1",
        role="backend",
        instance_number=1,
        status="busy",
        current_feature="F004",
        total_tasks_completed=5,
    )
    data = agent.to_dict()
    restored = AgentInstance.from_dict(data)
    assert restored.id == agent.id
    assert restored.status == agent.status
    assert restored.current_feature == agent.current_feature


def test_chat_message_roundtrip():
    msg = ChatMessage(
        id="chat_001",
        role="user",
        content="F007 先不做支付，改成做积分系统",
        action_triggered="override",
    )
    data = msg.to_dict()
    restored = ChatMessage.from_dict(data)
    assert restored.content == msg.content
    assert restored.action_triggered == msg.action_triggered


def test_dashboard_state_serialization():
    state = DashboardState(
        project_name="Test Project",
        agents=[AgentInstance(id="backend-1", role="backend", instance_number=1)],
        features=[{"id": "F001", "status": "done"}],
        chat_history=[ChatMessage(id="c1", role="pm", content="Ready")],
        events=[{"type": "agent_log"}],
    )
    data = state.to_dict()
    assert data["project_name"] == "Test Project"
    assert len(data["agents"]) == 1
    assert len(data["features"]) == 1
    assert len(data["chat_history"]) == 1
    assert len(data["events"]) == 1


def test_approval_request_serialization():
    appr = ApprovalRequest(
        approval_id="appr_001",
        command_id="cmd_001",
        artifact_type="prd",
        status="pending",
        reviewer="user",
    )
    data = appr.to_dict()
    assert data["approval_id"] == "appr_001"
    assert data["status"] == "pending"
    assert data["artifact_version"] == 1


def test_approval_request_from_dict():
    data = {
        "approval_id": "appr_002",
        "command_id": "cmd_002",
        "artifact_type": "code_output",
        "status": "approved",
        "artifact_version": 2,
    }
    appr = ApprovalRequest.from_dict(data)
    assert appr.approval_id == "appr_002"
    assert appr.artifact_version == 2
    assert appr.feedback == ""


def test_command_has_idempotency_key():
    cmd = Command(command_id="cmd_001", type="approve", idempotency_key="uuid-123")
    data = cmd.to_dict()
    assert data["idempotency_key"] == "uuid-123"

    restored = Command.from_dict(data)
    assert restored.idempotency_key == "uuid-123"
