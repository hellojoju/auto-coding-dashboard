"""ProjectStateRepository：统一读写 agents/features/commands/events/chat 的单一状态源。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dashboard.models import (
    AgentInstance,
    Feature,
    Command,
    Event,
    ChatMessage,
    Snapshot,
    ModuleAssignment,
    BlockingIssue,
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
        self._blocking_issues: dict[str, BlockingIssue] = {}
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
                blocking_issues=list(self._blocking_issues.values()),
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

    def upsert_feature(self, feature: Feature, *, event_type: str = "") -> Feature:
        with self._lock:
            existing = self._features.get(feature.id) if feature.id in self._features else None
            if feature.workspace_id:
                if existing is not None and existing.workspace_id != feature.workspace_id:
                    raise ValueError(
                        f"Feature {feature.id} belongs to workspace '{existing.workspace_id}', "
                        f"cannot write from workspace '{feature.workspace_id}'"
                    )
            # 状态变更必须伴随事件
            if existing is not None and existing.status != feature.status:
                if not event_type:
                    raise ValueError(
                        f"Feature {feature.id} status changed from '{existing.status}' to "
                        f"'{feature.status}' but no event_type provided. "
                        "Every status change must be accompanied by an event."
                    )
                self._next_event_id += 1
                evt = Event(
                    event_id=self._next_event_id,
                    project_id=self._project_id,
                    run_id=self._run_id,
                    type=event_type,
                    payload={"feature_id": feature.id, "old_status": existing.status, "new_status": feature.status},
                )
                self._events.append(evt)
            self._features[feature.id] = feature
            self._save()
            return feature

    # --- Command ---

    def save_command(self, cmd: Command) -> Command:
        with self._lock:
            if not cmd.command_id:
                cmd.command_id = str(uuid.uuid4())[:8]
            cmd.project_id = self._project_id
            cmd.run_id = self._run_id
            self._commands[cmd.command_id] = cmd
            self._save()
            return cmd

    def get_command_by_idempotency_key(self, key: str) -> Command | None:
        """通过幂等键查找命令。"""
        with self._lock:
            for cmd in self._commands.values():
                if cmd.idempotency_key == key:
                    return cmd
            return None

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

    def list_pending_commands(self) -> list[Command]:
        """返回所有状态为 pending 的命令。"""
        with self._lock:
            return [c for c in self._commands.values() if c.status == "pending"]

    def list_commands_by_status(self, *statuses: str) -> list[Command]:
        """返回指定状态列表中的所有命令。"""
        with self._lock:
            return [c for c in self._commands.values() if c.status in statuses]

    def list_all_commands(self) -> list[Command]:
        """返回所有命令的只读副本。"""
        with self._lock:
            return list(self._commands.values())

    def list_pending_approvals(self) -> list[dict]:
        """返回所有需要用户审批的条目（状态为 waiting_approval 的 agent 关联的命令）。"""
        with self._lock:
            approvals = []
            for cmd in self._commands.values():
                if cmd.status == "pending":
                    approvals.append(cmd.to_dict())
            return approvals

    # --- Blocking Issue ---

    def create_blocking_issue(self, issue: BlockingIssue) -> BlockingIssue:
        """创建阻塞问题，自动生成 issue_id。"""
        if not issue.issue_type:
            raise ValueError("issue_type is required")
        if not issue.feature_id:
            raise ValueError("feature_id is required")
        with self._lock:
            if not issue.issue_id:
                issue.issue_id = str(uuid.uuid4())[:8]
            self._blocking_issues[issue.issue_id] = issue
            self._save()
            return issue

    def resolve_blocking_issue(self, issue_id: str, resolution: str) -> bool:
        """标记阻塞问题为已解决。"""
        with self._lock:
            issue = self._blocking_issues.get(issue_id)
            if issue is None:
                return False
            issue.resolved = True
            issue.resolved_at = datetime.now(timezone.utc).isoformat()
            issue.resolution = resolution
            self._save()
            return True

    def get_blocking_issue(self, issue_id: str) -> BlockingIssue | None:
        """按 ID 获取阻塞问题。"""
        with self._lock:
            return self._blocking_issues.get(issue_id)

    def list_blocking_issues(
        self,
        *,
        feature_id: str | None = None,
        resolved: bool | None = None,
    ) -> list[BlockingIssue]:
        """列出阻塞问题，支持按 feature_id 和 resolved 状态过滤。"""
        with self._lock:
            issues = list(self._blocking_issues.values())
            if feature_id is not None:
                issues = [i for i in issues if i.feature_id == feature_id]
            if resolved is not None:
                issues = [i for i in issues if i.resolved == resolved]
            return issues

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
            "blocking_issues": [i.to_dict() for i in self._blocking_issues.values()],
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
        self._blocking_issues = {
            i["issue_id"]: BlockingIssue.from_dict(i)
            for i in state.get("blocking_issues", [])
        }
