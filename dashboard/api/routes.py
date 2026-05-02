"""Dashboard REST API 路由和 WebSocket 端点 — 接入 ProjectStateRepository + CommandProcessor + CommandConsumer。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.product_manager import ProductManager
    from dashboard.coordinator import PMCoordinator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from dashboard.command_processor import CommandProcessor
from dashboard.consumer import CommandConsumer
from dashboard.event_bus import EventBus
from dashboard.models import ChatMessage, Command, Event, ModuleAssignment
from dashboard.state_repository import ProjectStateRepository
from ralph.report_generator import ReportGenerator
from ralph.repository import RalphRepository
from ralph.schema.work_unit import WorkUnitStatus

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class _DashboardAppState:
    """存储在 app.state 中的 WebSocket 连接和广播队列。"""

    def __init__(self) -> None:
        self.connected_ws: set[WebSocket] = set()
        self.broadcast_queue: deque[dict] = deque()


def _emit_to_ws(broadcast_queue: deque, event: Event) -> None:
    """将 Repository 事件推入 WebSocket 广播队列。"""
    payload = {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "project_id": event.project_id,
        "run_id": event.run_id,
        "type": event.type,
        "payload": event.payload,
        "timestamp": event.timestamp or _now_iso(),
        "caused_by_command_id": event.caused_by_command_id,
    }
    broadcast_queue.append(payload)


def _event_to_stream_item(event: Event) -> dict[str, Any]:
    payload = event.payload or {}
    event_agent_id = payload.get("agent_id") or payload.get("assigned_agent_id")
    message = payload.get("message")
    if not isinstance(message, str) or not message:
        if event.type == "blocking_issue_created":
            message = payload.get("description", "阻塞问题已创建")
        elif event.type == "feature_updated":
            message = f"Feature {payload.get('feature_id', '')} -> {payload.get('status', '')}".strip()
        else:
            message = event.type
    severity = "info"
    if "blocked" in event.type or "failed" in event.type or "error" in event.type:
        severity = "error"
    elif "warning" in event.type or "reject" in event.type:
        severity = "warning"
    return {
        "id": str(event.event_id),
        "timestamp": event.timestamp,
        "type": event.type,
        "agent_id": event_agent_id,
        "feature_id": payload.get("feature_id"),
        "message": message,
        "severity": severity,
    }


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
        with suppress(asyncio.CancelledError):
            await task


def create_dashboard_app(
    event_bus: EventBus,
    repository: ProjectStateRepository | None = None,
    coordinator: "PMCoordinator | None" = None,  # noqa: UP037
    product_manager: "ProductManager | None" = None,  # noqa: UP037
    ralph_repository: RalphRepository | None = None,
    ralph_engine: Any = None,  # WorkUnitEngine | None
) -> FastAPI:
    app = FastAPI(title="AI Dev Dashboard", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app_state = _DashboardAppState()
    app.state.connected_ws = app_state.connected_ws
    app.state.broadcast_queue = app_state.broadcast_queue
    app.state.event_bus = event_bus

    # 注入 RalphRepository
    if ralph_repository is None:
        ralph_dir = Path(os.environ.get("RALPH_DIR", ".ralph"))
        ralph_repository = RalphRepository(ralph_dir)
    app.state.ralph_repository = ralph_repository

    # 注入 WorkUnitEngine（如果未提供则从 project_dir 初始化）
    if ralph_engine is None:
        project_dir_env = os.environ.get("PROJECT_DIR")
        if project_dir_env:
            from ralph.work_unit_engine import WorkUnitEngine

            ralph_engine = WorkUnitEngine(Path(project_dir_env))
    app.state.ralph_engine = ralph_engine

    # 注入 ReportGenerator
    report_generator = ReportGenerator(ralph_repository._ralph_dir)
    app.state.report_generator = report_generator

    # 注入 Repository
    if repository is None:
        _tmp_dir = tempfile.mkdtemp(prefix="dashboard_state_")
        repository = ProjectStateRepository(
            base_dir=Path(_tmp_dir),
            project_id="default",
            run_id="",
        )
    app.state.repository = repository

    # 桥接 EventBus → WebSocket broadcast_queue
    # EventBus 只负责内存队列（保持向后兼容），Repository 持久化在桥接层显式完成
    _original_emit = event_bus.emit
    def _wrapped_emit(event_type: str, **kwargs: Any) -> None:
        _original_emit(event_type, **kwargs)
        stored_event = repository.append_event(type=event_type, payload=kwargs)
        _emit_to_ws(app.state.broadcast_queue, stored_event)
    event_bus.emit = _wrapped_emit

    # 注入 CommandProcessor — 事件统一通过 Repository 追加
    def on_event(event: Event) -> None:
        stored_event = repository.append_event(type=event.type, payload=event.payload)
        _emit_to_ws(app.state.broadcast_queue, stored_event)

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
        """从 Repository 加载统一状态快照。"""
        snapshot = app.state.repository.load_snapshot()
        return {
            "project_name": snapshot.project_name,
            "agents": [a.to_dict() for a in snapshot.agents],
            "features": [f.to_dict() for f in snapshot.features],
            "events": [e.to_dict() for e in app.state.repository.get_events_after(0, limit=200)],
            "chat_history": [m.to_dict() for m in snapshot.chat_history],
        }

    @app.get("/api/dashboard/state")
    async def get_dashboard_state() -> dict:
        """从 Repository 加载统一快照。"""
        snapshot = app.state.repository.load_snapshot()
        return snapshot.to_dict()

    # --- REST: 事件列表 ---

    @app.get("/api/events")
    async def get_events(
        agent_id: str | None = None,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[dict] | dict:
        if agent_id is None and after_id == 0:
            return app.state.event_bus.get_events()

        events = app.state.repository.get_events_after(after_id, limit=max(limit * 5, limit))
        items: list[dict] = []
        for event in events:
            item = _event_to_stream_item(event)
            if agent_id and item.get("agent_id") != agent_id:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return {"events": items}

    @app.get("/api/dashboard/events")
    async def get_dashboard_events(after_event_id: int = 0, limit: int = 200) -> dict:
        events = app.state.repository.get_events_after(after_event_id, limit)
        return {
            "project_id": app.state.repository._project_id,
            "events": [e.to_dict() for e in events],
        }

    @app.get("/api/blocking-issues")
    async def list_blocking_issues(feature_id: str | None = None, resolved: bool | None = None) -> dict:
        issues = app.state.repository.list_blocking_issues(feature_id=feature_id, resolved=resolved)
        return {
            "issues": [issue.to_dict() for issue in issues],
            "total": len(issues),
        }

    @app.get("/api/execution-ledger")
    async def get_execution_ledger() -> dict:
        ledger_file = app.state.repository._base.parent / "execution-plan.json"
        if not ledger_file.exists():
            return {
                "executions": [],
                "summary": {
                    "total_executions": 0, "completed": 0,
                    "failed": 0, "blocked": 0, "retrying": 0,
                },
            }
        return json.loads(ledger_file.read_text(encoding="utf-8"))

    # --- REST: 用户对话 ---

    @app.post("/api/chat")
    async def post_chat(body: dict[str, Any]) -> dict:
        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=422, detail="content is required")
        msg = ChatMessage(id=f"chat_{_now_iso()}", role="user", content=content)
        app.state.repository.add_chat_message(msg)
        event = app.state.repository.append_event(
            type="pm_decision", message=f"用户消息: {content}",
        )
        _emit_to_ws(app.state.broadcast_queue, event)

        # 调用 PM 生成回复
        pm_response = _generate_pm_response(
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
        idempotency_key = body.get("idempotency_key", "")
        if idempotency_key:
            existing = app.state.repository.get_command_by_idempotency_key(idempotency_key)
            if existing:
                return {
                    "schema_version": 1,
                    "command_id": existing.command_id,
                    "status": existing.status,
                    "was_duplicate": True,
                }

        cmd = _create_command(body.get("type", ""), body)
        cmd.status = "pending"
        app.state.repository.save_command(cmd)
        return {
            "schema_version": 1,
            "command_id": cmd.command_id,
            "status": cmd.status,
            "was_duplicate": False,
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

        result = dict(agent)
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
                "blocking_issues": [i.to_dict() for i in snapshot.blocking_issues],
            })
            while True:
                try:
                    while app.state.broadcast_queue:
                        payload = app.state.broadcast_queue.popleft()
                        await ws.send_json(payload)
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.1)  # noqa: F841
                except TimeoutError:
                    continue
        except WebSocketDisconnect:
            app.state.connected_ws.discard(ws)

    # --- Ralph API: 只读端点 ---

    @app.get("/api/ralph/health")
    async def ralph_health() -> dict:
        """Ralph 系统健康检查。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        work_units = ralph_repo.list_work_units()
        return {
            "status": "healthy",
            "work_units_count": len(work_units),
            "timestamp": _now_iso(),
        }

    @app.get("/api/ralph/work-units")
    async def ralph_list_work_units(status: str | None = None) -> list[dict]:
        """列出所有 WorkUnit，支持状态过滤。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        filter_status = None
        if status:
            try:
                filter_status = WorkUnitStatus(status)
            except ValueError as err:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from err
        units = ralph_repo.list_work_units(status=filter_status)
        return [_serialize_work_unit(u) for u in units]

    @app.get("/api/ralph/work-units/{work_id}")
    async def ralph_get_work_unit(work_id: str) -> dict:
        """获取单个 WorkUnit 详情。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        unit = ralph_repo.get_work_unit(work_id)
        if unit is None:
            raise HTTPException(status_code=404, detail=f"WorkUnit {work_id} not found")
        return _serialize_work_unit(unit)

    @app.get("/api/ralph/work-units/{work_id}/evidence")
    async def ralph_list_evidence(work_id: str) -> list[dict]:
        """获取指定 WorkUnit 的证据列表。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        # 验证 work_id 存在
        unit = ralph_repo.get_work_unit(work_id)
        if unit is None:
            raise HTTPException(status_code=404, detail=f"WorkUnit {work_id} not found")
        evidence_list = ralph_repo.list_evidence(work_id=work_id)
        return [_serialize_evidence(e) for e in evidence_list]

    @app.get("/api/ralph/work-units/{work_id}/evidence/{file_path:path}")
    async def ralph_get_evidence_file(work_id: str, file_path: str) -> PlainTextResponse:
        """获取证据文件内容（带安全验证）。"""
        ralph_repo: RalphRepository = app.state.ralph_repository

        # 验证 work_id 存在
        unit = ralph_repo.get_work_unit(work_id)
        if unit is None:
            raise HTTPException(status_code=404, detail=f"WorkUnit {work_id} not found")

        # 安全验证：防止路径遍历攻击
        # 1. 拒绝包含 .. 的路径（在解析前检查原始路径）
        if ".." in file_path:
            raise HTTPException(status_code=403, detail="Invalid file path: path traversal detected")

        # 2. 拒绝绝对路径
        if file_path.startswith("/"):
            raise HTTPException(status_code=403, detail="Invalid file path: absolute paths not allowed")

        # 3. 构建完整路径并解析为绝对路径
        evidence_dir = ralph_repo._evidence_dir
        try:
            requested_path = (evidence_dir / file_path).resolve()
        except (ValueError, OSError) as err:
            raise HTTPException(status_code=403, detail="Invalid file path") from err

        evidence_dir_resolved = evidence_dir.resolve()

        # 4. 确保文件在 evidence 目录内
        try:
            requested_path.relative_to(evidence_dir_resolved)
        except ValueError as err:
            raise HTTPException(status_code=403, detail="Access denied: path outside evidence directory") from err

        # 4. 检查文件是否存在
        if not requested_path.exists() or not requested_path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        # 5. 读取文件内容，大文件截断
        content = requested_path.read_text(encoding="utf-8", errors="replace")
        truncated = False
        max_size = 100 * 1024  # 100KB
        if len(content) > max_size:
            content = content[:max_size] + "\n\n[TRUNCATED: file exceeds 100KB limit]"
            truncated = True

        # 6. 敏感信息 redaction
        content = _redact_sensitive_content(content)

        headers = {"X-Truncated": "true" if truncated else "false"}
        return PlainTextResponse(content, headers=headers)

    @app.get("/api/ralph/work-units/{work_id}/reviews")
    async def ralph_list_reviews(work_id: str) -> list[dict]:
        """获取指定 WorkUnit 的审查结果。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        # 验证 work_id 存在
        unit = ralph_repo.get_work_unit(work_id)
        if unit is None:
            raise HTTPException(status_code=404, detail=f"WorkUnit {work_id} not found")
        reviews = ralph_repo.list_reviews(work_id=work_id)
        return [ralph_repo._serialize_review(r) for r in reviews]

    @app.get("/api/ralph/blockers")
    async def ralph_list_blockers(work_id: str | None = None, resolved: bool | None = None) -> list[dict]:
        """获取所有阻塞项，支持过滤。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        blockers = ralph_repo.list_blockers(work_id=work_id, resolved=resolved)
        return [_serialize_blocker(b) for b in blockers]

    @app.get("/api/ralph/pending-actions")
    async def ralph_pending_actions() -> list[dict]:
        """获取待处理审批/干预项汇总。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        repo: ProjectStateRepository = app.state.repository

        # 获取需要人工干预的 WorkUnit（blocked 状态）
        blocked_units = ralph_repo.list_work_units(status=WorkUnitStatus.BLOCKED)
        needs_rework_units = ralph_repo.list_work_units(status=WorkUnitStatus.NEEDS_REWORK)
        needs_review_units = ralph_repo.list_work_units(status=WorkUnitStatus.NEEDS_REVIEW)

        # 获取失败的 Command
        failed_commands = [c for c in repo.list_all_commands() if c.status == "failed"]

        actions = []

        # 添加 blocked WorkUnit 为待处理项
        for unit in blocked_units:
            blockers = ralph_repo.list_blockers(work_id=unit.work_id, resolved=False)
            for blocker in blockers:
                actions.append({
                    "action_id": f"blocker_{blocker.blocker_id}",
                    "action_type": "missing_dep",
                    "work_id": unit.work_id,
                    "description": blocker.reason,
                    "context": {"blocker_type": blocker.blocker_type},
                    "created_at": "",  # Blocker 没有 created_at 字段
                })

        # 添加 needs_rework 为待处理项
        for unit in needs_rework_units:
            actions.append({
                "action_id": f"rework_{unit.work_id}",
                "action_type": "execution_error",
                "work_id": unit.work_id,
                "description": f"WorkUnit {unit.work_id} 需要返工",
                "context": {},
                "created_at": "",
            })

        # 添加 needs_review 为待处理项（人工可以干预）
        for unit in needs_review_units:
            actions.append({
                "action_id": f"review_{unit.work_id}",
                "action_type": "review_dispute",
                "work_id": unit.work_id,
                "description": f"WorkUnit {unit.work_id} 等待审查",
                "context": {},
                "created_at": "",
            })

        # 添加失败的 Command
        for cmd in failed_commands:
            actions.append({
                "action_id": f"cmd_failed_{cmd.command_id}",
                "action_type": "execution_error",
                "work_id": cmd.target_id,
                "description": cmd.result.get("error", "Command execution failed"),
                "context": {"command_id": cmd.command_id},
                "created_at": cmd.issued_at,
            })

        return actions

    @app.get("/api/ralph/work-units/{work_id}/transitions")
    async def ralph_get_transitions(work_id: str) -> list[dict]:
        """获取 WorkUnit 状态转换历史。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        # 验证 work_id 存在
        unit = ralph_repo.get_work_unit(work_id)
        if unit is None:
            raise HTTPException(status_code=404, detail=f"WorkUnit {work_id} not found")
        transitions = ralph_repo.get_transitions(work_id=work_id)
        return transitions

    @app.get("/api/ralph/summary")
    async def ralph_summary() -> dict:
        """获取 Ralph 运行概览统计。"""
        ralph_repo: RalphRepository = app.state.ralph_repository
        all_units = ralph_repo.list_work_units()

        status_counts = {status.value: 0 for status in WorkUnitStatus}
        for unit in all_units:
            status_counts[unit.status.value] += 1

        # 计算成功率（accepted / (accepted + failed + needs_rework)）
        terminal_count = status_counts["accepted"] + status_counts["failed"] + status_counts["needs_rework"]
        success_rate = 0.0
        if terminal_count > 0:
            success_rate = status_counts["accepted"] / terminal_count * 100

        # 获取未解决的 blockers
        unresolved_blockers = ralph_repo.list_blockers(resolved=False)

        return {
            "total_work_units": len(all_units),
            "status_counts": status_counts,
            "success_rate_percent": round(success_rate, 1),
            "unresolved_blockers": len(unresolved_blockers),
            "timestamp": _now_iso(),
        }

    # --- Ralph API: Command 端点 ---

    @app.post("/api/ralph/commands")
    async def ralph_create_command(body: dict[str, Any]) -> dict:
        """创建 Ralph Command（带幂等键）。"""
        repo: ProjectStateRepository = app.state.repository

        # 检查幂等键
        idempotency_key = body.get("idempotency_key", "")
        if idempotency_key:
            existing = repo.get_command_by_idempotency_key(idempotency_key)
            if existing:
                return {
                    "success": True,
                    "command_id": existing.command_id,
                    "status": existing.status,
                    "was_duplicate": True,
                }

        # 验证必需字段 (前端使用 command_type 而非 type)
        cmd_type = body.get("command_type", "")
        if not cmd_type:
            raise HTTPException(status_code=422, detail="command_type is required")

        # 创建 Command (前端使用 target_id 而非 work_id)
        cmd = Command(
            command_id=f"ralph_cmd_{_now_iso()}",
            type=cmd_type,
            target_id=body.get("target_id", ""),
            payload=body.get("payload", {}),
            project_id=body.get("project_id", ""),
            run_id=body.get("run_id", ""),
            issued_at=_now_iso(),
            idempotency_key=idempotency_key,
            status="pending",
        )

        repo.save_command(cmd)

        return {
            "success": True,
            "command_id": cmd.command_id,
            "status": cmd.status,
            "was_duplicate": False,
        }

    @app.get("/api/ralph/commands/{command_id}")
    async def ralph_get_command(command_id: str) -> dict:
        """查询 Command 状态。"""
        repo: ProjectStateRepository = app.state.repository
        cmd = repo.get_command(command_id)
        if cmd is None:
            raise HTTPException(status_code=404, detail=f"Command {command_id} not found")
        return cmd.to_dict()

    @app.post("/api/ralph/commands/{command_id}/cancel")
    async def ralph_cancel_command(command_id: str) -> dict:
        """取消待处理的 Command。"""
        repo: ProjectStateRepository = app.state.repository
        cmd = repo.get_command(command_id)
        if cmd is None:
            raise HTTPException(status_code=404, detail=f"Command {command_id} not found")

        # 只能取消 pending 状态的 Command
        if cmd.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel command with status: {cmd.status}",
            )

        cmd.status = "cancelled"
        cmd.updated_at = _now_iso()
        repo.save_command(cmd)

        return {
            "success": True,
            "command_id": cmd.command_id,
            "status": cmd.status,
        }

    @app.get("/api/ralph/commands")
    async def ralph_list_commands(status: str | None = None) -> list[dict]:
        """列出所有 Command，支持 status 过滤。"""
        repo: ProjectStateRepository = app.state.repository
        commands = repo.list_all_commands()
        if status:
            commands = [c for c in commands if c.status == status]
        return [c.to_dict() for c in commands]

    # --- Ralph API: 报告端点 ---

    @app.get("/api/ralph/reports")
    async def ralph_list_reports() -> list[dict]:
        """列出所有已生成的报告。"""
        gen: ReportGenerator = app.state.report_generator
        reports = gen.list_reports()
        return [
            {
                "name": r.name,
                "size_bytes": r.stat().st_size,
                "created_at": _now_iso(),
            }
            for r in reports
        ]

    @app.post("/api/ralph/reports/generate")
    async def ralph_generate_report(body: dict[str, Any] | None = None) -> dict:
        """生成中文研发报告。"""
        body = body or {}
        title = body.get("title", "研发报告")
        filename = body.get("filename", "report.md")

        gen: ReportGenerator = app.state.report_generator
        content = gen.generate(title=title)
        path = gen.save(content, filename)

        return {
            "success": True,
            "name": path.name,
            "path": str(path),
            "content": content,
        }

    @app.get("/api/ralph/reports/{name:path}")
    async def ralph_get_report(name: str) -> dict:
        """获取单个报告内容。"""
        gen: ReportGenerator = app.state.report_generator
        reports_dir = gen._ralph_dir / "reports"

        # 安全验证：防止路径遍历
        if ".." in name or name.startswith("/"):
            raise HTTPException(status_code=403, detail="Invalid report name")

        report_path = (reports_dir / name).resolve()
        try:
            report_path.relative_to(reports_dir.resolve())
        except ValueError as err:
            raise HTTPException(status_code=403, detail="Access denied: path outside reports directory") from err

        if not report_path.is_file():
            raise HTTPException(status_code=404, detail=f"Report {name} not found")

        content = report_path.read_text(encoding="utf-8")
        return {
            "name": report_path.name,
            "content": content,
            "size_bytes": report_path.stat().st_size,
        }

    return app


def _serialize_work_unit(unit: Any) -> dict:
    """序列化 WorkUnit 为字典。"""
    from dataclasses import asdict

    from ralph.schema.work_unit import WorkUnit

    if not isinstance(unit, WorkUnit):
        return {}

    data = asdict(unit)
    data["status"] = unit.status.value

    # 序列化嵌套对象
    if unit.task_harness:
        data["task_harness"] = asdict(unit.task_harness)
    if unit.context_pack:
        data["context_pack"] = asdict(unit.context_pack)
    if unit.evidence:
        data["evidence"] = [asdict(e) for e in unit.evidence]
    if unit.review_result:
        data["review_result"] = _serialize_review_result(unit.review_result)

    return data


def _serialize_review_result(review: Any) -> dict:
    """序列化 ReviewResult 为字典。"""
    from dataclasses import asdict

    return asdict(review)


def _serialize_evidence(evidence: Any) -> dict:
    """序列化 Evidence 为前端期望的格式。

    前端期望字段: evidence_id, work_id, file_name, file_type, size_bytes, created_at
    后端存储字段: evidence_id, work_id, evidence_type, file_path, description, created_at
    """
    from pathlib import Path

    file_path = evidence.file_path
    file_name = Path(file_path).name if file_path else ""

    # 从 file_path 推断 file_type（对齐前端 Evidence.file_type 枚举）
    file_type = "other"
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in (".diff", ".patch"):
            file_type = "diff"
        elif ext in (".log"):
            file_type = "log"
        elif ext in (".txt", ".md", ".rst"):
            file_type = "test_output"
        elif ext in (".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h"):
            file_type = "other"
        elif ext in (".json", ".yaml", ".yml", ".xml"):
            file_type = "other"
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            file_type = "screenshot"

    return {
        "evidence_id": evidence.evidence_id,
        "work_id": evidence.work_id,
        "file_name": file_name,
        "file_type": file_type,
        "size_bytes": 0,  # 暂时无法获取，设为 0
        "created_at": evidence.created_at,
    }


def _serialize_blocker(blocker: Any) -> dict:
    """序列化 Blocker 为前端期望的格式。

    前端期望字段: blocker_id, work_id, reason, category, created_at, resolved
    """
    return {
        "blocker_id": blocker.blocker_id,
        "work_id": blocker.work_id,
        "category": blocker.blocker_type,
        "reason": blocker.reason,
        "created_at": "",  # Blocker 没有 created_at 字段
        "resolved": blocker.resolved,
    }


def _redact_sensitive_content(content: str) -> str:
    """Redact 敏感信息如 API keys、密码等。"""
    # Redact API keys
    content = re.sub(
        r'(api[_-]?key["\']?\s*[:=]\s*)["\']?[a-zA-Z0-9_\-]{16,}["\']?',
        r'\1***REDACTED***',
        content,
        flags=re.IGNORECASE,
    )
    # Redact passwords
    content = re.sub(
        r'(password["\']?\s*[:=]\s*)["\'][^"\']+["\']',
        r'\1"***REDACTED***"',
        content,
        flags=re.IGNORECASE,
    )
    # Redact secrets
    content = re.sub(
        r'(secret["\']?\s*[:=]\s*)["\'][^"\']+["\']',
        r'\1"***REDACTED***"',
        content,
        flags=re.IGNORECASE,
    )
    # Redact tokens
    content = re.sub(
        r'(token["\']?\s*[:=]\s*)["\'][^"\']+["\']',
        r'\1"***REDACTED***"',
        content,
        flags=re.IGNORECASE,
    )
    return content


def _create_command(cmd_type: str, body: dict[str, Any]) -> Command:
    """从请求体创建 Command 对象，支持幂等键。"""
    from dashboard.models import Command
    return Command(
        command_id=f"cmd_{_now_iso()}",
        type=cmd_type,
        target_id=body.get("target_id", ""),
        payload=body.get("payload", {}),
        project_id=body.get("project_id", ""),
        run_id=body.get("run_id", ""),
        issued_at=_now_iso(),
        idempotency_key=body.get("idempotency_key", ""),
    )


def _generate_pm_response(
    repository: ProjectStateRepository,
    broadcast_queue: deque,
    product_manager: ProductManager | None = None,
) -> ChatMessage | None:
    """调用 ProductManager agent 生成 PM 回复。"""
    # 从 Repository 获取 chat history
    snapshot = repository.load_snapshot()
    chat_history = snapshot.chat_history

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

    # 持久化到 Repository
    repository.add_chat_message(pm_msg)

    # 广播给 WebSocket 客户端
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
