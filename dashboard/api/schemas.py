"""前后端契约的 Pydantic 模型，用于 API 请求/响应验证。"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


# ─── 请求体 ───────────────────────────────────────────────

class CreateCommandRequest(BaseModel):
    """POST /api/dashboard/commands 请求体。"""
    project_id: str = "default"
    run_id: str = ""
    type: str
    target_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    issued_by: str = "user"


class ChatMessageRequest(BaseModel):
    """POST /api/chat 请求体。"""
    project_id: str = "default"
    run_id: str = ""
    content: str


class LegacyControlRequest(BaseModel):
    """旧版控制接口请求体（approve/reject/pause/resume/retry/skip）。"""
    project_id: str = "default"
    run_id: str = ""
    target_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


# ─── 响应体 ───────────────────────────────────────────────

class CommandResponse(BaseModel):
    """命令创建/查询响应。"""
    schema_version: int = 1
    command_id: str
    status: str
    type: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class AgentInstanceResponse(BaseModel):
    """Agent 实例状态。"""
    id: str
    role: str
    instance_number: int
    status: str
    current_feature: str | None = None
    workspace_id: str = ""
    workspace_path: str = ""
    total_tasks_completed: int = 0
    started_at: str = ""


class FeatureResponse(BaseModel):
    """功能卡片状态。"""
    id: str
    category: str
    description: str
    priority: str = "P1"
    assigned_to: str = ""
    assigned_instance: str = ""
    status: str = "pending"
    dependencies: list[str] = Field(default_factory=list)
    workspace_id: str = ""
    files_changed: list[str] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    error_log: list[str] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    """PM 对话消息。"""
    id: str
    role: str
    content: str
    timestamp: str
    action_triggered: str = ""


class SnapshotResponse(BaseModel):
    """GET /api/dashboard/state 响应。"""
    schema_version: int = 1
    project_id: str
    run_id: str
    snapshot_version: int = 0
    last_event_id: int = 0
    project_name: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    agents: list[AgentInstanceResponse] = Field(default_factory=list)
    features: list[FeatureResponse] = Field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = Field(default_factory=list)
    chat_history: list[ChatMessageResponse] = Field(default_factory=list)


class EventResponse(BaseModel):
    """事件增量响应。"""
    schema_version: int = 1
    project_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)


class WebSocketHelloResponse(BaseModel):
    """WebSocket 握手消息。"""
    type: str = "hello"
    schema_version: int = 1
    project_id: str
    last_event_id: int = 0
    agents: list[AgentInstanceResponse] = Field(default_factory=list)
    features: list[FeatureResponse] = Field(default_factory=list)
    chat_history: list[ChatMessageResponse] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """通用错误响应。"""
    detail: str
