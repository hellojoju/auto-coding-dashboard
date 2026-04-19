"""Dashboard REST API 路由和 WebSocket 端点 — 接入 ProjectStateRepository + CommandProcessor + CommandConsumer。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dashboard.event_bus import EventBus
from dashboard.models import ChatMessage, DashboardState, Event
from dashboard.state_repository import ProjectStateRepository
from dashboard.command_processor import CommandProcessor, InvalidTransition
from dashboard.consumer import CommandConsumer

logger = logging.getLogger(__name__)

# 前端命令类型 → 后端期望类型映射
CMD_TYPE_MAP = {
    "approve_decision": "approve",
    "reject_decision": "reject",
}


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


def _emit_to_ws(broadcast_queue: deque, event: Event) -> None:
    """将 Repository 事件推入 WebSocket 广播队列。"""
    payload = {
        "type": event.type,
        "payload": event.payload,
        "timestamp": event.timestamp or _now_iso(),
    }
    broadcast_queue.append(payload)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动 CommandConsumer 后台轮询循环。"""
    consumer: CommandConsumer = app.state.consumer
    stop_event = asyncio.Event()

    async def consumer_loop() -> None:
        while not stop_event.is_set():
            try:
                n = consumer.process_once()
                if n > 0:
                    logger.info(f"CommandConsumer processed {n} command(s)")
            except Exception:
                logger.exception("CommandConsumer error")
            await asyncio.sleep(0.5)

    task = asyncio.create_task(consumer_loop())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_dashboard_app(
    event_bus: EventBus,
    repository: ProjectStateRepository | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Dev Dashboard", lifespan=lifespan)
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

    # 注入 Repository
    if repository is None:
        from pathlib import Path
        repository = ProjectStateRepository(
            base_dir=Path("/tmp/dashboard_state"),
            project_id="default",
            run_id="",
        )
    app.state.repository = repository

    # 注入 CommandProcessor — 事件统一通过 Repository 追加
    def on_event(event_type: str, **kwargs: Any) -> None:
        event = repository.append_event(type=event_type, **kwargs)
        _emit_to_ws(app.state.broadcast_queue, event)
        # 兼容旧 EventBus（如果外部还在监听）
        event_bus.emit(event_type, **kwargs)

    processor = CommandProcessor(on_event=on_event)
    app.state.command_processor = processor

    # 注入 CommandConsumer
    app.state.consumer = CommandConsumer(
        repository=repository,
        processor=processor,
        event_bus=event_bus,
    )

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
        event = app.state.repository.append_event(
            type="pm_decision", message=f"用户消息: {content}",
        )
        _emit_to_ws(app.state.broadcast_queue, event)
        return {"success": True, "message_id": msg.id}

    # --- REST: 批准（写为 pending，由 CommandConsumer 消费）---

    @app.post("/api/approve")
    async def post_approve(body: dict[str, Any] | None = None) -> dict:
        body = body or {}
        cmd = _create_command("approve_decision", body)
        cmd.status = "pending"
        app.state.repository.save_command(cmd)
        app.state.repository.append_event(
            type="command_created", command_id=cmd.command_id, cmd_type="approve",
        )
        return {"success": True, "command_id": cmd.command_id, "status": "pending"}

    # --- REST: 驳回（写为 pending，由 CommandConsumer 消费）---

    @app.post("/api/reject")
    async def post_reject(body: dict[str, Any] | None = None) -> dict:
        body = body or {}
        cmd = _create_command("reject_decision", body)
        cmd.status = "pending"
        app.state.repository.save_command(cmd)
        app.state.repository.append_event(
            type="command_created", command_id=cmd.command_id, cmd_type="reject",
        )
        return {"success": True, "command_id": cmd.command_id, "status": "pending"}

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
                event = repo.append_event(
                    type="agent_status_changed", agent_id=agent_id, message="paused",
                )
                _emit_to_ws(app.state.broadcast_queue, event)
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
                event = repo.append_event(
                    type="agent_status_changed", agent_id=agent_id, message="idle",
                )
                _emit_to_ws(app.state.broadcast_queue, event)
                return {"success": True}
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # --- REST: 重试 ---

    @app.post("/api/retry")
    async def post_retry(body: dict[str, Any]) -> dict:
        feature_id = body.get("feature_id", "")
        event = app.state.repository.append_event(type="retry_feature", feature_id=feature_id)
        _emit_to_ws(app.state.broadcast_queue, event)
        return {"success": True}

    # --- REST: 跳过 ---

    @app.post("/api/skip")
    async def post_skip(body: dict[str, Any]) -> dict:
        feature_id = body.get("feature_id", "")
        event = app.state.repository.append_event(type="skip_feature", feature_id=feature_id)
        _emit_to_ws(app.state.broadcast_queue, event)
        return {"success": True}

    # --- REST: 命令创建（新接口）---

    @app.post("/api/dashboard/commands", status_code=202)
    async def create_command_endpoint(body: dict[str, Any]) -> dict:
        cmd = _create_command(body.get("type", ""), body)
        cmd.status = "pending"
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

    return app


def _create_command(cmd_type: str, body: dict[str, Any]) -> Command:
    """从请求体创建 Command 对象。"""
    from dashboard.models import Command
    # 类型映射：前端类型 → 后端类型
    actual_type = CMD_TYPE_MAP.get(cmd_type, cmd_type)
    return Command(
        command_id=f"cmd_{_now_iso()}",
        type=actual_type,
        target_id=body.get("target_id", ""),
        payload=body.get("payload", {}),
        project_id=body.get("project_id", ""),
        run_id=body.get("run_id", ""),
        issued_at=_now_iso(),
    )
