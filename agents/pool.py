"""AgentPool — 多实例 Agent 管理器

支持同一角色多个实例并发执行，每个实例拥有独立 workspace。
PM 通过 AgentPool 分配任务，而非直接 get_agent()。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents import AGENT_REGISTRY, AGENT_ROLES, BaseAgent


@dataclass
class AgentInstance:
    """单个 agent 实例的运行时状态"""

    instance_id: str          # 如 "backend-1", "frontend-2"
    role: str                 # 如 "backend", "frontend"
    workspace_id: str         # 唯一 workspace 标识
    workspace_path: Path      # 工作目录
    status: str = "idle"      # idle | busy | error | stopped
    current_task_id: str = ""
    total_tasks_completed: int = 0

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "role": self.role,
            "workspace_id": self.workspace_id,
            "workspace_path": str(self.workspace_path),
            "status": self.status,
            "current_task_id": self.current_task_id,
            "total_tasks_completed": self.total_tasks_completed,
        }


class AgentPool:
    """管理多角色多实例 agent 的生命周期和任务分配。

    典型用法:
        pool = AgentPool(base_workspace=Path("/tmp/workspaces"))
        pool.ensure_instances("backend", count=2)
        agent = pool.acquire("backend")
        # ... 执行任务 ...
        pool.release(agent)
    """

    def __init__(self, base_workspace: Path | None = None) -> None:
        self._base_workspace = base_workspace or Path("/tmp/auto-coding-workspaces")
        self._base_workspace.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._instances: dict[str, AgentInstance] = {}  # instance_id -> AgentInstance
        self._agents: dict[str, BaseAgent] = {}         # instance_id -> Agent实例
        self._available: dict[str, list[str]] = {}      # role -> [instance_id, ...]

    # ── 实例管理 ─────────────────────────────────────────────

    def ensure_instances(self, role: str, count: int = 1) -> list[AgentInstance]:
        """确保某角色有 count 个可用实例，已存在则补齐。"""
        if role not in AGENT_REGISTRY:
            raise ValueError(f"未知角色: {role}")

        with self._lock:
            existing = self._list_instances_for_role(role)
            base_num = len(existing)
            to_create = max(0, count - base_num)
            for i in range(to_create):
                num = base_num + i + 1
                instance = self._create_instance(role, num)
                existing.append(instance)
            return list(existing)

    def _list_instances_for_role(self, role: str) -> list[AgentInstance]:
        """必须在锁内调用"""
        return [inst for inst in self._instances.values() if inst.role == role]

    def _create_instance(self, role: str, num: int) -> AgentInstance:
        """必须在锁内调用"""
        instance_id = f"{role}-{num}"
        workspace_id = f"{role}-{num}-{id(self)}"
        workspace_path = self._base_workspace / workspace_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        agent_cls = AGENT_REGISTRY[role]
        agent = agent_cls(workspace_path)

        instance = AgentInstance(
            instance_id=instance_id,
            role=role,
            workspace_id=workspace_id,
            workspace_path=workspace_path,
        )
        self._instances[instance_id] = instance
        self._agents[instance_id] = agent
        self._available.setdefault(role, []).append(instance_id)
        return instance

    # ── 获取 / 归还 ──────────────────────────────────────────

    def acquire(self, role: str) -> tuple[AgentInstance, BaseAgent] | None:
        """获取一个空闲实例。无可用实例返回 None。"""
        with self._lock:
            available_ids = self._available.get(role, [])
            if not available_ids:
                return None
            instance_id = available_ids.pop(0)
            instance = self._instances[instance_id]
            agent = self._agents[instance_id]
            instance.status = "busy"
            return instance, agent

    def release(self, instance_id: str, task_success: bool = True) -> None:
        """归还实例。"""
        with self._lock:
            instance = self._instances.get(instance_id)
            if instance is None:
                return
            if task_success:
                instance.total_tasks_completed += 1
            instance.status = "idle"
            instance.current_task_id = ""
            self._available.setdefault(instance.role, []).append(instance_id)

    # ── 查询 ─────────────────────────────────────────────────

    def list_all(self) -> list[AgentInstance]:
        with self._lock:
            return list(self._instances.values())

    def list_by_role(self, role: str) -> list[AgentInstance]:
        with self._lock:
            return [i for i in self._instances.values() if i.role == role]

    def get_instance(self, instance_id: str) -> AgentInstance | None:
        with self._lock:
            return self._instances.get(instance_id)

    def get_agent(self, instance_id: str) -> BaseAgent | None:
        with self._lock:
            return self._agents.get(instance_id)

    def stats(self) -> dict:
        with self._lock:
            roles: dict[str, dict] = {}
            for inst in self._instances.values():
                r = roles.setdefault(inst.role, {"total": 0, "idle": 0, "busy": 0, "error": 0})
                r["total"] += 1
                r[inst.status] = r.get(inst.status, 0) + 1
            return {
                "total_instances": len(self._instances),
                "by_role": roles,
            }

    def get_status(self) -> dict:
        """获取 pool 当前状态，供 Dashboard 查询。"""
        with self._lock:
            agents = []
            for inst in self._instances.values():
                agents.append(inst.to_dict())
            return {
                "total_instances": len(self._instances),
                "by_role": self.stats()["by_role"],
                "agents": agents,
            }

    def cleanup(self) -> None:
        """移除所有实例（workspace 目录保留，便于调试）。"""
        with self._lock:
            self._instances.clear()
            self._agents.clear()
            self._available.clear()
