"""Dashboard 数据模型：AgentInstance, Feature, Command, Event, Snapshot, ChatMessage, DashboardState。"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class AgentInstance:
    """单个 Agent 实例的状态。"""
    id: str
    role: str
    instance_number: int
    status: str = "idle"  # idle|busy|paused|error|waiting_approval|waiting_pm
    current_feature: str | None = None
    workspace_id: str = ""
    workspace_path: str = ""
    total_tasks_completed: int = 0
    started_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "instance_number": self.instance_number,
            "status": self.status,
            "current_feature": self.current_feature,
            "workspace_id": self.workspace_id,
            "workspace_path": self.workspace_path,
            "total_tasks_completed": self.total_tasks_completed,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentInstance":
        return cls(
            id=data["id"],
            role=data["role"],
            instance_number=data["instance_number"],
            status=data.get("status", "idle"),
            current_feature=data.get("current_feature"),
            workspace_id=data.get("workspace_id", ""),
            workspace_path=data.get("workspace_path", ""),
            total_tasks_completed=data.get("total_tasks_completed", 0),
            started_at=data.get("started_at", _now_iso()),
        )


@dataclass
class Feature:
    """单个功能/任务卡片。"""
    id: str
    category: str
    description: str
    priority: str = "P1"
    assigned_to: str = ""
    assigned_instance: str = ""
    status: str = "pending"  # pending|in_progress|review|done|blocked
    passes: bool = False
    test_steps: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    workspace_id: str = ""
    files_changed: list[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    error_log: list[str] = field(default_factory=list)

    blocking_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "priority": self.priority,
            "assigned_to": self.assigned_to,
            "assigned_instance": self.assigned_instance,
            "status": self.status,
            "passes": self.passes,
            "test_steps": self.test_steps,
            "dependencies": self.dependencies,
            "workspace_id": self.workspace_id,
            "files_changed": self.files_changed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_log": self.error_log,
            "blocking_issues": self.blocking_issues,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Feature":
        return cls(
            id=data["id"],
            category=data["category"],
            description=data["description"],
            priority=data.get("priority", "P1"),
            assigned_to=data.get("assigned_to", ""),
            assigned_instance=data.get("assigned_instance", ""),
            status=data.get("status", "pending"),
            passes=data.get("passes", False),
            test_steps=data.get("test_steps", []),
            dependencies=data.get("dependencies", []),
            workspace_id=data.get("workspace_id", ""),
            files_changed=data.get("files_changed", []),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            error_log=data.get("error_log", []),
            blocking_issues=data.get("blocking_issues", []),
        )


@dataclass
class Command:
    """用户/前端发出的控制命令。"""
    schema_version: int = 1
    command_id: str = ""
    project_id: str = ""
    run_id: str = ""
    type: str = ""
    target_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    issued_by: str = "user"
    issued_at: str = ""
    updated_at: str = ""
    status: str = "pending"  # pending|accepted|applied|rejected|failed|cancelled
    result: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "type": self.type,
            "target_id": self.target_id,
            "payload": self.payload,
            "issued_by": self.issued_by,
            "issued_at": self.issued_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "result": self.result,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Command":
        return cls(
            schema_version=data.get("schema_version", 1),
            command_id=data.get("command_id", ""),
            project_id=data.get("project_id", ""),
            run_id=data.get("run_id", ""),
            type=data.get("type", ""),
            target_id=data.get("target_id", ""),
            payload=data.get("payload", {}),
            issued_by=data.get("issued_by", "user"),
            issued_at=data.get("issued_at", ""),
            updated_at=data.get("updated_at", ""),
            status=data.get("status", "pending"),
            result=data.get("result", {}),
            idempotency_key=data.get("idempotency_key", ""),
        )


@dataclass
class Event:
    """系统产出的事实事件，带单调递增 event_id。"""
    schema_version: int = 1
    event_id: int = 0
    project_id: str = ""
    run_id: str = ""
    type: str = ""
    timestamp: str = field(default_factory=_now_iso)
    caused_by_command_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "type": self.type,
            "timestamp": self.timestamp,
            "caused_by_command_id": self.caused_by_command_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(
            schema_version=data.get("schema_version", 1),
            event_id=data.get("event_id", 0),
            project_id=data.get("project_id", ""),
            run_id=data.get("run_id", ""),
            type=data["type"],
            timestamp=data.get("timestamp", _now_iso()),
            caused_by_command_id=data.get("caused_by_command_id"),
            payload=data.get("payload", {}),
        )


@dataclass
class ChatMessage:
    """PM 对话消息。"""
    id: str
    role: str  # user|pm
    content: str
    timestamp: str = field(default_factory=_now_iso)
    action_triggered: str = ""  # approve|reject|override|""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "action_triggered": self.action_triggered,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        return cls(
            id=data["id"],
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", _now_iso()),
            action_triggered=data.get("action_triggered", ""),
        )


@dataclass
class ModuleAssignment:
    """同角色多 Agent 的模块分配记录。

    例如两个后端 agent：backend-1 负责 auth + user 模块，backend-2 负责 order + payment 模块。
    """
    module_id: str                          # 模块唯一标识，如 "backend-auth"
    role: str                               # 角色，如 "backend"
    assigned_agent_id: str = ""             # 分配的 agent 实例 ID
    module_name: str = ""                   # 模块人类可读名称
    description: str = ""                   # 模块职责描述
    dependencies: list[str] = field(default_factory=list)  # 依赖的其他 module_id
    status: str = "pending"                 # pending | in_progress | blocked | completed
    interface_contract: dict[str, Any] = field(default_factory=dict)  # 接口契约描述

    def to_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "role": self.role,
            "assigned_agent_id": self.assigned_agent_id,
            "module_name": self.module_name,
            "description": self.description,
            "dependencies": self.dependencies,
            "status": self.status,
            "interface_contract": self.interface_contract,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleAssignment":
        return cls(
            module_id=data["module_id"],
            role=data["role"],
            assigned_agent_id=data.get("assigned_agent_id", ""),
            module_name=data.get("module_name", ""),
            description=data.get("description", ""),
            dependencies=data.get("dependencies", []),
            status=data.get("status", "pending"),
            interface_contract=data.get("interface_contract", {}),
        )


@dataclass
class Snapshot:
    """项目状态快照，用于前端初始加载和断线重连。"""
    schema_version: int = 1
    project_id: str = ""
    run_id: str = ""
    snapshot_version: int = 0
    last_event_id: int = 0
    project_name: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    agents: list[AgentInstance] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    chat_history: list[ChatMessage] = field(default_factory=list)
    module_assignments: list[ModuleAssignment] = field(default_factory=list)
    blocking_issues: list["BlockingIssue"] = field(default_factory=list)
    approval_requests: list["ApprovalRequest"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "snapshot_version": self.snapshot_version,
            "last_event_id": self.last_event_id,
            "project_name": self.project_name,
            "summary": self.summary,
            "agents": [a.to_dict() for a in self.agents],
            "features": [f.to_dict() for f in self.features],
            "pending_approvals": self.pending_approvals,
            "chat_history": [m.to_dict() for m in self.chat_history],
            "module_assignments": [m.to_dict() for m in self.module_assignments],
            "blocking_issues": [i.to_dict() for i in self.blocking_issues],
            "approval_requests": [a.to_dict() for a in self.approval_requests],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(
            schema_version=data.get("schema_version", 1),
            project_id=data.get("project_id", ""),
            run_id=data.get("run_id", ""),
            snapshot_version=data.get("snapshot_version", 0),
            last_event_id=data.get("last_event_id", 0),
            project_name=data.get("project_name", ""),
            summary=data.get("summary", {}),
            agents=[AgentInstance.from_dict(a) for a in data.get("agents", [])],
            features=[Feature.from_dict(f) for f in data.get("features", [])],
            pending_approvals=data.get("pending_approvals", []),
            chat_history=[ChatMessage.from_dict(m) for m in data.get("chat_history", [])],
            module_assignments=[ModuleAssignment.from_dict(m) for m in data.get("module_assignments", [])],
            blocking_issues=[BlockingIssue.from_dict(i) for i in data.get("blocking_issues", [])],
            approval_requests=[ApprovalRequest.from_dict(a) for a in data.get("approval_requests", [])],
        )




@dataclass
class DashboardState:
    """看板完整状态快照，用于前端初始加载和断线重连。"""
    agents: list[AgentInstance] = field(default_factory=list)
    features: list[dict] = field(default_factory=list)
    chat_history: list[ChatMessage] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    project_name: str = ""

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "agents": [a.to_dict() for a in self.agents],
            "features": self.features,
            "chat_history": [m.to_dict() for m in self.chat_history],
            "events": self.events,
        }


@dataclass
class BlockingIssue:
    """阻塞问题，作为一等公民对象。"""
    issue_id: str = ""
    issue_type: str = ""  # missing_env, missing_credentials, external_service_down, \
    # dependency_not_met, code_error, resource_exhausted
    feature_id: str = ""
    detected_by: str = ""  # coordinator, agent, verification
    detected_at: str = field(default_factory=_now_iso)
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: str = ""
    resolution: str = ""

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "feature_id": self.feature_id,
            "detected_by": self.detected_by,
            "detected_at": self.detected_at,
            "description": self.description,
            "context": self.context,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlockingIssue":
        return cls(
            issue_id=data.get("issue_id", ""),
            issue_type=data.get("issue_type", ""),
            feature_id=data.get("feature_id", ""),
            detected_by=data.get("detected_by", ""),
            detected_at=data.get("detected_at", _now_iso()),
            description=data.get("description", ""),
            context=data.get("context", {}),
            resolved=data.get("resolved", False),
            resolved_at=data.get("resolved_at", ""),
            resolution=data.get("resolution", ""),
        )


@dataclass
class ApprovalRequest:
    """独立审批请求对象，与 Command 是 1:N 关系。"""
    approval_id: str = ""
    command_id: str = ""
    project_id: str = ""
    run_id: str = ""
    artifact_type: str = ""
    artifact_ref: str = ""
    artifact_version: int = 1
    status: str = "pending"
    reviewer: str = "user"
    created_at: str = field(default_factory=_now_iso)
    expires_at: str = ""
    feedback: str = ""

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "command_id": self.command_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "artifact_type": self.artifact_type,
            "artifact_ref": self.artifact_ref,
            "artifact_version": self.artifact_version,
            "status": self.status,
            "reviewer": self.reviewer,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRequest":
        return cls(
            approval_id=data.get("approval_id", ""),
            command_id=data.get("command_id", ""),
            project_id=data.get("project_id", ""),
            run_id=data.get("run_id", ""),
            artifact_type=data.get("artifact_type", ""),
            artifact_ref=data.get("artifact_ref", ""),
            artifact_version=data.get("artifact_version", 1),
            status=data.get("status", "pending"),
            reviewer=data.get("reviewer", "user"),
            created_at=data.get("created_at", _now_iso()),
            expires_at=data.get("expires_at", ""),
            feedback=data.get("feedback", ""),
        )
