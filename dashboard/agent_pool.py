"""AgentPool: 多实例 Agent 管理 + 文件锁冲突检测。"""

from dashboard.models import AgentInstance

# 实例上限
MAX_INSTANCES = {
    "backend": 3,
    "frontend": 3,
}
DEFAULT_MAX = 1  # 其他角色始终 1 个


class FileLockTable:
    """记录哪些文件正在被哪个 Agent 修改。"""

    def __init__(self):
        self._locks: dict[str, str] = {}  # path -> agent_id

    def acquire(self, agent_id: str, path: str) -> None:
        self._locks[path] = agent_id

    def release(self, agent_id: str, path: str) -> None:
        self._locks.pop(path, None)

    def release_all(self, agent_id: str) -> None:
        """释放某 Agent 持有的所有锁。"""
        self._locks = {p: aid for p, aid in self._locks.items() if aid != agent_id}

    def check_conflict(self, agent_id: str, path: str) -> str | None:
        """检查是否有冲突，返回持有锁的 agent_id，无冲突返回 None。"""
        holder = self._locks.get(path)
        if holder and holder != agent_id:
            return holder
        return None


class AgentPool:
    """管理所有 Agent 实例，提供实例查找和状态管理。"""

    def __init__(self):
        self.instances: list[AgentInstance] = []
        self._file_locks = FileLockTable()

    def add_instance(self, role: str, instance_number: int) -> None:
        max_allowed = MAX_INSTANCES.get(role, DEFAULT_MAX)
        current_count = sum(1 for i in self.instances if i.role == role)
        if current_count >= max_allowed:
            return
        instance = AgentInstance(
            id=f"{role}-{instance_number}",
            role=role,
            instance_number=instance_number,
        )
        self.instances.append(instance)

    def get_idle_instance(self, role: str) -> AgentInstance | None:
        for inst in self.instances:
            if inst.role == role and inst.status == "idle":
                return inst
        return None

    def set_instance_busy(self, instance_id: str, feature_id: str) -> None:
        for inst in self.instances:
            if inst.id == instance_id:
                inst.status = "busy"
                inst.current_feature = feature_id
                return

    def set_instance_idle(self, instance_id: str) -> None:
        for inst in self.instances:
            if inst.id == instance_id:
                inst.status = "idle"
                inst.current_feature = ""
                self._file_locks.release_all(instance_id)
                return

    def file_lock(self) -> FileLockTable:
        """返回文件锁表供外部使用。"""
        return self._file_locks

    def to_dict(self) -> list[dict]:
        return [inst.to_dict() for inst in self.instances]
