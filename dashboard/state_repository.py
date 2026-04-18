"""ProjectStateRepository：统一读写 agents/features/commands/events/chat 的单一状态源。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from dashboard.models import (
    AgentInstance,
    Feature,
    Command,
    Event,
    ChatMessage,
    Snapshot,
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
        self._next_event_id = 0
        self._snapshot_version = 0

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
            )

    # --- Agent ---

    def upsert_agent(self, agent: AgentInstance) -> AgentInstance:
        with self._lock:
            self._agents[agent.id] = agent
            return agent

    # --- Feature ---

    def upsert_feature(self, feature: Feature) -> Feature:
        with self._lock:
            self._features[feature.id] = feature
            return feature

    # --- Command ---

    def save_command(self, cmd: Command) -> Command:
        with self._lock:
            cmd.project_id = self._project_id
            cmd.run_id = self._run_id
            self._commands[cmd.command_id] = cmd
            return cmd

    def get_command(self, command_id: str) -> Command | None:
        with self._lock:
            return self._commands.get(command_id)

    # --- Event ---

    def append_event(self, event: Event | None = None, *, type: str = "", **kwargs) -> Event:
        with self._lock:
            if event is None:
                event = Event(type=type, **kwargs)
            self._next_event_id += 1
            event.event_id = self._next_event_id
            event.project_id = self._project_id
            event.run_id = self._run_id
            self._events.append(event)
            return event

    def get_events_after(self, after_id: int, limit: int = 200) -> list[Event]:
        with self._lock:
            return [e for e in self._events if e.event_id > after_id][:limit]

    # --- Chat ---

    def add_chat_message(self, msg: ChatMessage) -> ChatMessage:
        with self._lock:
            self._chat_history.append(msg)
            return msg
