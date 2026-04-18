"""Dashboard 数据模型：AgentInstance, Feature, Command, Event, Snapshot, ChatMessage, DashboardState。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    dependencies: list[str] = field(default_factory=list)
    workspace_id: str = ""
    files_changed: list[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    error_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "priority": self.priority,
            "assigned_to": self.assigned_to,
            "assigned_instance": self.assigned_instance,
            "status": self.status,
            "dependencies": self.dependencies,
            "workspace_id": self.workspace_id,
            "files_changed": self.files_changed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_log": self.error_log,
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
            dependencies=data.get("dependencies", []),
            workspace_id=data.get("workspace_id", ""),
            files_changed=data.get("files_changed", []),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            error_log=data.get("error_log", []),
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
