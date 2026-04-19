"""Dashboard REST API 路由和 WebSocket 端点 — 接入 ProjectStateRepository + CommandProcessor + CommandConsumer。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dashboard.event_bus import EventBus
from dashboard.models import ChatMessage, Command, DashboardState, Event, ModuleAssignment
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
    coordinator: "PMCoordinator | None" = None,
    product_manager: "ProductManager | None" = None,
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

    # 注入 PMCoordinator（可选）
    app.state.coordinator = coordinator

    # 注入 ProductManager（可选，用于对话回复）
    app.state.product_manager = product_manager

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

        # 调用 PM 生成回复
        pm_response = _generate_pm_response(
            app.state.dashboard_state.chat_history,
            app.state.repository,
            app.state.broadcast_queue,
            app.state.product_manager,
        )

        return {
            "success": True,
            "message_id": msg.id,
            "pm_response": pm_response.to_dict() if pm_response else None,
        }

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

    # --- REST: 模块分配 ---

    @app.get("/api/dashboard/modules")
    async def list_modules(role: str | None = None) -> dict:
        """列出所有模块分配，可按角色过滤。"""
        assignments = app.state.repository.list_module_assignments(role=role)
        return {
            "modules": [a.to_dict() for a in assignments],
            "total": len(assignments),
        }

    @app.post("/api/dashboard/modules", status_code=201)
    async def upsert_module(body: dict[str, Any]) -> dict:
        """创建或更新模块分配。"""
        required = ("module_id", "role")
        for field in required:
            if field not in body:
                raise HTTPException(status_code=422, detail=f"Missing required field: {field}")

        assignment = ModuleAssignment(
            module_id=body["module_id"],
            role=body["role"],
            assigned_agent_id=body.get("assigned_agent_id", ""),
            module_name=body.get("module_name", ""),
            description=body.get("description", ""),
            dependencies=body.get("dependencies", []),
            status=body.get("status", "pending"),
            interface_contract=body.get("interface_contract", {}),
        )
        saved = app.state.repository.upsert_module_assignment(assignment)
        return {"success": True, "assignment": saved.to_dict()}

    @app.delete("/api/dashboard/modules/{module_id}")
    async def delete_module(module_id: str) -> dict:
        """删除模块分配。"""
        repo = app.state.repository
        if not repo.get_module_assignment(module_id):
            raise HTTPException(status_code=404, detail=f"Module {module_id} not found")
        with repo._lock:
            repo._module_assignments.pop(module_id, None)
            repo._save()
        return {"success": True, "module_id": module_id}

    # --- REST: 执行控制 ---

    @app.post("/api/execution/start")
    async def start_execution() -> dict:
        """启动 PMCoordinator 执行循环。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            raise HTTPException(status_code=503, detail="PMCoordinator 未配置")
        result = coordinator.start_execution()
        if not result["success"]:
            raise HTTPException(status_code=409, detail=result.get("error", "无法启动"))
        return result

    @app.post("/api/execution/stop")
    async def stop_execution() -> dict:
        """停止 PMCoordinator 执行循环。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            raise HTTPException(status_code=503, detail="PMCoordinator 未配置")
        return coordinator.stop_execution()

    @app.get("/api/execution/status")
    async def get_execution_status() -> dict:
        """获取当前执行状态。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            return {"status": "idle", "thread_alive": False, "error": None, "available": False}
        return coordinator.get_execution_status()

    # --- REST: Agent 管理 ---

    @app.get("/api/agents")
    async def list_agents() -> dict:
        """列出所有 Agent 实例及其状态（含静默检测）。"""
        coordinator = getattr(app.state, "coordinator", None)
        repo = app.state.repository

        # 从 Repository 加载已注册的 Agent
        snapshot = repo.load_snapshot()
        agents = [a.to_dict() for a in snapshot.agents]

        # 补充静默检测状态
        silence_status = {}
        if coordinator:
            silence_status = coordinator.get_all_silence_status()

        for agent in agents:
            agent["silence_status"] = silence_status.get(agent.get("id", ""), {})

        # 从 Coordinator 补充执行中的 Agent 信息
        if coordinator:
            pm = coordinator._process_manager
            for agent_id, proc_info in pm.get_all_agents().items():
                for agent in agents:
                    if agent["id"] == agent_id:
                        agent["process_status"] = proc_info.get("status", "unknown")
                        agent["pid"] = proc_info.get("pid")
                        break

        return {"agents": agents, "total": len(agents)}

    @app.get("/api/agents/{agent_id}/status")
    async def get_agent_status(agent_id: str) -> dict:
        """获取单个 Agent 的详细状态，包括静默检测。"""
        coordinator = getattr(app.state, "coordinator", None)
        repo = app.state.repository

        snapshot = repo.load_snapshot()
        agent = None
        for a in snapshot.agents:
            if a.id == agent_id:
                agent = a.to_dict()
                break

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        result = {"agent": agent}

        if coordinator:
            silence = coordinator.get_all_silence_status().get(agent_id)
            if silence:
                result["silence_status"] = silence

            pm = coordinator._process_manager
            proc_status = pm.get_agent_status(agent_id)
            if proc_status:
                result["process_status"] = proc_status

        return result

    @app.post("/api/agents/{agent_id}/message")
    async def send_agent_message(agent_id: str, body: dict[str, Any]) -> dict:
        """向 Agent 发送消息（通过 stdin）。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            raise HTTPException(status_code=503, detail="PMCoordinator 未配置")

        message = body.get("message", "")
        if not message:
            raise HTTPException(status_code=422, detail="message is required")

        pm = coordinator._process_manager
        success = pm.send_message_to_agent(agent_id, message)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Agent {agent_id} not found or has no stdin",
            )

        app.state.repository.append_event(
            type="agent_message_sent",
            agent_id=agent_id,
            message=message[:200],
        )
        return {"success": True, "agent_id": agent_id}

    @app.post("/api/agents/{agent_id}/interrupt")
    async def interrupt_agent(agent_id: str, body: dict[str, Any] | None = None) -> dict:
        """中断 Agent 进程（默认 SIGINT，可 force=true 强制 kill）。"""
        body = body or {}
        force = body.get("force", False)

        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            raise HTTPException(status_code=503, detail="PMCoordinator 未配置")

        pm = coordinator._process_manager

        if force:
            pm.force_kill(agent_id)
        else:
            pm.graceful_interrupt(agent_id)

        app.state.repository.append_event(
            type="agent_interrupted",
            agent_id=agent_id,
            force=force,
        )
        return {"success": True, "agent_id": agent_id, "force": force}

    # --- REST: 待审批列表 ---

    @app.get("/api/dashboard/pending-approvals")
    async def list_pending_approvals() -> dict:
        """返回所有等待用户审批的命令。"""
        approvals = app.state.repository.list_pending_approvals()
        return {
            "approvals": approvals,
            "total": len(approvals),
        }

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
                "module_assignments": [m.to_dict() for m in snapshot.module_assignments],
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


def _generate_pm_response(
    chat_history: list[ChatMessage],
    repository: ProjectStateRepository,
    broadcast_queue: deque,
    product_manager: "ProductManager | None" = None,
) -> ChatMessage | None:
    """调用 ProductManager agent 生成 PM 回复。"""
    if product_manager is None:
        logger.warning("ProductManager 未配置，使用 fallback 回复")
        pm_content = "PM 暂未就绪，请重试。"
    else:
        user_message = chat_history[-1].content if chat_history else ""
        pm_content = product_manager.chat_response(user_message, chat_history, repository)
        if not pm_content:
            logger.error("ProductManager.chat_response 返回空结果")
            pm_content = "PM 处理消息时出错，请重试。"

    pm_msg = ChatMessage(
        id=f"pm_{_now_iso()}",
        role="pm",
        content=pm_content,
    )

    # 添加到 chat_history
    chat_history.append(pm_msg)

    # 持久化到 Repository
    repository.add_chat_message(pm_msg)

    # 广播给 WebSocket 客户端 — payload 必须包含完整 pm_response 对象
    # 前端 store.ts applyEventToState 通过 event.payload.pm_response 路由到 chatHistory
    event = repository.append_event(
        type="pm_response",
        pm_response={
            "id": pm_msg.id,
            "content": pm_content,
            "timestamp": pm_msg.timestamp,
            "action_triggered": "",
        },
    )
    _emit_to_ws(broadcast_queue, event)

    return pm_msg
