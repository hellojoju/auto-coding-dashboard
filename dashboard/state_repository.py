"""ProjectStateRepository：统一读写 agents/features/commands/events/chat 的单一状态源。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from dashboard.models import (
    AgentInstance,
    Feature,
    Command,
    Event,
    ChatMessage,
    Snapshot,
    ModuleAssignment,
)


class ProjectStateRepository:
    """线程安全的项目状态仓储，所有状态读写收口到此处。"""

    def __init__(
        self,
        base_dir: Path | str,
        project_id: str,
        run_id: str = "",
    ) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._project_id = project_id
        self._run_id = run_id
        self._lock = threading.Lock()

        # 内存状态
        self._agents: dict[str, AgentInstance] = {}
        self._features: dict[str, Feature] = {}
        self._commands: dict[str, Command] = {}
        self._events: list[Event] = []
        self._chat_history: list[ChatMessage] = []
        self._module_assignments: dict[str, ModuleAssignment] = {}
        self._next_event_id = 0
        self._snapshot_version = 0

        # 从磁盘加载已有状态
        self._load_all()

    # --- Snapshot ---

    def load_snapshot(self) -> Snapshot:
        with self._lock:
            self._snapshot_version += 1
            return Snapshot(
                project_id=self._project_id,
                run_id=self._run_id,
                snapshot_version=self._snapshot_version,
                last_event_id=self._next_event_id,
                project_name="",
                agents=list(self._agents.values()),
                features=list(self._features.values()),
                chat_history=list(self._chat_history),
                module_assignments=list(self._module_assignments.values()),
            )

    # --- Agent ---

    def upsert_agent(self, agent: AgentInstance) -> AgentInstance:
        with self._lock:
            if agent.workspace_id:
                existing = self._agents.get(agent.id)
                if existing is not None and existing.workspace_id != agent.workspace_id:
                    raise ValueError(
                        f"Agent {agent.id} belongs to workspace '{existing.workspace_id}', "
                        f"cannot write from workspace '{agent.workspace_id}'"
                    )
            self._agents[agent.id] = agent
            self._save()
            return agent

    # --- Feature ---

    def upsert_feature(self, feature: Feature) -> Feature:
        with self._lock:
            if feature.workspace_id:
                existing = self._features.get(feature.id)
                if existing is not None and existing.workspace_id != feature.workspace_id:
                    raise ValueError(
                        f"Feature {feature.id} belongs to workspace '{existing.workspace_id}', "
                        f"cannot write from workspace '{feature.workspace_id}'"
                    )
            self._features[feature.id] = feature
            self._save()
            return feature

    # --- Command ---

    def save_command(self, cmd: Command) -> Command:
        with self._lock:
            if not cmd.command_id:
                import uuid
                cmd.command_id = str(uuid.uuid4())[:8]
            cmd.project_id = self._project_id
            cmd.run_id = self._run_id
            self._commands[cmd.command_id] = cmd
            self._save()
            return cmd

    def get_command(self, command_id: str) -> Command | None:
        with self._lock:
            return self._commands.get(command_id)

    # --- Event ---

    def append_event(self, event: Event | None = None, *, type: str = "", **kwargs) -> Event:
        with self._lock:
            if event is None:
                # Event 合法字段（payload 除外）
                _valid_fields = {
                    "schema_version", "event_id", "project_id", "run_id",
                    "type", "timestamp", "caused_by_command_id", "payload",
                }
                payload = dict(kwargs.pop("payload", {}))
                extra = {k: v for k, v in kwargs.items() if k not in _valid_fields}
                payload.update(extra)
                valid_kwargs = {k: v for k, v in kwargs.items() if k in _valid_fields}
                event = Event(type=type, payload=payload, **valid_kwargs)
            self._next_event_id += 1
            event.event_id = self._next_event_id
            event.project_id = self._project_id
            event.run_id = self._run_id
            self._events.append(event)
            self._save()
            return event

    def get_events_after(self, after_id: int, limit: int = 200) -> list[Event]:
        with self._lock:
            return [e for e in self._events if e.event_id > after_id][:limit]

    # --- Chat ---

    def add_chat_message(self, msg: ChatMessage) -> ChatMessage:
        with self._lock:
            self._chat_history.append(msg)
            self._save()
            return msg

    # --- Module Assignment ---

    def upsert_module_assignment(self, assignment: ModuleAssignment) -> ModuleAssignment:
        with self._lock:
            self._module_assignments[assignment.module_id] = assignment
            self._save()
            return assignment

    def get_module_assignment(self, module_id: str) -> ModuleAssignment | None:
        with self._lock:
            return self._module_assignments.get(module_id)

    def list_module_assignments(self, *, role: str | None = None) -> list[ModuleAssignment]:
        with self._lock:
            assignments = list(self._module_assignments.values())
            if role:
                assignments = [a for a in assignments if a.role == role]
            return assignments

    def list_pending_approvals(self) -> list[dict]:
        """返回所有需要用户审批的条目（状态为 waiting_approval 的 agent 关联的命令）。"""
        with self._lock:
            approvals = []
            for cmd in self._commands.values():
                if cmd.status == "pending":
                    approvals.append(cmd.to_dict())
            return approvals

    # --- Workspace filtering (多实例隔离预留) ---

    def get_agents_by_workspace(self, workspace_id: str) -> list[AgentInstance]:
        with self._lock:
            return [a for a in self._agents.values() if a.workspace_id == workspace_id]

    def get_features_by_workspace(self, workspace_id: str) -> list[Feature]:
        with self._lock:
            return [f for f in self._features.values() if f.workspace_id == workspace_id]

    # --- 持久化 ---

    def _save(self) -> None:
        """原子写入所有状态到磁盘。"""
        state = {
            "agents": [a.to_dict() for a in self._agents.values()],
            "features": [f.to_dict() for f in self._features.values()],
            "commands": [c.to_dict() for c in self._commands.values()],
            "events": [e.to_dict() for e in self._events],
            "chat_history": [m.to_dict() for m in self._chat_history],
            "module_assignments": [m.to_dict() for m in self._module_assignments.values()],
            "next_event_id": self._next_event_id,
        }
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._base, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._base / "state.json")
        except Exception:
            os.unlink(tmp_path)
            raise

    def _load_all(self) -> None:
        """从磁盘加载所有状态。"""
        state_file = self._base / "state.json"
        if not state_file.exists():
            return
        with open(state_file, "r") as f:
            state = json.load(f)
        self._agents = {a["id"]: AgentInstance.from_dict(a) for a in state.get("agents", [])}
        self._features = {f["id"]: Feature.from_dict(f) for f in state.get("features", [])}
        self._commands = {c["command_id"]: Command.from_dict(c) for c in state.get("commands", [])}
        self._events = [Event.from_dict(e) for e in state.get("events", [])]
        self._chat_history = [ChatMessage.from_dict(m) for m in state.get("chat_history", [])]
        self._module_assignments = {
            m["module_id"]: ModuleAssignment.from_dict(m)
            for m in state.get("module_assignments", [])
        }
        self._next_event_id = state.get("next_event_id", 0)
