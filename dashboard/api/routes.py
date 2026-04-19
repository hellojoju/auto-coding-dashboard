"""Dashboard REST API 路由和 WebSocket 端点 — 接入 ProjectStateRepository + CommandProcessor。"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dashboard.event_bus import EventBus
from dashboard.models import ChatMessage, DashboardState
from dashboard.state_repository import ProjectStateRepository
from dashboard.command_processor import CommandProcessor, InvalidTransition


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_state() -> DashboardState:
    return DashboardState()


class DashboardAppState:
    """存储在 app.state 中的可变看板状态。"""

    def __init__(self) -> None:
        self.dashboard_state = _make_state()
        self.connected_ws: set[WebSocket] = set()
        self.broadcast_queue: deque[dict] = deque()


def create_dashboard_app(
    event_bus: EventBus,
    repository: ProjectStateRepository | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Dev Dashboard")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    state = DashboardAppState()
    app.state.dashboard_state = state.dashboard_state
    app.state.event_bus = event_bus
    app.state.connected_ws = state.connected_ws
    app.state.broadcast_queue = state.broadcast_queue

    # 注入 Repository（如未提供则创建默认）
    if repository is None:
        from pathlib import Path
        repository = ProjectStateRepository(
            base_dir=Path("/tmp/dashboard_state"),
            project_id="default",
            run_id="",
        )
    app.state.repository = repository

    # 注入 CommandProcessor
    def on_event(event) -> None:
        event_bus.emit(event.type, **event.payload)

    app.state.command_processor = CommandProcessor(on_event=on_event)

    # --- REST: 状态快照 ---

    @app.get("/api/state")
    async def get_state() -> dict:
        s = app.state.dashboard_state
        return {
            "project_name": s.project_name,
            "agents": [a.to_dict() for a in s.agents],
            "features": s.features,
            "events": s.events,
            "chat_history": [m.to_dict() for m in s.chat_history],
        }

    @app.get("/api/dashboard/state")
    async def get_dashboard_state() -> dict:
        """从 Repository 加载统一快照。"""
        snapshot = app.state.repository.load_snapshot()
        return snapshot.to_dict()

    # --- REST: 事件列表 ---

    @app.get("/api/events")
    async def get_events() -> list[dict]:
        return app.state.event_bus.get_events()

    @app.get("/api/dashboard/events")
    async def get_dashboard_events(after_event_id: int = 0, limit: int = 200) -> dict:
        events = app.state.repository.get_events_after(after_event_id, limit)
        return {
            "project_id": app.state.repository._project_id,
            "events": [e.to_dict() for e in events],
        }

    # --- REST: 用户对话 ---

    @app.post("/api/chat")
    async def post_chat(body: dict[str, Any]) -> dict:
        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=422, detail="content is required")
        msg = ChatMessage(id=f"chat_{_now_iso()}", role="user", content=content)
        app.state.dashboard_state.chat_history.append(msg)
        app.state.repository.add_chat_message(msg)
        app.state.event_bus.emit("pm_decision", message=f"用户消息: {content}")
        return {"success": True, "message_id": msg.id}

    # --- REST: 批准 ---

    @app.post("/api/approve")
    async def post_approve(body: dict[str, Any] | None = None) -> dict:
        body = body or {}
        cmd = _create_command("approve_decision", body)
        try:
            app.state.command_processor.accept(cmd)
        except InvalidTransition:
            raise HTTPException(status_code=409, detail="Command cannot be accepted")
        app.state.repository.save_command(cmd)
        return {"success": True, "command_id": cmd.command_id}

    # --- REST: 驳回 ---

    @app.post("/api/reject")
    async def post_reject(body: dict[str, Any] | None = None) -> dict:
        body = body or {}
        reason = body.get("reason", "")
        cmd = _create_command("reject_decision", body)
        try:
            app.state.command_processor.reject(cmd, reason=reason)
        except InvalidTransition:
            raise HTTPException(status_code=409, detail="Command cannot be rejected")
        app.state.repository.save_command(cmd)
        return {"success": True, "command_id": cmd.command_id}

    # --- REST: 暂停 ---

    @app.post("/api/pause")
    async def post_pause(body: dict[str, Any]) -> dict:
        agent_id = body.get("agent_id", "")
        repo = app.state.repository
        snapshot = repo.load_snapshot()
        for agent in snapshot.agents:
            if agent.id == agent_id:
                agent.status = "paused"
                repo.upsert_agent(agent)
                app.state.event_bus.emit("agent_status_changed", agent_id=agent_id, message="paused")
                return {"success": True}
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # --- REST: 恢复 ---

    @app.post("/api/resume")
    async def post_resume(body: dict[str, Any]) -> dict:
        agent_id = body.get("agent_id", "")
        repo = app.state.repository
        snapshot = repo.load_snapshot()
        for agent in snapshot.agents:
            if agent.id == agent_id:
                agent.status = "idle"
                repo.upsert_agent(agent)
                app.state.event_bus.emit("agent_status_changed", agent_id=agent_id, message="idle")
                return {"success": True}
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # --- REST: 重试 ---

    @app.post("/api/retry")
    async def post_retry(body: dict[str, Any]) -> dict:
        feature_id = body.get("feature_id", "")
        app.state.event_bus.emit("retry_feature", feature_id=feature_id)
        return {"success": True}

    # --- REST: 跳过 ---

    @app.post("/api/skip")
    async def post_skip(body: dict[str, Any]) -> dict:
        feature_id = body.get("feature_id", "")
        app.state.event_bus.emit("skip_feature", feature_id=feature_id)
        return {"success": True}

    # --- REST: 命令创建（新接口）---

    @app.post("/api/dashboard/commands", status_code=202)
    async def create_command_endpoint(body: dict[str, Any]) -> dict:
        cmd = _create_command(body.get("type", ""), body)
        app.state.repository.save_command(cmd)
        return {
            "schema_version": 1,
            "command_id": cmd.command_id,
            "status": cmd.status,
        }

    @app.get("/api/dashboard/commands/{command_id}")
    async def get_command(command_id: str) -> dict:
        cmd = app.state.repository.get_command(command_id)
        if not cmd:
            raise HTTPException(status_code=404, detail="Command not found")
        return cmd.to_dict()

    # --- WebSocket: 实时推送 ---

    @app.websocket("/ws/dashboard")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        app.state.connected_ws.add(ws)
        try:
            # 发送欢迎 + 状态快照（对齐前端 WsCallbacks.onSnapshot 期望）
            snapshot = app.state.repository.load_snapshot()
            await ws.send_json({
                "type": "hello",
                "schema_version": 1,
                "project_id": app.state.repository._project_id,
                "last_event_id": snapshot.last_event_id,
                "agents": [a.to_dict() for a in snapshot.agents],
                "features": [f.to_dict() for f in snapshot.features],
                "chat_history": [m.to_dict() for m in snapshot.chat_history],
            })
            # 保持连接，轮询广播队列
            while True:
                try:
                    while app.state.broadcast_queue:
                        payload = app.state.broadcast_queue.popleft()
                        await ws.send_json(payload)
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
        except WebSocketDisconnect:
            app.state.connected_ws.discard(ws)

    # 注册广播钩子
    original_emit = event_bus.emit

    def emit_with_broadcast(event_type: str, **kwargs: Any) -> None:
        original_emit(event_type, **kwargs)
        payload = {"type": event_type, "payload": kwargs, "timestamp": _now_iso()}
        app.state.broadcast_queue.append(payload)

    event_bus.emit = emit_with_broadcast

    return app


def _create_command(cmd_type: str, body: dict[str, Any]) -> Command:
    """从请求体创建 Command 对象。"""
    from dashboard.models import Command
    return Command(
        command_id=f"cmd_{_now_iso()}",
        type=cmd_type,
        target_id=body.get("target_id", ""),
        payload=body.get("payload", {}),
        project_id=body.get("project_id", ""),
        run_id=body.get("run_id", ""),
        issued_at=_now_iso(),
    )
