# 项目管理看板(Dashboard) 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建 AI 全自动开发平台的可视化项目管理看板，让甲方（用户）通过浏览器实时监控所有 Agent 状态、与 PM 对话交互、批准/驳回/调整任务方向。

**架构：** FastAPI 后端提供 REST API + WebSocket 推送，EventBus 作为状态上报中枢（内存队列 + 文件持久化），Next.js 14 前端通过 WebSocket 接收实时状态更新，通过 REST API 发送操作指令。多实例 Agent 通过 PM 层面的逻辑锁协调，不搞物理沙箱。

**技术栈：** FastAPI, websockets, Next.js 14 (App Router), Zustand, shadcn/ui, Tailwind CSS

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `dashboard/__init__.py` | Dashboard 模块入口 |
| `dashboard/event_bus.py` | EventBus：内存事件队列 + 文件追加持久化 |
| `dashboard/models.py` | 数据模型：AgentInstance, DashboardState, ChatMessage, Event |
| `dashboard/api.py` | REST API 路由 + WebSocket 端点 |
| `dashboard/agent_pool.py` | AgentPool：多实例管理、文件锁、冲突检测 |
| `dashboard/status_reporter.py` | StatusReporter：Agent 执行过程中上报状态到 EventBus |
| `dashboard/integration.py` | 集成入口：挂载到 FastAPI 主应用 |
| `dashboard-web/package.json` | Next.js 项目配置 |
| `dashboard-web/src/app/layout.tsx` | Next.js 根布局 |
| `dashboard-web/src/app/page.tsx` | 看板主页面 |
| `dashboard-web/src/app/globals.css` | 全局样式 (Tailwind) |
| `dashboard-web/src/lib/store.ts` | Zustand 状态管理 |
| `dashboard-web/src/lib/api.ts` | API 客户端 + WebSocket 连接管理 |
| `dashboard-web/src/components/kanban-board.tsx` | 看板三列布局 |
| `dashboard-web/src/components/agent-card.tsx` | Agent 状态卡片 |
| `dashboard-web/src/components/summary-bar.tsx` | 概览统计栏 |
| `dashboard-web/src/components/pm-chat.tsx` | PM 对话窗口 |
| `dashboard-web/src/components/log-stream.tsx` | 实时日志流 |
| `dashboard-web/src/components/log-panel.tsx` | 侧边日志弹窗 |
| `dashboard-web/src/components/action-buttons.tsx` | 操作按钮（暂停/重试/跳过） |
| `dashboard-web/src/components/chat-input.tsx` | 对话输入框 |
| `dashboard-web/tailwind.config.ts` | Tailwind 配置 |
| `dashboard-web/tsconfig.json` | TypeScript 配置 |
| `dashboard-web/next.config.js` | Next.js 配置（含 API proxy） |
| `dashboard-web/postcss.config.mjs` | PostCSS 配置 |
| `tests/test_event_bus.py` | EventBus 单元测试 |
| `tests/test_agent_pool.py` | AgentPool 单元测试 |
| `tests/test_dashboard_api.py` | Dashboard API 集成测试 |
| `tests/test_status_reporter.py` | StatusReporter 单元测试 |
| `tests/test_dashboard_e2e.py` | 看板端到端测试 |

### 修改文件

| 文件 | 修改范围 |
|------|---------|
| `core/feature_tracker.py` | 新增字段：`assigned_instance`, `workspace_path`, `files_changed`, `started_at` |
| `core/project_manager.py` | `_execute_feature()` 中接入 StatusReporter；新增 dashboard 操作 API 方法 |
| `agents/base_agent.py` | `execute()` 方法中上报状态到 EventBus |
| `main.py` | 挂载 dashboard API 路由 |
| `pyproject.toml` | 添加 `websockets` 依赖 |

---

### 任务 1：EventBus 核心实现

**文件：**
- 创建：`dashboard/__init__.py`
- 创建：`dashboard/event_bus.py`
- 测试：`tests/test_event_bus.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_event_bus.py
import json
import pytest
from pathlib import Path
from dashboard.event_bus import EventBus, Event

@pytest.fixture
def tmp_log_file(tmp_path: Path) -> Path:
    return tmp_path / "events.log"

@pytest.fixture
def bus(tmp_log_file: Path) -> EventBus:
    return EventBus(log_file=tmp_log_file)

def test_emit_adds_to_queue(bus: EventBus):
    bus.emit("agent_status_changed", agent_id="backend-1", feature_id="F001")
    events = bus.get_events()
    assert len(events) == 1
    assert events[0]["type"] == "agent_status_changed"
    assert events[0]["agent_id"] == "backend-1"

def test_emit_appends_to_log_file(bus: EventBus, tmp_log_file: Path):
    bus.emit("agent_log", agent_id="backend-1", feature_id="F001", message="test")
    lines = tmp_log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "agent_log"
    assert event["message"] == "test"

def test_get_events_since_timestamp(bus: EventBus):
    import time
    bus.emit("type1", data="first")
    time.sleep(0.1)
    cutoff = Event.now_iso()
    time.sleep(0.1)
    bus.emit("type2", data="second")
    recent = bus.get_events_since(cutoff)
    assert len(recent) == 1
    assert recent[0]["type"] == "type2"

def test_clear_log_file(bus: EventBus, tmp_log_file: Path):
    bus.emit("type1")
    bus.clear_log()
    assert not tmp_log_file.exists() or tmp_log_file.read_text().strip() == ""

def test_load_events_from_file(bus: EventBus, tmp_log_file: Path):
    tmp_log_file.write_text(json.dumps({"type": "old_event"}) + "\n")
    events = bus.load_recent_events(n=10)
    assert len(events) == 1
    assert events[0]["type"] == "old_event"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_event_bus.py -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'dashboard'"

- [ ] **步骤 3：实现 EventBus**

```python
# dashboard/__init__.py
from dashboard.event_bus import EventBus, Event

__all__ = ["EventBus", "Event"]
```

```python
# dashboard/event_bus.py
"""EventBus: 内存队列 + 文件持久化，用于 Dashboard 实时推送。"""

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Event:
    type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict = field(default_factory=dict)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {"type": self.type, "timestamp": self.timestamp, **self.data}


class EventBus:
    """线程安全的事件总线，支持内存队列 + 文件追加写入。"""

    def __init__(self, log_file: Path | None = None, max_queue: int = 1000):
        self._lock = threading.Lock()
        self._queue: deque[dict] = deque(maxlen=max_queue)
        self._log_file = log_file
        # 项目初始化时清空日志
        if self._log_file and self._log_file.exists():
            self.clear_log()

    def emit(self, event_type: str, **kwargs: Any) -> None:
        """发布事件到内存队列并追加到日志文件。"""
        event = Event(type=event_type, data=kwargs)
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        with self._lock:
            self._queue.append(event.to_dict())
            if self._log_file:
                self._log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(payload + "\n")

    def get_events(self) -> list[dict]:
        """获取当前内存队列中的所有事件。"""
        with self._lock:
            return list(self._queue)

    def get_events_since(self, timestamp: str) -> list[dict]:
        """获取指定时间戳之后的事件。"""
        with self._lock:
            return [e for e in self._queue if e["timestamp"] > timestamp]

    def load_recent_events(self, n: int = 100) -> list[dict]:
        """从日志文件加载最近 N 条事件。"""
        if not self._log_file or not self._log_file.exists():
            return []
        lines = self._log_file.read_text(encoding="utf-8").strip().split("\n")
        events = []
        for line in lines[-n:]:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def clear_log(self) -> None:
        """清空日志文件。"""
        if self._log_file and self._log_file.exists():
            self._log_file.unlink()

    @property
    def last_timestamp(self) -> str:
        """获取最后一个事件的时间戳。"""
        with self._lock:
            if self._queue:
                return self._queue[-1]["timestamp"]
            return Event.now_iso()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_event_bus.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/__init__.py dashboard/event_bus.py tests/test_event_bus.py
git commit -m "feat: implement EventBus with in-memory queue and file persistence"
```

---

### 任务 2：数据模型定义

**文件：**
- 创建：`dashboard/models.py`
- 测试：`tests/test_event_bus.py` (复用，补充模型测试)

- [ ] **步骤 1：编写失败的测试**

```python
# 追加到 tests/test_event_bus.py
from dashboard.models import AgentInstance, DashboardState, ChatMessage

def test_agent_instance_creation():
    agent = AgentInstance(id="backend-1", role="backend", instance_number=1)
    assert agent.status == "idle"
    assert agent.current_feature is None

def test_dashboard_state_counts():
    agents = [
        AgentInstance(id="b1", role="backend", instance_number=1, status="busy"),
        AgentInstance(id="b2", role="backend", instance_number=2, status="idle"),
    ]
    state = DashboardState(agents=agents, features=[], chat_messages=[])
    summary = state.summary()
    assert summary["total"] == 2
    assert summary["busy"] == 1
    assert summary["idle"] == 1

def test_chat_message_serialization():
    msg = ChatMessage(role="pm", content="test")
    d = msg.to_dict()
    assert d["role"] == "pm"
    assert d["content"] == "test"
    assert "timestamp" in d
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_event_bus.py::test_agent_instance_creation -v`
预期：FAIL，"ModuleNotFoundError: No module named 'dashboard.models'"

- [ ] **步骤 3：实现数据模型**

```python
# dashboard/models.py
"""Dashboard 数据模型定义。"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AgentInstance:
    id: str
    role: str
    instance_number: int
    status: str = "idle"  # idle, busy, paused, error
    current_feature: Optional[str] = None
    total_tasks_completed: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChatMessage:
    role: str  # "user" | "pm"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    action_triggered: Optional[str] = None  # "approve" | "reject" | "override" | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DashboardState:
    """完整状态快照，用于 WebSocket 推送和断线重连。"""
    agents: list[AgentInstance] = field(default_factory=list)
    features: list[dict] = field(default_factory=list)
    chat_messages: list[ChatMessage] = field(default_factory=list)
    last_event_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def summary(self) -> dict:
        total = len(self.agents)
        idle = sum(1 for a in self.agents if a.status == "idle")
        busy = sum(1 for a in self.agents if a.status == "busy")
        paused = sum(1 for a in self.agents if a.status == "paused")
        error = sum(1 for a in self.agents if a.status == "error")
        return {
            "total": total,
            "idle": idle,
            "busy": busy,
            "paused": paused,
            "error": error,
        }

    def to_dict(self) -> dict:
        return {
            "agents": [a.to_dict() for a in self.agents],
            "features": self.features,
            "chat_messages": [m.to_dict() for m in self.chat_messages],
            "last_event_timestamp": self.last_event_timestamp,
            "summary": self.summary(),
        }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_event_bus.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/models.py tests/test_event_bus.py
git commit -m "feat: add dashboard data models (AgentInstance, ChatMessage, DashboardState)"
```

---

### 任务 3：扩展 Feature 数据模型

**文件：**
- 修改：`core/feature_tracker.py`
- 测试：`tests/test_project_manager.py`

- [ ] **步骤 1：编写失败的测试**

```python
# 追加到 tests/test_project_manager.py
from core.feature_tracker import Feature

def test_feature_new_fields():
    f = Feature(
        id="F001",
        category="backend",
        description="test",
        priority="P0",
        assigned_to="backend",
        assigned_instance="backend-1",
        workspace_path="src/api/",
        files_changed=["src/api/users.py"],
        started_at="2026-04-18T14:20:00Z",
    )
    assert f.assigned_instance == "backend-1"
    assert f.workspace_path == "src/api/"
    assert f.started_at is not None

def test_feature_to_dict_includes_new_fields():
    f = Feature(
        id="F001", category="backend", description="test",
        priority="P0", assigned_to="backend",
        assigned_instance="backend-1",
    )
    d = f.to_dict()
    assert "assigned_instance" in d
    assert d["assigned_instance"] == "backend-1"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_project_manager.py::test_feature_new_fields -v`
预期：FAIL，"got an unexpected keyword argument 'assigned_instance'"

- [ ] **步骤 3：扩展 Feature dataclass**

```python
# 在 core/feature_tracker.py 的 Feature dataclass 中新增字段
@dataclass
class Feature:
    id: str
    category: str
    description: str
    priority: str
    assigned_to: str
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    passes: bool = False
    test_steps: list[str] = field(default_factory=list)
    error_log: list[str] = field(default_factory=list)
    completed_at: Optional[str] = None
    # 新增：Dashboard 看板需要的字段
    assigned_instance: Optional[str] = None       # 分配给的 Agent 实例 ID
    workspace_path: Optional[str] = None           # 工作目录
    files_changed: list[str] = field(default_factory=list)  # 修改的文件列表
    started_at: Optional[str] = None               # 开始执行时间
```

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_project_manager.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add core/feature_tracker.py tests/test_project_manager.py
git commit -m "feat: extend Feature model with dashboard fields (assigned_instance, workspace_path, files_changed, started_at)"
```

---

### 任务 4：StatusReporter 状态上报

**文件：**
- 创建：`dashboard/status_reporter.py`
- 测试：`tests/test_status_reporter.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_status_reporter.py
import pytest
from unittest.mock import MagicMock
from dashboard.status_reporter import StatusReporter


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    return bus

def test_report_status_change(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_status("backend-1", "F001", "idle", "busy")
    mock_bus.emit.assert_called_once_with(
        "agent_status_changed",
        agent_id="backend-1",
        feature_id="F001",
        old_status="idle",
        new_status="busy",
        project_id="proj-1",
    )

def test_report_log_message(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_log("backend-1", "F001", "created endpoint")
    mock_bus.emit.assert_called_once_with(
        "agent_log",
        agent_id="backend-1",
        feature_id="F001",
        message="created endpoint",
        project_id="proj-1",
    )

def test_report_feature_completed(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_feature_completed("F001", ["src/api/users.py"], "done")
    mock_bus.emit.assert_called_once_with(
        "feature_completed",
        feature_id="F001",
        files_changed=["src/api/users.py"],
        summary="done",
        project_id="proj-1",
    )

def test_report_error(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_error("F001", "backend-1", "connection timeout")
    mock_bus.emit.assert_called_once_with(
        "error_occurred",
        feature_id="F001",
        agent_id="backend-1",
        error_message="connection timeout",
        project_id="proj-1",
    )

def test_report_pm_decision(mock_bus):
    reporter = StatusReporter(event_bus=mock_bus, project_id="proj-1")
    reporter.report_pm_decision("start_F007", ["F007"], requires_approval=True)
    mock_bus.emit.assert_called_once_with(
        "pm_decision",
        decision="start_F007",
        next_actions=["F007"],
        requires_approval=True,
        project_id="proj-1",
    )
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_status_reporter.py -v`
预期：FAIL，"ModuleNotFoundError: No module named 'dashboard.status_reporter'"

- [ ] **步骤 3：实现 StatusReporter**

```python
# dashboard/status_reporter.py
"""StatusReporter: Agent 执行过程中上报状态到 EventBus。"""

from typing import Any


class StatusReporter:
    """封装 EventBus 调用，提供语义化的状态上报接口。"""

    def __init__(self, event_bus: Any, project_id: str):
        self._bus = event_bus
        self._project_id = project_id

    def report_status(self, agent_id: str, feature_id: str, old_status: str, new_status: str) -> None:
        """Agent 状态变化时调用。"""
        self._bus.emit(
            "agent_status_changed",
            agent_id=agent_id,
            feature_id=feature_id,
            old_status=old_status,
            new_status=new_status,
            project_id=self._project_id,
        )

    def report_log(self, agent_id: str, feature_id: str, message: str) -> None:
        """Agent 执行过程中产生日志时调用。"""
        self._bus.emit(
            "agent_log",
            agent_id=agent_id,
            feature_id=feature_id,
            message=message,
            project_id=self._project_id,
        )

    def report_feature_completed(self, feature_id: str, files_changed: list[str], summary: str) -> None:
        """Feature 完成时调用。"""
        self._bus.emit(
            "feature_completed",
            feature_id=feature_id,
            files_changed=files_changed,
            summary=summary,
            project_id=self._project_id,
        )

    def report_error(self, feature_id: str, agent_id: str, error_message: str) -> None:
        """执行出错时调用。"""
        self._bus.emit(
            "error_occurred",
            feature_id=feature_id,
            agent_id=agent_id,
            error_message=error_message,
            project_id=self._project_id,
        )

    def report_pm_decision(self, decision: str, next_actions: list[str], requires_approval: bool = False) -> None:
        """PM 做出调度决策时调用。"""
        self._bus.emit(
            "pm_decision",
            decision=decision,
            next_actions=next_actions,
            requires_approval=requires_approval,
            project_id=self._project_id,
        )
```

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_status_reporter.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/status_reporter.py tests/test_status_reporter.py
git commit -m "feat: implement StatusReporter for agent status reporting to EventBus"
```

---

### 任务 5：AgentPool 多实例协调

**文件：**
- 创建：`dashboard/agent_pool.py`
- 测试：`tests/test_agent_pool.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_agent_pool.py
import pytest
from dashboard.agent_pool import AgentPool, FileLockTable


def test_get_idle_instance():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    instance = pool.get_idle_instance("backend")
    assert instance is not None
    assert instance.id == "backend-1"

def test_no_idle_returns_none():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    pool.set_instance_busy("backend-1", "F001")
    instance = pool.get_idle_instance("backend")
    assert instance is None

def test_file_lock_no_conflict():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/api/users.py")
    conflict = locks.check_conflict("backend-2", "src/api/orders.py")
    assert conflict is None

def test_file_lock_has_conflict():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/api/users.py")
    conflict = locks.check_conflict("backend-2", "src/api/users.py")
    assert conflict == "backend-1"

def test_file_lock_release():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/api/users.py")
    locks.release("backend-1", "src/api/users.py")
    conflict = locks.check_conflict("backend-2", "src/api/users.py")
    assert conflict is None

def test_max_instances_backend():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    pool.add_instance("backend", 2)
    pool.add_instance("backend", 3)
    # 超过上限，不应该再添加
    pool.add_instance("backend", 4)  # 应该被忽略
    assert len([i for i in pool.instances if i.role == "backend"]) == 3

def test_max_instances_frontend():
    pool = AgentPool()
    pool.add_instance("frontend", 1)
    pool.add_instance("frontend", 2)
    pool.add_instance("frontend", 3)
    pool.add_instance("frontend", 4)
    assert len([i for i in pool.instances if i.role == "frontend"]) == 3

def test_other_roles_single_instance():
    pool = AgentPool()
    pool.add_instance("database", 1)
    pool.add_instance("database", 2)
    assert len([i for i in pool.instances if i.role == "database"]) == 1
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_agent_pool.py -v`
预期：FAIL，"ModuleNotFoundError"

- [ ] **步骤 3：实现 AgentPool**

```python
# dashboard/agent_pool.py
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
            return  # 超过上限，忽略
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
                inst.current_feature = None
                inst.total_tasks_completed += 1
                self._file_locks.release_all(instance_id)
                return

    def set_instance_paused(self, instance_id: str) -> None:
        for inst in self.instances:
            if inst.id == instance_id:
                inst.status = "paused"
                return

    def set_instance_error(self, instance_id: str) -> None:
        for inst in self.instances:
            if inst.id == instance_id:
                inst.status = "error"
                return

    def acquire_file_lock(self, agent_id: str, path: str) -> bool:
        """尝试获取文件锁，返回是否成功。"""
        conflict = self._file_locks.check_conflict(agent_id, path)
        if conflict:
            return False
        self._file_locks.acquire(agent_id, path)
        return True

    def release_file_lock(self, agent_id: str, path: str) -> None:
        self._file_locks.release(agent_id, path)

    def check_file_conflict(self, agent_id: str, paths: list[str]) -> str | None:
        """检查一组文件路径是否与正在执行的其他 Agent 冲突。"""
        for path in paths:
            conflict = self._file_locks.check_conflict(agent_id, path)
            if conflict:
                return conflict
        return None

    def get_state(self) -> list[dict]:
        return [inst.to_dict() for inst in self.instances]
```

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_agent_pool.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/agent_pool.py tests/test_agent_pool.py
git commit -m "feat: implement AgentPool with multi-instance management and file lock conflict detection"
```

---

### 任务 6：REST API 路由实现

**文件：**
- 创建：`dashboard/api.py`
- 修改：`core/config.py`（新增 DASHBOARD_DATA_DIR 配置）
- 测试：`tests/test_dashboard_api.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_dashboard_api.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from dashboard.event_bus import EventBus
from dashboard.models import DashboardState, AgentInstance, ChatMessage
from dashboard.agent_pool import AgentPool


@pytest.fixture
def setup_api(tmp_path: Path):
    """创建包含 API router 的 FastAPI 应用。"""
    from fastapi import FastAPI
    event_bus = EventBus(log_file=tmp_path / "events.log")
    agent_pool = AgentPool()
    agent_pool.add_instance("backend", 1)
    agent_pool.add_instance("frontend", 1)

    chat_file = tmp_path / "chat.json"
    chat_file.write_text("[]")

    from dashboard.api import create_dashboard_router
    app = FastAPI()
    router = create_dashboard_router(
        event_bus=event_bus,
        agent_pool=agent_pool,
        chat_file=chat_file,
        project_dir=tmp_path,
    )
    app.include_router(router, prefix="/api/dashboard")
    return TestClient(app), event_bus, agent_pool, chat_file


def test_get_state_returns_agents(setup_api):
    client, _, _, _ = setup_api
    resp = client.get("/api/dashboard/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert len(data["agents"]) == 2


def test_chat_sends_message(setup_api):
    client, event_bus, _, chat_file = setup_api
    resp = client.post("/api/dashboard/chat", json={
        "role": "user",
        "content": "F007 改成做积分系统",
    })
    assert resp.status_code == 200
    messages = json.loads(chat_file.read_text())
    assert len(messages) == 1
    assert messages[0]["content"] == "F007 改成做积分系统"


def test_approve_action_emits_event(setup_api):
    client, event_bus, _, _ = setup_api
    resp = client.post("/api/dashboard/approve", json={
        "decision": "start_F007",
    })
    assert resp.status_code == 200
    events = event_bus.get_events()
    assert any(e["type"] == "pm_decision" for e in events)


def test_reject_action_emits_event(setup_api):
    client, event_bus, _, _ = setup_api
    resp = client.post("/api/dashboard/reject", json={
        "decision": "start_F007",
    })
    assert resp.status_code == 200
    events = event_bus.get_events()
    assert any(e["type"] == "pm_decision" and e.get("rejected") for e in events)


def test_pause_agent(setup_api):
    client, _, pool, _ = setup_api
    pool.set_instance_busy("backend-1", "F001")
    resp = client.post("/api/dashboard/pause", json={
        "agent_id": "backend-1",
    })
    assert resp.status_code == 200
    inst = pool.instances[0]
    assert inst.status == "paused"


def test_resume_agent(setup_api):
    client, _, pool, _ = setup_api
    pool.set_instance_paused("backend-1")
    resp = client.post("/api/dashboard/resume", json={
        "agent_id": "backend-1",
    })
    assert resp.status_code == 200
    inst = pool.instances[0]
    assert inst.status == "busy"


def test_retry_feature(setup_api):
    client, event_bus, _, _ = setup_api
    resp = client.post("/api/dashboard/retry", json={
        "feature_id": "F001",
    })
    assert resp.status_code == 200


def test_skip_feature(setup_api):
    client, event_bus, _, _ = setup_api
    resp = client.post("/api/dashboard/skip", json={
        "feature_id": "F001",
    })
    assert resp.status_code == 200
```

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_dashboard_api.py -v`
预期：FAIL

- [ ] **步骤 3：实现 REST API 路由**

```python
# dashboard/api.py
"""Dashboard REST API + WebSocket 端点。"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from dashboard.event_bus import EventBus
from dashboard.models import ChatMessage, DashboardState
from dashboard.agent_pool import AgentPool


def create_dashboard_router(
    event_bus: EventBus,
    agent_pool: AgentPool,
    chat_file: Path,
    project_dir: Path,
) -> APIRouter:
    router = APIRouter()
    connected_clients: list[WebSocket] = []

    @router.get("/state")
    def get_state() -> dict:
        """获取当前完整状态快照。"""
        state = _build_state(event_bus, agent_pool, chat_file)
        return state.to_dict()

    @router.post("/chat")
    def post_chat(role: str = "user", content: str = "") -> dict:
        """甲方给 PM 发消息。"""
        msg = ChatMessage(role=role, content=content)
        _save_chat_message(chat_file, msg)
        event_bus.emit("pm_chat", role=role, content=content)
        return {"status": "ok", "message": msg.to_dict()}

    @router.post("/approve")
    def approve(decision: str) -> dict:
        """批准 PM 的下一步计划。"""
        event_bus.emit("pm_decision", decision=decision, approved=True)
        return {"status": "approved", "decision": decision}

    @router.post("/reject")
    def reject(decision: str) -> dict:
        """驳回 PM 的计划。"""
        event_bus.emit("pm_decision", decision=decision, rejected=True)
        return {"status": "rejected", "decision": decision}

    @router.post("/pause")
    def pause(agent_id: str) -> dict:
        """暂停指定 Agent。"""
        agent_pool.set_instance_paused(agent_id)
        event_bus.emit("agent_status_changed", agent_id=agent_id, new_status="paused")
        return {"status": "paused", "agent_id": agent_id}

    @router.post("/resume")
    def resume(agent_id: str) -> dict:
        """恢复指定 Agent。"""
        agent_pool.set_instance_busy(agent_id, "unknown")  # TODO: 从 feature tracker 获取
        event_bus.emit("agent_status_changed", agent_id=agent_id, new_status="busy")
        return {"status": "resumed", "agent_id": agent_id}

    @router.post("/retry")
    def retry(feature_id: str) -> dict:
        """重试失败 Feature。"""
        event_bus.emit("feature_retry", feature_id=feature_id)
        return {"status": "retried", "feature_id": feature_id}

    @router.post("/skip")
    def skip(feature_id: str) -> dict:
        """跳过阻塞 Feature。"""
        event_bus.emit("feature_skipped", feature_id=feature_id)
        return {"status": "skipped", "feature_id": feature_id}

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        connected_clients.append(websocket)
        try:
            # 推送完整状态快照
            state = _build_state(event_bus, agent_pool, chat_file)
            await websocket.send_json({"type": "state_snapshot", "data": state.to_dict()})
            while True:
                # 接收心跳
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            connected_clients.remove(websocket)

    return router


def _build_state(event_bus: EventBus, agent_pool: AgentPool, chat_file: Path) -> DashboardState:
    messages = []
    if chat_file.exists():
        data = json.loads(chat_file.read_text(encoding="utf-8") or "[]")
        messages = [ChatMessage(**m) for m in data]

    features = []
    features_file = Path(chat_file).parent / "features.json"
    if features_file.exists():
        raw = json.loads(features_file.read_text(encoding="utf-8"))
        features = raw if isinstance(raw, list) else raw.get("features", [])

    return DashboardState(
        agents=[AgentInstance(**{**i, "status": i.get("status", "idle")}) for i in agent_pool.get_state()],
        features=features,
        chat_messages=messages,
        last_event_timestamp=event_bus.last_timestamp,
    )


def _save_chat_message(chat_file: Path, msg: ChatMessage) -> None:
    messages = []
    if chat_file.exists():
        messages = json.loads(chat_file.read_text(encoding="utf-8") or "[]")
    messages.append(msg.to_dict())
    chat_file.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_dashboard_api.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/api.py tests/test_dashboard_api.py
git commit -m "feat: implement Dashboard REST API routes and WebSocket endpoint"
```

---

### 任务 7：集成到主应用

**文件：**
- 创建：`dashboard/integration.py`
- 修改：`pyproject.toml`（添加 websockets 依赖）
- 修改：`core/project_manager.py`（在 `_execute_feature` 中接入 StatusReporter）

- [ ] **步骤 1：创建集成入口**

```python
# dashboard/integration.py
"""Dashboard 集成：挂载到 FastAPI 主应用 + 初始化 EventBus/AgentPool。"""

from pathlib import Path
from fastapi import FastAPI
from dashboard.event_bus import EventBus
from dashboard.agent_pool import AgentPool


def init_dashboard(app: FastAPI, project_dir: Path) -> dict:
    """初始化 Dashboard 并挂载到 FastAPI 应用。返回 dashboard 组件字典。"""
    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    event_bus = EventBus(log_file=data_dir / "events.log")
    agent_pool = AgentPool()

    # 默认每角色 1 个实例
    for role in ["backend", "frontend", "database", "qa", "security", "ui", "docs", "architect"]:
        agent_pool.add_instance(role, 1)

    chat_file = data_dir / "chat.json"
    if not chat_file.exists():
        chat_file.write_text("[]")

    from dashboard.api import create_dashboard_router
    router = create_dashboard_router(
        event_bus=event_bus,
        agent_pool=agent_pool,
        chat_file=chat_file,
        project_dir=project_dir,
    )
    app.include_router(router, prefix="/api/dashboard")

    return {
        "event_bus": event_bus,
        "agent_pool": agent_pool,
        "chat_file": chat_file,
    }
```

- [ ] **步骤 2：修改 project_manager 接入 StatusReporter**

在 `core/project_manager.py` 的 `_execute_feature` 方法开头添加状态上报：

```python
# 在 ProjectManager.__init__ 中添加
from typing import Optional
from dashboard.status_reporter import StatusReporter

# 在 __init__ 中添加
self._status_reporter: Optional[StatusReporter] = None

# 新增方法
def attach_status_reporter(self, reporter: StatusReporter) -> None:
    """绑定 StatusReporter，用于向 Dashboard 上报状态。"""
    self._status_reporter = reporter

# 修改 _execute_feature 方法，在开头和结尾添加状态上报
def _execute_feature(self, feature: Feature) -> None:
    """执行单个feature"""
    self.feature_tracker.mark_in_progress(feature.id)
    feature.started_at = __import__("datetime").datetime.now().isoformat()

    # 上报：Agent 开始执行
    if self._status_reporter:
        self._status_reporter.report_status(
            agent_id=feature.assigned_instance or feature.assigned_to,
            feature_id=feature.id,
            old_status="idle",
            new_status="busy",
        )

    # 构建任务描述
    task_description = self._build_task_description(feature)

    # ... (其余代码不变)
```

- [ ] **步骤 3：添加 websockets 依赖**

```toml
# 在 pyproject.toml 的 dependencies 中追加
"websockets>=12.0",
```

- [ ] **步骤 4：运行导入测试**

运行：`uv run python -c "from dashboard import *; from dashboard.integration import init_dashboard"`
预期：无报错

- [ ] **步骤 5：Commit**

```bash
git add dashboard/integration.py core/project_manager.py pyproject.toml
git commit -m "feat: integrate dashboard into main FastAPI application with StatusReporter hooks"
```

---

### 任务 8：Next.js 前端初始化

**文件：**
- 创建：`dashboard-web/package.json`
- 创建：`dashboard-web/next.config.js`
- 创建：`dashboard-web/tsconfig.json`
- 创建：`dashboard-web/tailwind.config.ts`
- 创建：`dashboard-web/postcss.config.mjs`
- 创建：`dashboard-web/src/app/layout.tsx`
- 创建：`dashboard-web/src/app/globals.css`

- [ ] **步骤 1：初始化 Next.js 项目**

```bash
cd dashboard-web
npm init -y
```

- [ ] **步骤 2：创建 package.json**

```json
{
  "name": "dashboard-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3568",
    "build": "next build",
    "start": "next start -p 3568",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "ws": "^8.16.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.2.0",
    "lucide-react": "^0.363.0"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@types/ws": "^8.5.10",
    "autoprefixer": "^10.4.18",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.4.0"
  }
}
```

- [ ] **步骤 3：创建配置文件**

```javascript
// dashboard-web/next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/dashboard/:path*",
        destination: "http://localhost:8000/api/dashboard/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
```

```json
// dashboard-web/tsconfig.json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

```typescript
// dashboard-web/tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
export default config;
```

```javascript
// dashboard-web/postcss.config.mjs
/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
export default config;
```

- [ ] **步骤 4：创建根布局**

```tsx
// dashboard-web/src/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI全自动开发平台 — 项目管理看板",
  description: "实时监控 Agent 状态，与 PM 对话，审查产出，批准/驳回任务方向",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-gray-50 text-gray-900">{children}</body>
    </html>
  );
}
```

```css
/* dashboard-web/src/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
```

- [ ] **步骤 5：安装依赖并验证构建**

```bash
cd dashboard-web && npm install && npm run build
```

预期：构建成功

- [ ] **步骤 6：Commit**

```bash
git add dashboard-web/
git commit -m "feat: initialize Next.js frontend project with Tailwind CSS on port 3568"
```

---

### 任务 9：前端状态管理 + API 客户端

**文件：**
- 创建：`dashboard-web/src/lib/store.ts`
- 创建：`dashboard-web/src/lib/api.ts`

- [ ] **步骤 1：创建 Zustand Store**

```typescript
// dashboard-web/src/lib/store.ts
import { create } from "zustand";

export interface Agent {
  id: string;
  role: string;
  instance_number: number;
  status: "idle" | "busy" | "paused" | "error";
  current_feature: string | null;
  total_tasks_completed: number;
  started_at: string;
}

export interface ChatMessage {
  role: "user" | "pm";
  content: string;
  timestamp: string;
  action_triggered?: string;
}

export interface LogEntry {
  agent_id: string;
  feature_id: string;
  message: string;
  timestamp: string;
}

interface DashboardState {
  agents: Agent[];
  features: any[];
  chatMessages: ChatMessage[];
  logs: LogEntry[];
  summary: { total: number; idle: number; busy: number; paused: number; error: number };
  wsConnected: boolean;

  // Actions
  setAgents: (agents: Agent[]) => void;
  setFeatures: (features: any[]) => void;
  addChatMessage: (msg: ChatMessage) => void;
  addLog: (entry: LogEntry) => void;
  updateAgentStatus: (agentId: string, status: Agent["status"]) => void;
  setWsConnected: (connected: boolean) => void;
}

export const useStore = create<DashboardState>((set) => ({
  agents: [],
  features: [],
  chatMessages: [],
  logs: [],
  summary: { total: 0, idle: 0, busy: 0, paused: 0, error: 0 },
  wsConnected: false,

  setAgents: (agents) =>
    set((state) => ({
      agents,
      summary: {
        total: agents.length,
        idle: agents.filter((a) => a.status === "idle").length,
        busy: agents.filter((a) => a.status === "busy").length,
        paused: agents.filter((a) => a.status === "paused").length,
        error: agents.filter((a) => a.status === "error").length,
      },
    })),

  setFeatures: (features) => set({ features }),

  addChatMessage: (msg) =>
    set((state) => ({ chatMessages: [...state.chatMessages, msg] })),

  addLog: (entry) =>
    set((state) => ({ logs: [entry, ...state.logs].slice(0, 200) })),

  updateAgentStatus: (agentId, status) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.id === agentId ? { ...a, status } : a
      ),
    })),

  setWsConnected: (wsConnected) => set({ wsConnected }),
}));
```

- [ ] **步骤 2：创建 API 客户端 + WebSocket 管理**

```typescript
// dashboard-web/src/lib/api.ts
import { useStore } from "./store";
import type { ChatMessage, LogEntry } from "./store";

const API_BASE = "/api/dashboard";

export async function fetchState() {
  const res = await fetch(`${API_BASE}/state`);
  return res.json();
}

export async function sendChat(content: string) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: "user", content }),
  });
  return res.json();
}

export async function approve(decision: string) {
  const res = await fetch(`${API_BASE}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  return res.json();
}

export async function reject(decision: string) {
  const res = await fetch(`${API_BASE}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  return res.json();
}

export async function pauseAgent(agentId: string) {
  const res = await fetch(`${API_BASE}/pause`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId }),
  });
  return res.json();
}

export async function resumeAgent(agentId: string) {
  const res = await fetch(`${API_BASE}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId }),
  });
  return res.json();
}

export async function retryFeature(featureId: string) {
  const res = await fetch(`${API_BASE}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feature_id: featureId }),
  });
  return res.json();
}

export async function skipFeature(featureId: string) {
  const res = await fetch(`${API_BASE}/skip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feature_id: featureId }),
  });
  return res.json();
}

// WebSocket 连接管理
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWebSocket(onReconnect?: () => Promise<void>) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/dashboard/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    useStore.getState().setWsConnected(true);
    // 启动心跳
    startHeartbeat();
  };

  ws.onmessage = (event) => {
    const data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
    handleWsMessage(data);
  };

  ws.onclose = () => {
    useStore.getState().setWsConnected(false);
    stopHeartbeat();
    // 3秒后重连
    reconnectTimer = setTimeout(() => {
      connectWebSocket(onReconnect);
    }, 3000);
  };

  ws.onerror = () => {
    ws?.close();
  };
}

function handleWsMessage(data: any) {
  const store = useStore.getState();

  if (data.type === "state_snapshot") {
    store.setAgents(data.data.agents || []);
    store.setFeatures(data.data.features || []);
    // 初始化 chatMessages
    if (data.data.chat_messages) {
      store.chatMessages.length = 0; // 清空
      data.data.chat_messages.forEach((m: ChatMessage) => store.addChatMessage(m));
    }
  } else if (data.type === "agent_status_changed") {
    store.updateAgentStatus(data.agent_id, data.new_status);
  } else if (data.type === "agent_log") {
    store.addLog({
      agent_id: data.agent_id,
      feature_id: data.feature_id,
      message: data.message,
      timestamp: data.timestamp,
    });
  } else if (data.type === "feature_completed") {
    // Feature 完成，刷新状态
    fetchState().then((state) => {
      store.setAgents(state.agents);
      store.setFeatures(state.features);
    });
  } else if (data.type === "pm_chat") {
    if (data.role === "pm") {
      store.addChatMessage({
        role: "pm",
        content: data.content,
        timestamp: data.timestamp,
        action_triggered: data.requires_approval ? "approval" : undefined,
      });
    }
  } else if (data.type === "pm_decision") {
    store.addChatMessage({
      role: "pm",
      content: `调度决策：${data.decision}`,
      timestamp: data.timestamp,
      action_triggered: data.requires_approval ? "approval" : undefined,
    });
  } else if (data.type === "pong") {
    // 心跳回复，忽略
  }
}

let heartbeatInterval: ReturnType<typeof setInterval> | null = null;

function startHeartbeat() {
  heartbeatInterval = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send("ping");
    }
  }, 30000);
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

export function disconnectWebSocket() {
  stopHeartbeat();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
}
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard-web/src/lib/
git commit -m "feat: implement Zustand store and WebSocket API client for real-time updates"
```

---

### 任务 10：看板主页面 + 组件

**文件：**
- 创建：`dashboard-web/src/app/page.tsx`
- 创建：`dashboard-web/src/components/kanban-board.tsx`
- 创建：`dashboard-web/src/components/agent-card.tsx`
- 创建：`dashboard-web/src/components/summary-bar.tsx`
- 创建：`dashboard-web/src/components/pm-chat.tsx`
- 创建：`dashboard-web/src/components/log-stream.tsx`
- 创建：`dashboard-web/src/components/action-buttons.tsx`
- 创建：`dashboard-web/src/components/chat-input.tsx`
- 创建：`dashboard-web/src/components/log-panel.tsx`

- [ ] **步骤 1：创建看板主页面**

```tsx
// dashboard-web/src/app/page.tsx
"use client";

import { useEffect } from "react";
import { connectWebSocket, fetchState } from "@/lib/api";
import { useStore } from "@/lib/store";
import { SummaryBar } from "@/components/summary-bar";
import { KanbanBoard } from "@/components/kanban-board";
import { PmChat } from "@/components/pm-chat";
import { LogStream } from "@/components/log-stream";

export default function DashboardPage() {
  const { setAgents, setFeatures, wsConnected } = useStore();

  useEffect(() => {
    // 初始加载
    fetchState().then((state) => {
      setAgents(state.agents || []);
      setFeatures(state.features || []);
    });

    // 连接 WebSocket
    connectWebSocket(async () => {
      // 重连后补全状态
      const state = await fetchState();
      setAgents(state.agents || []);
      setFeatures(state.features || []);
    });

    return () => {
      // cleanup 在页面卸载时断开
    };
  }, [setAgents, setFeatures]);

  return (
    <div className="flex flex-col h-screen">
      <header className="px-6 py-3 bg-white border-b border-gray-200 flex items-center justify-between">
        <h1 className="text-xl font-semibold">AI全自动开发平台 — 项目管理看板</h1>
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${wsConnected ? "bg-green-500" : "bg-red-500"}`} />
          <span className="text-sm text-gray-500">{wsConnected ? "已连接" : "断开中"}</span>
        </div>
      </header>

      <SummaryBar />

      <div className="flex-1 overflow-hidden flex flex-col lg:flex-row">
        <div className="flex-1 overflow-auto p-4">
          <KanbanBoard />
        </div>

        <div className="w-full lg:w-96 border-l border-gray-200 flex flex-col bg-white">
          <PmChat />
          <div className="border-t border-gray-200">
            <LogStream />
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **步骤 2：创建概览栏**

```tsx
// dashboard-web/src/components/summary-bar.tsx
import { useStore } from "@/lib/store";

export function SummaryBar() {
  const { summary } = useStore();
  return (
    <div className="px-6 py-2 bg-gray-100 border-b border-gray-200 flex gap-6 text-sm">
      <span><strong>总计:</strong> {summary.total}</span>
      <span><strong>空闲:</strong> {summary.idle}</span>
      <span><strong>运行中:</strong> {summary.busy}</span>
      <span><strong>暂停:</strong> {summary.paused}</span>
      <span><strong>错误:</strong> {summary.error}</span>
    </div>
  );
}
```

- [ ] **步骤 3：创建看板三列布局**

```tsx
// dashboard-web/src/components/kanban-board.tsx
import { useStore, type Agent } from "@/lib/store";
import { AgentCard } from "./agent-card";

function groupByStatus(agents: Agent[]) {
  const done: Agent[] = [];
  const inProgress: Agent[] = [];
  const pending: Agent[] = [];
  const blocked: Agent[] = [];

  for (const a of agents) {
    if (a.status === "idle") done.push(a);
    else if (a.status === "busy") inProgress.push(a);
    else if (a.status === "error") blocked.push(a);
    else pending.push(a);
  }

  return { done, inProgress, pending, blocked };
}

export function KanbanBoard() {
  const { agents } = useStore();
  const { done, inProgress, pending, blocked } = groupByStatus(agents);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <KanbanColumn title="✅ 已完成 (Done)" agents={done} variant="done" />
      <KanbanColumn title="🔄 进行中" agents={inProgress} variant="progress" />
      <div className="space-y-4">
        <KanbanColumn title="⏳ 等待中" agents={pending} variant="pending" />
        <KanbanColumn title="🚫 阻塞" agents={blocked} variant="blocked" />
      </div>
    </div>
  );
}

function KanbanColumn({
  title,
  agents,
  variant,
}: {
  title: string;
  agents: Agent[];
  variant: "done" | "progress" | "pending" | "blocked";
}) {
  const bgClass = variant === "done" ? "bg-green-50" :
    variant === "progress" ? "bg-blue-50" :
    variant === "blocked" ? "bg-red-50" : "bg-gray-50";

  return (
    <div className={`${bgClass} rounded-lg p-3`}>
      <h3 className="font-medium text-sm mb-3">{title} ({agents.length})</h3>
      <div className="space-y-2">
        {agents.map((agent) => (
          <AgentCard key={agent.id} agent={agent} variant={variant} />
        ))}
        {agents.length === 0 && (
          <p className="text-gray-400 text-sm">无</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **步骤 4：创建 Agent 卡片**

```tsx
// dashboard-web/src/components/agent-card.tsx
import type { Agent } from "@/lib/store";
import { pauseAgent, resumeAgent } from "@/lib/api";
import { Pause, Play, Loader2, AlertCircle } from "lucide-react";

const roleIcons: Record<string, string> = {
  backend: "🤖",
  frontend: "🎨",
  database: "🗄️",
  qa: "🧪",
  security: "🔒",
  ui: "🖌️",
  docs: "📝",
  architect: "📐",
};

export function AgentCard({ agent, variant }: { agent: Agent; variant: string }) {
  const icon = roleIcons[agent.role] || "🤖";
  const label = `${icon} ${agent.role.charAt(0).toUpperCase() + agent.role.slice(1)} #${agent.instance_number}`;
  const feature = agent.current_feature || "无任务";

  return (
    <div className="bg-white rounded-md p-3 shadow-sm border border-gray-200">
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium text-sm">{label}</span>
        {variant === "progress" && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
        {variant === "blocked" && <AlertCircle className="w-4 h-4 text-red-500" />}
      </div>
      <p className="text-xs text-gray-500 mb-2">当前: {feature}</p>
      {variant === "progress" && (
        <div className="flex gap-1">
          <button
            onClick={() => pauseAgent(agent.id)}
            className="text-xs px-2 py-1 bg-yellow-100 hover:bg-yellow-200 rounded flex items-center gap-1"
          >
            <Pause className="w-3 h-3" /> 暂停
          </button>
        </div>
      )}
      {variant === "blocked" && (
        <div className="flex gap-1">
          <button
            onClick={() => resumeAgent(agent.id)}
            className="text-xs px-2 py-1 bg-green-100 hover:bg-green-200 rounded flex items-center gap-1"
          >
            <Play className="w-3 h-3" /> 重试
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **步骤 5：创建 PM 对话窗口**

```tsx
// dashboard-web/src/components/pm-chat.tsx
import { useRef, useEffect } from "react";
import { useStore } from "@/lib/store";
import { ChatInput } from "./chat-input";

export function PmChat() {
  const { chatMessages } = useStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  return (
    <div className="flex flex-col h-1/2 min-h-[200px]">
      <div className="px-4 py-2 border-b border-gray-200 bg-gray-50">
        <h2 className="font-medium text-sm">💬 PM 对话窗口</h2>
      </div>
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {chatMessages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
              msg.role === "user"
                ? "bg-blue-500 text-white"
                : "bg-gray-100 text-gray-900"
            }`}>
              <p>{msg.content}</p>
              <p className="text-xs opacity-60 mt-1">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <ChatInput />
    </div>
  );
}
```

- [ ] **步骤 6：创建对话输入框**

```tsx
// dashboard-web/src/components/chat-input.tsx
import { useState } from "react";
import { sendChat, approve, reject } from "@/lib/api";
import { useStore } from "@/lib/store";
import { Check, X, Send } from "lucide-react";

export function ChatInput() {
  const [input, setInput] = useState("");
  const { chatMessages } = useStore();
  const lastMsg = chatMessages[chatMessages.length - 1];
  const needsApproval = lastMsg?.role === "pm" && lastMsg?.action_triggered === "approval";

  const handleSend = async () => {
    if (!input.trim()) return;
    await sendChat(input.trim());
    setInput("");
  };

  const handleApprove = async () => {
    await approve(lastMsg.content);
  };

  const handleReject = async () => {
    await reject(lastMsg.content);
  };

  return (
    <div className="border-t border-gray-200 p-3">
      {needsApproval && (
        <div className="flex gap-2 mb-2">
          <button onClick={handleApprove} className="text-xs px-3 py-1 bg-green-100 text-green-700 rounded flex items-center gap-1">
            <Check className="w-3 h-3" /> 批准
          </button>
          <button onClick={handleReject} className="text-xs px-3 py-1 bg-red-100 text-red-700 rounded flex items-center gap-1">
            <X className="w-3 h-3" /> 驳回
          </button>
        </div>
      )}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="输入指令..."
          className="flex-1 text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleSend}
          className="px-3 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
```

- [ ] **步骤 7：创建实时日志流**

```tsx
// dashboard-web/src/components/log-stream.tsx
import { useRef, useEffect } from "react";
import { useStore } from "@/lib/store";

export function LogStream() {
  const { logs } = useStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="h-1/2 min-h-[150px] flex flex-col">
      <div className="px-4 py-2 border-b border-gray-200 bg-gray-50">
        <h2 className="font-medium text-sm">📋 实时日志流</h2>
      </div>
      <div className="flex-1 overflow-auto p-3 font-mono text-xs space-y-1 bg-gray-900 text-green-400">
        {logs.map((log, i) => (
          <div key={i} className="truncate">
            <span className="text-gray-500">{new Date(log.timestamp).toLocaleTimeString()}</span>
            {" "}
            <span className="text-yellow-400">[{log.agent_id}]</span>
            {" "}
            {log.message}
          </div>
        ))}
        {logs.length === 0 && (
          <p className="text-gray-600">暂无日志</p>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
```

- [ ] **步骤 8：运行 dev server 验证 UI**

```bash
cd dashboard-web && npm run dev
```

打开 http://localhost:3568 验证看板布局正常显示。

- [ ] **步骤 9：Commit**

```bash
git add dashboard-web/src/
git commit -m "feat: build kanban board UI with agent cards, PM chat, and real-time log stream"
```

---

### 任务 11：端到端集成测试

**文件：**
- 创建：`tests/test_dashboard_e2e.py`

- [ ] **步骤 1：编写端到端测试**

```python
# tests/test_dashboard_e2e.py
"""Dashboard 端到端集成测试：启动 FastAPI + WebSocket + 前端模拟。"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from dashboard.event_bus import EventBus
from dashboard.agent_pool import AgentPool
from dashboard.api import create_dashboard_router


@pytest.fixture
def dashboard_app(tmp_path: Path):
    """创建完整的 Dashboard FastAPI 应用。"""
    event_bus = EventBus(log_file=tmp_path / "events.log")
    agent_pool = AgentPool()
    for role in ["backend", "frontend", "database"]:
        agent_pool.add_instance(role, 1)

    chat_file = tmp_path / "chat.json"
    chat_file.write_text("[]")

    features_file = tmp_path / "features.json"
    features_file.write_text(json.dumps([
        {"id": "F001", "category": "backend", "description": "test", "priority": "P0",
         "assigned_to": "backend", "status": "pending", "assigned_instance": "backend-1"}
    ]))

    app = FastAPI()
    router = create_dashboard_router(
        event_bus=event_bus,
        agent_pool=agent_pool,
        chat_file=chat_file,
        project_dir=tmp_path,
    )
    app.include_router(router, prefix="/api/dashboard")
    return TestClient(app), event_bus, agent_pool, chat_file


def test_full_workflow(dashboard_app):
    """模拟完整工作流：查看状态 → PM 推送决策 → 用户批准 → Agent 状态变化。"""
    client, event_bus, pool, _ = dashboard_app

    # 1. 查看初始状态
    resp = client.get("/api/dashboard/state")
    assert resp.status_code == 200
    state = resp.json()
    assert len(state["agents"]) == 3

    # 2. 模拟 PM 推送决策
    event_bus.emit("pm_decision", decision="start_F001", requires_approval=True)

    # 3. 用户批准
    resp = client.post("/api/dashboard/approve", json={"decision": "start_F001"})
    assert resp.status_code == 200

    # 4. Agent 开始工作
    pool.set_instance_busy("backend-1", "F001")
    event_bus.emit("agent_status_changed", agent_id="backend-1", old_status="idle", new_status="busy")
    event_bus.emit("agent_log", agent_id="backend-1", feature_id="F001", message="开始开发")

    # 5. 验证状态变化
    resp = client.get("/api/dashboard/state")
    agents = resp.json()["agents"]
    backend = next(a for a in agents if a["id"] == "backend-1")
    assert backend["status"] == "busy"

    # 6. 验证事件日志已写入
    events = event_bus.get_events()
    assert len(events) >= 3


def test_websocket_reconnect(dashboard_app):
    """测试 WebSocket 断线重连后能收到完整状态。"""
    client, event_bus, pool, _ = dashboard_app

    with client.websocket_connect("/api/dashboard/ws") as ws:
        # 接收初始状态
        data = ws.receive_json()
        assert data["type"] == "state_snapshot"
        assert len(data["data"]["agents"]) == 3

        # 发送心跳
        ws.send_text("ping")
        pong = ws.receive_text()
        assert pong == "pong"


def test_chat_workflow(dashboard_app):
    """测试对话流程：用户发消息 → 保存到文件 → 可通过状态获取。"""
    client, _, _, chat_file = dashboard_app

    resp = client.post("/api/dashboard/chat", json={
        "role": "user",
        "content": "F007 先不做支付，改成做积分系统",
    })
    assert resp.status_code == 200

    messages = json.loads(chat_file.read_text())
    assert len(messages) == 1
    assert messages[0]["content"] == "F007 先不做支付，改成做积分系统"
```

- [ ] **步骤 2：运行测试验证通过**

运行：`uv run pytest tests/test_dashboard_e2e.py -v`
预期：全部 PASS

- [ ] **步骤 3：Commit**

```bash
git add tests/test_dashboard_e2e.py
git commit -m "test: add end-to-end integration tests for dashboard API and WebSocket"
```

---

### 任务 12：最终验证

- [ ] **步骤 1：运行全部测试**

运行：`uv run pytest tests/ -v`
预期：全部 PASS，覆盖率 ≥ 80%

- [ ] **步骤 2：验证导入**

运行：`uv run python -c "from dashboard import *; from dashboard.integration import init_dashboard; print('OK')"`
预期：打印 "OK"

- [ ] **步骤 3：Commit**

```bash
git commit -am "chore: final verification and cleanup for dashboard implementation"
```

---

## 验证计划

1. `uv run pytest tests/ -v` → 全部 PASS
2. `uv run pytest --cov=dashboard --cov-report=term-missing` → ≥ 80% 覆盖率
3. `cd dashboard-web && npm run build` → 构建成功
4. `cd dashboard-web && npm run dev` → 启动成功，http://localhost:3568 可见看板
5. FastAPI 后端启动后，WebSocket 连接可用，REST API 可正常调用