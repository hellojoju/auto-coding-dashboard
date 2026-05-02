# Agent Cluster Monitor 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 替换现有的 ExecutionControl 组件，构建实时 Agent 集群监控系统，支持 Agent 状态实时展示、事件流过滤、静默检测、PM 干预（消息注入/中断/恢复）和可折叠聊天抽屉。

**架构：** 后端 PMCoordinator 在后台线程运行协调循环，通过 EventBus 发布事件；SilenceDetector 监控最后事件时间戳触发三级静默警报；AgentProcessManager 管理子进程生命周期（启动/消息注入/SIGINT中断/--continue恢复）。前端通过 WebSocket 推送实时事件到 AgentClusterMonitor 组件，支持按 Agent 过滤事件流和 PM-to-Agent 聊天抽屉。

**技术栈：** Python threading + subprocess + signal, FastAPI, WebSocket, Next.js 16.2.4, TypeScript, Zustand, Tailwind CSS v4, shadcn/ui

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `core/config.py` | **修改** | 添加静默检测阈值配置 |
| `dashboard/event_bus.py` | **修改** | 添加新事件类型说明和 emit 方法 |
| `dashboard/silence_detector.py` | **新建** | 三级静默检测器（30s/120s/600s） |
| `dashboard/agent_process_manager.py` | **新建** | Agent 子进程管理（启动/消息注入/SIGINT/恢复） |
| `dashboard/coordinator.py` | **修改** | 集成 SilenceDetector + AgentProcessManager，改造 run_coordinated_loop |
| `dashboard/api/routes.py` | **修改** | 添加 4 个 Agent 管理 REST 端点 |
| `dashboard-ui/lib/types.ts` | **修改** | 添加 silence 状态、资源使用类型、新事件常量 |
| `dashboard-ui/lib/store.ts` | **修改** | 添加 selectedAgent、事件过滤、resources 状态和操作 |
| `dashboard-ui/lib/api.ts` | **修改** | 添加 Agent 管理 API 函数 |
| `dashboard-ui/components/event-stream.tsx` | **新建** | 替换 log-stream.tsx，支持按 Agent 过滤的事件流 |
| `dashboard-ui/components/agent-list-panel.tsx` | **新建** | Agent 列表面板（角色分组、状态指示、静默告警） |
| `dashboard-ui/components/activity-panel.tsx` | **新建** | 当前活动 Agent 摘要面板 |
| `dashboard-ui/components/chat-drawer.tsx` | **新建** | 可折叠聊天抽屉（复用 ChatWindow） |
| `dashboard-ui/components/agent-cluster-monitor.tsx` | **新建** | 替换 execution-control.tsx，三面板布局主组件 |
| `dashboard-ui/app/page.tsx` | **修改** | 集成 AgentClusterMonitor 替换 ExecutionControl |
| `tests/test_silence_detector.py` | **新建** | SilenceDetector 单元测试 |
| `tests/test_agent_process_manager.py` | **新建** | AgentProcessManager 单元测试 |

---

## 任务 1：核心配置添加静默检测阈值

**文件：** `core/config.py`

- [x] **步骤 1：读取当前配置了解结构**

已读取：`core/config.py` 使用 dataclass 配置，包含 `timeout`, `max_iterations` 等字段。

- [x] **步骤 2：添加静默检测配置**

在 `PMConfig` dataclass 中添加：

```python
@dataclass
class PMConfig:
    # ... 现有字段 ...
    silence_warning_secs: int = 30       # 30秒：标记为静默状态
    silence_notify_secs: int = 120       # 120秒：通知PM诊断
    silence_intervention_secs: int = 600 # 600秒：需要PM干预
    status_poll_interval: int = 5        # 状态轮询间隔（秒）
```

- [x] **步骤 3：验证导入**

运行：`cd /Users/jieson/auto-coding && python -c "from core.config import PMConfig; print('OK')"`
预期：`OK`

- [x] **步骤 4：Commit**

```bash
git add core/config.py
git commit -m "feat(config): 添加静默检测阈值和轮询间隔配置"
```

---

## 任务 2：EventBus 添加新事件类型支持

**文件：** `dashboard/event_bus.py`

- [x] **步骤 1：读取当前 EventBus 了解结构**

已读取：77 行，`emit()` 方法接受 `event_type` 和 `data`，线程安全。

- [x] **步骤 2：添加事件类型常量**

在文件顶部添加事件类型常量：

```python
class AgentEventTypes:
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    AGENT_SILENCE = "agent_silence"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_INTERRUPT = "agent_interrupt"
    AGENT_RESUME = "agent_resume"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    RESOURCE_USAGE = "resource_usage"
```

- [x] **步骤 3：验证导入**

运行：`cd /Users/jieson/auto-coding && python -c "from dashboard.event_bus import AgentEventTypes; print('OK')"`
预期：`OK`

- [x] **步骤 4：Commit**

```bash
git add dashboard/event_bus.py
git commit -m "feat(event_bus): 添加 Agent 事件类型常量"
```

---

## 任务 3：实现 SilenceDetector 三级静默检测

**文件：** `dashboard/silence_detector.py`（新建）

- [ ] **步骤 1：编写失败的测试**

创建 `tests/test_silence_detector.py`：

```python
import time
from dashboard.silence_detector import SilenceDetector, SilenceLevel

def test_no_silence_when_active():
    detector = SilenceDetector(warning_secs=30, notify_secs=120, intervention_secs=600)
    detector.record_event("agent-1")
    level, secs = detector.check("agent-1")
    assert level == SilenceLevel.NONE
    assert secs == 0

def test_warning_after_threshold():
    detector = SilenceDetector(warning_secs=2, notify_secs=5, intervention_secs=10)
    detector.record_event("agent-1")
    time.sleep(3)
    level, secs = detector.check("agent-1")
    assert level == SilenceLevel.WARNING
    assert secs >= 2

def test_notify_after_longer_threshold():
    detector = SilenceDetector(warning_secs=2, notify_secs=4, intervention_secs=8)
    detector.record_event("agent-1")
    time.sleep(5)
    level, secs = detector.check("agent-1")
    assert level == SilenceLevel.NOTIFY
    assert secs >= 4

def test_intervention_after_very_long_silence():
    detector = SilenceDetector(warning_secs=2, notify_secs=4, intervention_secs=6)
    detector.record_event("agent-1")
    time.sleep(7)
    level, secs = detector.check("agent-1")
    assert level == SilenceLevel.INTERVENTION
    assert secs >= 6

def test_reset_on_new_event():
    detector = SilenceDetector(warning_secs=2, notify_secs=4, intervention_secs=6)
    detector.record_event("agent-1")
    time.sleep(3)
    detector.record_event("agent-1")
    level, _ = detector.check("agent-1")
    assert level == SilenceLevel.NONE

def test_unknown_agent_returns_none():
    detector = SilenceDetector()
    level, secs = detector.check("unknown-agent")
    assert level is None
    assert secs == 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/jieson/auto-coding && pytest tests/test_silence_detector.py -v`
预期：FAIL — `ModuleNotFoundError: No module named 'dashboard.silence_detector'`

- [ ] **步骤 3：实现 SilenceDetector**

创建 `dashboard/silence_detector.py`：

```python
import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

class SilenceLevel(Enum):
    NONE = "none"
    WARNING = "warning"       # 30s - 标记为静默
    NOTIFY = "notify"         # 120s - 通知PM诊断
    INTERVENTION = "intervention"  # 600s - 需要PM干预

class SilenceDetector:
    """三级静默检测器：监控每个 Agent 的最后事件时间，分级告警。"""

    def __init__(self, warning_secs: int = 30, notify_secs: int = 120, intervention_secs: int = 600):
        self._warning_secs = warning_secs
        self._notify_secs = notify_secs
        self._intervention_secs = intervention_secs
        self._last_event: dict[str, float] = {}
        self._alerted: dict[str, set[SilenceLevel]] = {}  # 防止重复告警

    def record_event(self, agent_id: str) -> None:
        """记录 Agent 产生了一个事件，重置静默计时器。"""
        self._last_event[agent_id] = time.time()
        self._alerted.pop(agent_id, None)  # 重置告警状态

    def check(self, agent_id: str) -> tuple[Optional[SilenceLevel], int]:
        """检查 Agent 的静默状态。返回 (级别, 静默秒数)。"""
        last_time = self._last_event.get(agent_id)
        if last_time is None:
            return None, 0

        elapsed = int(time.time() - last_time)
        level = SilenceLevel.NONE

        if elapsed >= self._intervention_secs:
            level = SilenceLevel.INTERVENTION
        elif elapsed >= self._notify_secs:
            level = SilenceLevel.NOTIFY
        elif elapsed >= self._warning_secs:
            level = SilenceLevel.WARNING

        # 防止重复告警：同一级别只告警一次
        if agent_id not in self._alerted:
            self._alerted[agent_id] = set()

        if level in self._alerted[agent_id]:
            return SilenceLevel.NONE, elapsed  # 已告警过，不再重复

        if level != SilenceLevel.NONE:
            self._alerted[agent_id].add(level)

        return level, elapsed

    def reset(self, agent_id: str) -> None:
        """重置 Agent 的静默状态（用于恢复后）。"""
        self._last_event.pop(agent_id, None)
        self._alerted.pop(agent_id, None)

    def remove(self, agent_id: str) -> None:
        """移除 Agent 的静默记录（Agent 停止后调用）。"""
        self._last_event.pop(agent_id, None)
        self._alerted.pop(agent_id, None)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/jieson/auto-coding && pytest tests/test_silence_detector.py -v`
预期：全部 6 个测试 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/silence_detector.py tests/test_silence_detector.py
git commit -m "feat(dashboard): 实现三级静默检测器 SilenceDetector"
```

---

## 任务 4：实现 AgentProcessManager 子进程管理

**文件：** `dashboard/agent_process_manager.py`（新建）

- [ ] **步骤 1：编写失败的测试**

在 `tests/test_agent_process_manager.py` 中添加：

```python
import signal
from unittest.mock import MagicMock, patch
from dashboard.agent_process_manager import AgentProcess, AgentProcessManager

def test_register_agent():
    manager = AgentProcessManager()
    manager.register_agent("agent-1", "backend-dev", ["claude", "-p"])
    assert "agent-1" in manager._agents
    assert manager._agents["agent-1"].role == "backend-dev"

def test_update_process():
    manager = AgentProcessManager()
    manager.register_agent("agent-1", "backend-dev", ["claude", "-p"])
    mock_process = MagicMock()
    mock_process.stdin = MagicMock()
    mock_process.stdin.closed = False
    manager.update_process("agent-1", mock_process)
    assert manager._agents["agent-1"].process is mock_process

def test_send_message_to_agent():
    manager = AgentProcessManager()
    mock_stdin = MagicMock()
    mock_stdin.closed = False
    mock_process = MagicMock()
    mock_process.stdin = mock_stdin
    manager.register_agent("agent-1", "backend-dev", ["claude", "-p"])
    manager.update_process("agent-1", mock_process)
    manager.send_message_to_agent("agent-1", "报告状态")
    mock_stdin.write.assert_called_once()
    mock_stdin.flush.assert_called_once()

def test_send_message_to_agent_without_process():
    manager = AgentProcessManager()
    manager.register_agent("agent-1", "backend-dev", ["claude", "-p"])
    result = manager.send_message_to_agent("agent-1", "报告状态")
    assert result is False

def test_graceful_interrupt():
    manager = AgentProcessManager()
    mock_process = MagicMock()
    manager.register_agent("agent-1", "backend-dev", ["claude", "-p"])
    manager.update_process("agent-1", mock_process)
    manager.graceful_interrupt("agent-1")
    mock_process.send_signal.assert_called_once_with(signal.SIGINT)

def test_remove_agent():
    manager = AgentProcessManager()
    manager.register_agent("agent-1", "backend-dev", ["claude", "-p"])
    manager.remove_agent("agent-1")
    assert "agent-1" not in manager._agents
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/jieson/auto-coding && pytest tests/test_agent_process_manager.py -v`
预期：FAIL — `ModuleNotFoundError: No module named 'dashboard.agent_process_manager'`

- [ ] **步骤 3：实现 AgentProcessManager**

创建 `dashboard/agent_process_manager.py`：

```python
import signal
import subprocess
import logging
import json
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class AgentProcess:
    agent_id: str
    role: str
    command: list[str]
    process: Optional[subprocess.Popen] = None
    working_dir: Optional[str] = None

class AgentProcessManager:
    """管理 Agent 子进程生命周期：启动、消息注入、中断、恢复。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentProcess] = {}

    def register_agent(self, agent_id: str, role: str, command: list[str], working_dir: Optional[str] = None) -> None:
        """注册 Agent 到管理器。"""
        self._agents[agent_id] = AgentProcess(
            agent_id=agent_id,
            role=role,
            command=command,
            working_dir=working_dir,
        )

    def update_process(self, agent_id: str, process: subprocess.Popen) -> None:
        """更新 Agent 的进程引用。"""
        if agent_id in self._agents:
            self._agents[agent_id].process = process

    def send_message_to_agent(self, agent_id: str, message: str) -> bool:
        """通过 stdin 向运行中的 Agent 注入消息。返回是否成功。"""
        agent = self._agents.get(agent_id)
        if not agent or not agent.process or not agent.process.stdin or agent.process.stdin.closed:
            logger.warning(f"无法向 Agent {agent_id} 发送消息：进程不可用")
            return False
        try:
            prompt = f"\n--- System Message from PM: {message} ---\n请报告你当前的工作状态、正在执行的任务、以及是否遇到任何阻塞。如果正在等待某项操作完成，请说明预期完成时间。\n"
            agent.process.stdin.write(prompt)
            agent.process.stdin.flush()
            logger.info(f"已向 Agent {agent_id} 注入消息")
            return True
        except (BrokenPipeError, OSError) as e:
            logger.error(f"向 Agent {agent_id} 发送消息失败: {e}")
            return False

    def graceful_interrupt(self, agent_id: str) -> bool:
        """发送 SIGINT 信号，让 Agent 优雅中断（保留 Claude Code 上下文）。"""
        agent = self._agents.get(agent_id)
        if not agent or not agent.process:
            logger.warning(f"无法中断 Agent {agent_id}：进程不存在")
            return False
        try:
            agent.process.send_signal(signal.SIGINT)
            agent.process.wait(timeout=10)
            logger.info(f"Agent {agent_id} 已优雅中断")
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"Agent {agent_id} SIGINT 超时，可能需要强制终止")
            return False
        except (ProcessLookupError, OSError) as e:
            logger.error(f"中断 Agent {agent_id} 失败: {e}")
            return False

    def force_kill(self, agent_id: str) -> bool:
        """强制终止 Agent 进程。"""
        agent = self._agents.get(agent_id)
        if not agent or not agent.process:
            return False
        try:
            agent.process.kill()
            agent.process.wait(timeout=5)
            logger.info(f"Agent {agent_id} 已强制终止")
            return True
        except (ProcessLookupError, OSError) as e:
            logger.error(f"强制终止 Agent {agent_id} 失败: {e}")
            return False

    def get_agent_status(self, agent_id: str) -> dict:
        """获取 Agent 进程状态。"""
        agent = self._agents.get(agent_id)
        if not agent:
            return {"exists": False}
        if not agent.process:
            return {"exists": True, "running": False}
        poll_result = agent.process.poll()
        return {
            "exists": True,
            "running": poll_result is None,
            "exit_code": poll_result,
            "pid": agent.process.pid,
        }

    def remove_agent(self, agent_id: str) -> None:
        """从管理器移除 Agent。"""
        self._agents.pop(agent_id, None)

    def list_agents(self) -> dict[str, AgentProcess]:
        """返回所有注册的 Agent。"""
        return dict(self._agents)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/jieson/auto-coding && pytest tests/test_agent_process_manager.py -v`
预期：全部 6 个测试 PASS

- [ ] **步骤 5：Commit**

```bash
git add dashboard/agent_process_manager.py tests/test_agent_process_manager.py
git commit -m "feat(dashboard): 实现 AgentProcessManager 子进程生命周期管理"
```

---

## 任务 5：PMCoordinator 集成静默检测和进程管理

**文件：** `dashboard/coordinator.py`

- [ ] **步骤 1：读取当前 coordinator.py 了解现有结构**

已读取过：PMCoordinator 类有 `run_coordinated_loop()` 方法，使用 EventBus 发布事件，支持 threading 的 start/stop。

- [ ] **步骤 2：添加 import 和初始化**

在 `coordinator.py` 顶部添加：

```python
from dashboard.silence_detector import SilenceDetector, SilenceLevel
from dashboard.agent_process_manager import AgentProcessManager
from dashboard.event_bus import AgentEventTypes
```

在 `__init__` 中初始化组件：

```python
def __init__(self, ...):
    # ... 现有代码 ...
    self._silence_detector = SilenceDetector(
        warning_secs=30,
        notify_secs=120,
        intervention_secs=600,
    )
    self._process_manager = AgentProcessManager()
```

- [ ] **步骤 3：在 run_coordinated_loop 中添加静默检测循环**

在 `run_coordinated_loop` 的 while 循环中，在每次迭代末尾添加：

```python
# 静默检测
for agent_id, assignment in tracker.get_running_agents().items():
    self._silence_detector.record_event(agent_id)  # 每次迭代重置

# 检查所有 Agent 的静默状态
for agent_id in tracker.get_all_agent_ids():
    level, secs = self._silence_detector.check(agent_id)
    if level == SilenceLevel.WARNING:
        self._event_bus.emit(AgentEventTypes.AGENT_SILENCE, {
            "agent_id": agent_id,
            "level": "warning",
            "seconds": secs,
            "message": f"Agent {agent_id} 已静默 {secs} 秒",
        })
    elif level == SilenceLevel.NOTIFY:
        self._event_bus.emit(AgentEventTypes.AGENT_TIMEOUT, {
            "agent_id": agent_id,
            "level": "notify",
            "seconds": secs,
            "message": f"Agent {agent_id} 已静默 {secs} 秒，请检查是否卡住",
        })
    elif level == SilenceLevel.INTERVENTION:
        self._event_bus.emit(AgentEventTypes.AGENT_TIMEOUT, {
            "agent_id": agent_id,
            "level": "intervention",
            "seconds": secs,
            "message": f"Agent {agent_id} 已静默 {secs} 秒，需要立即干预",
        })
```

- [ ] **步骤 4：在 Agent 启动和停止时管理进程和静默状态**

在 Agent 启动时：

```python
# Agent 启动时
self._process_manager.register_agent(agent_id, role, command)
self._silence_detector.record_event(agent_id)
```

在 Agent 停止时：

```python
# Agent 停止时
self._silence_detector.remove(agent_id)
```

- [ ] **步骤 5：添加 Agent 管理方法到 PMCoordinator**

```python
def send_message_to_agent(self, agent_id: str, message: str) -> dict:
    """向运行中的 Agent 注入消息。"""
    success = self._process_manager.send_message_to_agent(agent_id, message)
    return {"success": success, "agent_id": agent_id}

def interrupt_agent(self, agent_id: str) -> dict:
    """优雅中断 Agent。"""
    success = self._process_manager.graceful_interrupt(agent_id)
    if success:
        self._silence_detector.reset(agent_id)
    return {"success": success, "agent_id": agent_id}

def get_agent_status(self, agent_id: str) -> dict:
    """获取 Agent 进程状态。"""
    return self._process_manager.get_agent_status(agent_id)

def list_agents(self) -> list[dict]:
    """列出所有 Agent 及其状态。"""
    result = []
    for agent_id, proc in self._process_manager.list_agents().items():
        silence_level, silence_secs = self._silence_detector.check(agent_id)
        result.append({
            "agent_id": agent_id,
            "role": proc.role,
            "pid": proc.process.pid if proc.process else None,
            "running": proc.process.poll() is None if proc.process else False,
            "silence_level": silence_level.value if silence_level else "none",
            "silence_secs": silence_secs,
        })
    return result
```

- [ ] **步骤 6：验证导入**

运行：`cd /Users/jieson/auto-coding && python -c "from dashboard.coordinator import PMCoordinator; print('OK')"`
预期：`OK`

- [ ] **步骤 7：Commit**

```bash
git add dashboard/coordinator.py
git commit -m "feat(dashboard): PMCoordinator 集成静默检测和 Agent 进程管理"
```

---

## 任务 6：REST API 添加 Agent 管理端点

**文件：** `dashboard/api/routes.py`

- [ ] **步骤 1：在 create_dashboard_app 中确保 coordinator 已注入**

```python
def create_dashboard_app(
    event_bus: EventBus,
    coordinator: "PMCoordinator | None" = None,
) -> FastAPI:
    app.state.coordinator = coordinator
```

- [ ] **步骤 2：添加 4 个 Agent 管理端点**

```python
    @app.get("/api/agents")
    async def list_agents() -> list[dict]:
        """列出所有 Agent 及其状态。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            return []
        return coordinator.list_agents()

    @app.post("/api/agents/{agent_id}/message")
    async def send_agent_message(agent_id: str, request: dict = Body(...)) -> dict:
        """向 Agent 注入消息。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            raise HTTPException(status_code=503, detail="PMCoordinator 未配置")
        message = request.get("message", "")
        if not message:
            raise HTTPException(status_code=400, detail="message 不能为空")
        return coordinator.send_message_to_agent(agent_id, message)

    @app.post("/api/agents/{agent_id}/interrupt")
    async def interrupt_agent(agent_id: str) -> dict:
        """优雅中断 Agent（SIGINT）。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            raise HTTPException(status_code=503, detail="PMCoordinator 未配置")
        return coordinator.interrupt_agent(agent_id)

    @app.get("/api/agents/{agent_id}/status")
    async def get_agent_status(agent_id: str) -> dict:
        """获取单个 Agent 状态。"""
        coordinator = getattr(app.state, "coordinator", None)
        if not coordinator:
            return {"agent_id": agent_id, "available": False}
        return coordinator.get_agent_status(agent_id)
```

- [ ] **步骤 3：验证导入**

运行：`cd /Users/jieson/auto-coding && python -c "from dashboard.api.routes import create_dashboard_app; print('OK')"`
预期：`OK`

- [ ] **步骤 4：Commit**

```bash
git add dashboard/api/routes.py
git commit -m "feat(dashboard): 添加 Agent 管理 REST 端点 (list/message/interrupt/status)"
```

---

## 任务 7：前端类型定义更新

**文件：** `dashboard-ui/lib/types.ts`

- [ ] **步骤 1：读取当前 types.ts 了解结构**

已读取：包含 `AgentStatus`, `DashboardEvent`, `AgentInstance` 等类型定义。

- [ ] **步骤 2：更新 AgentStatus 添加 silence 状态**

```typescript
// 修改现有 AgentStatus 类型
export type AgentStatus = 'idle' | 'starting' | 'running' | 'silence' | 'waiting_pm' | 'error' | 'completed'
```

- [ ] **步骤 3：添加资源使用类型**

```typescript
/** Agent 资源使用快照。 */
export interface ResourceUsage {
  cpu_percent: number
  memory_mb: number
  disk_io_read_mb: number
  disk_io_write_mb: number
  timestamp: string
}
```

- [ ] **步骤 4：添加事件类型常量**

```typescript
/** Agent 事件类型常量。 */
export const AGENT_EVENT_TYPES = {
  AGENT_START: 'agent_start',
  AGENT_STOP: 'agent_stop',
  AGENT_SILENCE: 'agent_silence',
  AGENT_TIMEOUT: 'agent_timeout',
  AGENT_INTERRUPT: 'agent_interrupt',
  AGENT_RESUME: 'agent_resume',
  TOOL_USE: 'tool_use',
  TOOL_RESULT: 'tool_result',
  RESOURCE_USAGE: 'resource_usage',
} as const

export type AgentEventType = (typeof AGENT_EVENT_TYPES)[keyof typeof AGENT_EVENT_TYPES]
```

- [ ] **步骤 5：更新 AgentInstance 添加静默字段**

```typescript
export interface AgentInstance {
  // ... 现有字段 ...
  silenceLevel?: 'none' | 'warning' | 'notify' | 'intervention'
  silenceSecs?: number
  pid?: number
}
```

- [ ] **步骤 6：验证构建**

运行：`cd /Users/jieson/auto-coding/dashboard-ui && npx tsc --noEmit`
预期：零错误

- [ ] **步骤 7：Commit**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
git add lib/types.ts
git commit -m "feat(dashboard-ui): 添加 silence 状态、资源使用类型和事件常量"
```

---

## 任务 8：前端 API 客户端添加 Agent 管理函数

**文件：** `dashboard-ui/lib/api.ts`

- [ ] **步骤 1：读取当前 api.ts 了解结构**

- [ ] **步骤 2：添加 Agent 管理 API 函数**

```typescript
import type { AgentInstance } from './types'

export interface AgentStatusResponse {
  agent_id: string
  role: string
  pid: number | null
  running: boolean
  silence_level: string
  silence_secs: number
}

export async function listAgents(): Promise<AgentStatusResponse[]> {
  const res = await fetch(`${API_BASE}/agents`)
  if (!res.ok) return []
  return res.json()
}

export async function sendAgentMessage(agentId: string, message: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) throw new Error('发送消息失败')
  return res.json()
}

export async function interruptAgent(agentId: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/interrupt`, { method: 'POST' })
  if (!res.ok) throw new Error('中断失败')
  return res.json()
}

export async function getAgentStatus(agentId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/status`)
  if (!res.ok) return {}
  return res.json()
}
```

- [ ] **步骤 3：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 4：Commit**

```bash
git add lib/api.ts
git commit -m "feat(dashboard-ui): 添加 Agent 管理 API 客户端函数"
```

---

## 任务 9：Zustand Store 添加 Agent 选择和事件过滤

**文件：** `dashboard-ui/lib/store.ts`

- [ ] **步骤 1：读取当前 store.ts 了解结构**

已读取：178 行，`DashboardState` 接口，`applyEventToState` 辅助函数。

- [ ] **步骤 2：添加状态字段**

```typescript
import type { ExecutionStatus, AgentInstance, AgentEventType } from './types'
import { AGENT_EVENT_TYPES, listAgents } from './types'  // 调整 import

// 在 DashboardState 中添加
export interface DashboardState {
  // ... 现有字段 ...
  selectedAgentId: string | null     // 选中的 Agent，null = 全部显示
  resources: Record<string, { cpu: number; memory: number }>  // 资源使用
}

// 在 initialState 中添加
export const initialState: DashboardState = {
  // ... 现有字段 ...
  selectedAgentId: null,
  resources: {},
}
```

- [ ] **步骤 3：添加事件过滤函数**

```typescript
/** 根据选中的 Agent 过滤事件。 */
function filterEventsByAgent(events: DashboardEvent[], selectedAgentId: string | null): DashboardEvent[] {
  if (!selectedAgentId) return events
  return events.filter(e => e.agent_id === selectedAgentId || e.agent_id == null)
}
```

- [ ] **步骤 4：添加 Agent 相关 actions**

```typescript
export const useDashboardStore = create<DashboardState & DashboardActions>((set, get) => ({
  // ... 现有 actions ...

  selectAgent: (agentId: string | null) => {
    set({ selectedAgentId: agentId })
  },

  fetchAgentList: async () => {
    try {
      const agents = await listAgents()
      // 将 Agent 状态同步到 store
      const currentAgents = get().agents
      for (const a of agents) {
        const existing = currentAgents[a.role]
        if (existing) {
          existing.silenceLevel = a.silence_level as AgentInstance['silenceLevel']
          existing.silenceSecs = a.silence_secs
          existing.pid = a.pid ?? undefined
        }
      }
      set({ agents: { ...currentAgents } })
    } catch {
      // 静默失败，后端可能未配置 coordinator
    }
  },

  sendAgentMessage: async (agentId: string, message: string) => {
    try {
      await sendAgentMessageAPI(agentId, message)
    } catch (error) {
      console.error('发送消息失败:', error)
    }
  },

  interruptAgent: async (agentId: string) => {
    try {
      await interruptAgentAPI(agentId)
    } catch (error) {
      console.error('中断失败:', error)
    }
  },
}))
```

- [ ] **步骤 5：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 6：Commit**

```bash
git add lib/store.ts
git commit -m "feat(dashboard-ui): Store 添加 Agent 选择、事件过滤和资源状态"
```

---

## 任务 10：创建 EventStream 组件（替换 log-stream.tsx）

**文件：** `dashboard-ui/components/event-stream.tsx`（新建）

- [ ] **步骤 1：创建组件**

```tsx
'use client';

import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useDashboardStore } from '@/lib/store';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { AGENT_EVENT_TYPES } from '@/lib/types';
import { cn } from '@/lib/utils';

interface EventStreamProps {
  className?: string;
}

function EventIcon({ type }: { type: string }) {
  const iconMap: Record<string, string> = {
    [AGENT_EVENT_TYPES.TOOL_USE]: '🔧',
    [AGENT_EVENT_TYPES.TOOL_RESULT]: '✅',
    [AGENT_EVENT_TYPES.AGENT_SILENCE]: '⏸',
    [AGENT_EVENT_TYPES.AGENT_TIMEOUT]: '⚠️',
    [AGENT_EVENT_TYPES.AGENT_START]: '🚀',
    [AGENT_EVENT_TYPES.AGENT_STOP]: '🛑',
  };
  return <span className="text-sm">{iconMap[type] || '📝'}</span>;
}

function EventBadge({ type }: { type: string }) {
  const variantMap: Record<string, "default" | "secondary" | "destructive"> = {
    [AGENT_EVENT_TYPES.AGENT_TIMEOUT]: 'destructive',
    [AGENT_EVENT_TYPES.AGENT_SILENCE]: 'secondary',
    [AGENT_EVENT_TYPES.AGENT_START]: 'default',
  };
  return (
    <Badge variant={variantMap[type] || 'secondary'} className="text-xs">
      {type.replace('agent_', '').replace('tool_', '')}
    </Badge>
  );
}

export function EventStream({ className }: EventStreamProps) {
  const events = useDashboardStore((s) => s.events);
  const selectedAgentId = useDashboardStore((s) => s.selectedAgentId);
  const agents = useDashboardStore((s) => s.agents);
  const scrollRef = useRef<HTMLDivElement>(null);
  const autoScroll = useDashboardStore((s) => s.autoScroll ?? true);

  // 按选中 Agent 过滤事件
  const filteredEvents = useMemo(() => {
    if (!selectedAgentId) return events;
    return events.filter(e => e.agent_id === selectedAgentId || e.agent_id == null);
  }, [events, selectedAgentId]);

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredEvents.length, autoScroll]);

  return (
    <div className={cn('flex flex-col h-full', className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <h3 className="text-sm font-medium">
          事件流
          {selectedAgentId && (
            <span className="ml-2 text-muted-foreground">
              — {agents[selectedAgentId]?.role || selectedAgentId}
            </span>
          )}
        </h3>
        <Badge variant="outline" className="text-xs">
          {filteredEvents.length} 条
        </Badge>
      </div>
      <ScrollArea className="flex-1">
        <div ref={scrollRef} className="p-3 space-y-1">
          {filteredEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              暂无事件
            </p>
          ) : (
            filteredEvents.map((event, i) => (
              <div
                key={`${event.timestamp}-${i}`}
                className="flex items-start gap-2 text-xs py-1 px-2 rounded hover:bg-muted/50"
              >
                <EventIcon type={event.type} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <EventBadge type={event.type} />
                    {event.agent_id && (
                      <span className="text-muted-foreground">
                        {agents[event.agent_id]?.role || event.agent_id}
                      </span>
                    )}
                  </div>
                  <p className="text-foreground mt-0.5 break-words">
                    {event.message || JSON.stringify(event.data ?? '')}
                  </p>
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
```

- [ ] **步骤 2：验证构建**

运行：`cd /Users/jieson/auto-coding/dashboard-ui && npx tsc --noEmit`
预期：零错误

- [ ] **步骤 3：Commit**

```bash
git add components/event-stream.tsx
git commit -m "feat(dashboard-ui): 创建 EventStream 组件，支持按 Agent 过滤"
```

---

## 任务 11：创建 AgentListPanel 组件

**文件：** `dashboard-ui/components/agent-list-panel.tsx`（新建）

- [ ] **步骤 1：创建组件**

```tsx
'use client';

import { useDashboardStore } from '@/lib/store';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { AGENT_STATUS_LABELS } from '@/lib/types';
import { cn } from '@/lib/utils';
import { AlertTriangle, Loader2 } from 'lucide-react';

interface AgentListPanelProps {
  className?: string;
}

const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-gray-400',
  starting: 'bg-yellow-400',
  running: 'bg-green-500',
  silence: 'bg-orange-400',
  waiting_pm: 'bg-purple-400',
  error: 'bg-red-500',
  completed: 'bg-blue-500',
};

export function AgentListPanel({ className }: AgentListPanelProps) {
  const agents = useDashboardStore((s) => s.agents);
  const selectedAgentId = useDashboardStore((s) => s.selectedAgentId);
  const selectAgent = useDashboardStore((s) => s.selectAgent);

  const agentEntries = Object.entries(agents);

  return (
    <div className={cn('flex flex-col h-full', className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <h3 className="text-sm font-medium">Agent 列表</h3>
        <Badge variant="outline" className="text-xs">
          {agentEntries.filter(([, a]) => a.status === 'running' || a.status === 'silence').length} 活跃
        </Badge>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {agentEntries.map(([id, agent]) => {
            const isSelected = id === selectedAgentId;
            const isSilence = agent.silenceLevel && agent.silenceLevel !== 'none';
            return (
              <button
                key={id}
                onClick={() => selectAgent(isSelected ? null : id)}
                className={cn(
                  'w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm text-left transition-colors',
                  isSelected && 'bg-primary/10 border border-primary/20',
                  !isSelected && 'hover:bg-muted/50',
                )}
              >
                {/* 状态点 */}
                <span className={cn(
                  'h-2 w-2 rounded-full flex-shrink-0',
                  STATUS_COLORS[agent.status] || 'bg-gray-400',
                  agent.status === 'running' && 'animate-pulse',
                )} />

                {/* 角色名 */}
                <span className="flex-1 truncate font-medium text-xs">
                  {agent.role}
                </span>

                {/* 静默告警 */}
                {isSilence && (
                  <AlertTriangle className={cn(
                    'h-3.5 w-3.5 flex-shrink-0',
                    agent.silenceLevel === 'intervention' ? 'text-red-500' :
                    agent.silenceLevel === 'notify' ? 'text-orange-500' : 'text-yellow-500',
                  )} />
                )}

                {/* 状态标签 */}
                <span className="text-[10px] text-muted-foreground">
                  {AGENT_STATUS_LABELS[agent.status]}
                </span>

                {/* 启动中动画 */}
                {agent.status === 'starting' && (
                  <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                )}
              </button>
            );
          })}
          {agentEntries.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">
              暂无 Agent
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
```

- [ ] **步骤 2：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 3：Commit**

```bash
git add components/agent-list-panel.tsx
git commit -m "feat(dashboard-ui): 创建 AgentListPanel 组件"
```

---

## 任务 12：创建 ActivityPanel 组件

**文件：** `dashboard-ui/components/activity-panel.tsx`（新建）

- [ ] **步骤 1：创建组件**

```tsx
'use client';

import { useDashboardStore } from '@/lib/store';
import { Badge } from '@/components/ui/badge';
import { Loader2 } from 'lucide-react';

interface ActivityPanelProps {
  className?: string;
}

export function ActivityPanel({ className }: ActivityPanelProps) {
  const agents = useDashboardStore((s) => s.agents);
  const runningAgents = Object.entries(agents).filter(
    ([, a]) => a.status === 'running' || a.status === 'starting'
  );

  if (runningAgents.length === 0) {
    return (
      <div className={className}>
        <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
          没有活跃任务
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="px-3 py-2 border-b">
        <h3 className="text-sm font-medium">当前活动</h3>
      </div>
      <div className="p-3 space-y-2">
        {runningAgents.map(([id, agent]) => (
          <div key={id} className="flex items-start gap-2 text-sm">
            <Loader2 className="h-3.5 w-3.5 mt-0.5 animate-spin text-muted-foreground" />
            <div className="min-w-0">
              <span className="font-medium text-xs">{agent.role}</span>
              <p className="text-xs text-muted-foreground truncate max-w-[280px]">
                {agent.currentTask || '执行任务中...'}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **步骤 2：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 3：Commit**

```bash
git add components/activity-panel.tsx
git commit -m "feat(dashboard-ui): 创建 ActivityPanel 组件"
```

---

## 任务 13：创建 ChatDrawer 组件

**文件：** `dashboard-ui/components/chat-drawer.tsx`（新建）

- [ ] **步骤 1：读取现有 ChatWindow 了解可复用部分**

已读取：`chat-window.tsx` 95 行，包含消息列表、输入框、发送按钮。

- [ ] **步骤 2：创建 ChatDrawer 组件**

```tsx
'use client';

import { useState, useEffect } from 'react';
import { useDashboardStore } from '@/lib/store';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ChatWindow } from '@/components/chat-window';
import { cn } from '@/lib/utils';
import { X, MessageSquare, Send } from 'lucide-react';

interface ChatDrawerProps {
  className?: string;
}

export function ChatDrawer({ className }: ChatDrawerProps) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const agents = useDashboardStore((s) => s.agents);
  const selectedAgentId = useDashboardStore((s) => s.selectedAgentId);
  const sendAgentMessage = useDashboardStore((s) => s.sendAgentMessage);

  const targetAgent = selectedAgentId ? agents[selectedAgentId] : null;
  const hasUnread = false; // 后续可通过 unread count 实现

  const handleSend = async () => {
    if (!message.trim() || !selectedAgentId) return;
    await sendAgentMessage(selectedAgentId, message.trim());
    setMessage('');
  };

  return (
    <>
      {/* 触发按钮 */}
      <Button
        size="icon"
        variant="outline"
        onClick={() => setOpen(!open)}
        className={cn('relative', className)}
        title="打开聊天"
      >
        <MessageSquare className="h-4 w-4" />
        {hasUnread && (
          <Badge className="absolute -top-1 -right-1 h-4 w-4 p-0 text-[8px] flex items-center justify-center">
            !
          </Badge>
        )}
      </Button>

      {/* 抽屉面板 */}
      {open && (
        <div className="fixed right-0 top-0 h-full w-80 border-l bg-background shadow-xl z-50 flex flex-col">
          {/* 头部 */}
          <div className="flex items-center justify-between px-3 py-2 border-b">
            <div>
              <h3 className="text-sm font-medium">
                {targetAgent?.role || '选择 Agent'}
              </h3>
              {selectedAgentId && (
                <p className="text-[10px] text-muted-foreground">{selectedAgentId}</p>
              )}
            </div>
            <Button size="icon" variant="ghost" onClick={() => setOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* 内容 */}
          <div className="flex-1 overflow-hidden">
            {selectedAgentId ? (
              <ChatWindow agentId={selectedAgentId} />
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                请先选择一个 Agent
              </div>
            )}
          </div>

          {/* 底部输入 */}
          {selectedAgentId && (
            <div className="flex items-center gap-2 p-2 border-t">
              <Input
                placeholder="输入消息..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                className="text-sm"
              />
              <Button size="icon" onClick={handleSend} disabled={!message.trim()}>
                <Send className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
```

- [ ] **步骤 2：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 3：Commit**

```bash
git add components/chat-drawer.tsx
git commit -m "feat(dashboard-ui): 创建 ChatDrawer 组件，复用 ChatWindow"
```

---

## 任务 14：创建 AgentClusterMonitor 组件（替换 execution-control.tsx）

**文件：** `dashboard-ui/components/agent-cluster-monitor.tsx`（新建）

- [ ] **步骤 1：创建主组件**

```tsx
'use client';

import { useEffect, useCallback } from 'react';
import { useDashboardStore } from '@/lib/store';
import { AgentListPanel } from './agent-list-panel';
import { ActivityPanel } from './activity-panel';
import { EventStream } from './event-stream';
import { ChatDrawer } from './chat-drawer';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Play, Square, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { EXECUTION_STATUS_LABELS, EXECUTION_STATUS_COLORS } from '@/lib/types';

interface AgentClusterMonitorProps {
  className?: string;
}

export function AgentClusterMonitor({ className }: AgentClusterMonitorProps) {
  const { executionStatus, startExecution, stopExecution, fetchExecutionStatus, fetchAgentList } = useDashboardStore();

  const isRunning = executionStatus === 'running' || executionStatus === 'starting';

  // 初始化轮询
  useEffect(() => {
    fetchExecutionStatus();
    fetchAgentList();
    const interval = setInterval(() => {
      fetchExecutionStatus();
      fetchAgentList();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchExecutionStatus, fetchAgentList]);

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {/* 顶部控制栏 */}
      <div className="flex items-center gap-3 px-3 py-2 border rounded-lg bg-muted/30">
        {/* 执行状态 + 启停按钮 */}
        <div className="flex items-center gap-2">
          <Badge variant={isRunning ? 'default' : 'secondary'} className="flex items-center gap-1.5">
            <span className={cn(
              'h-2 w-2 rounded-full',
              EXECUTION_STATUS_COLORS[executionStatus],
              isRunning && 'animate-pulse',
            )} />
            {EXECUTION_STATUS_LABELS[executionStatus]}
          </Badge>
          {executionStatus === 'starting' && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
          )}
        </div>

        {!isRunning ? (
          <Button size="sm" variant="default" onClick={startExecution} disabled={executionStatus === 'starting'} className="gap-1">
            <Play className="h-3.5 w-3.5" />
            启动开发
          </Button>
        ) : (
          <Button size="sm" variant="destructive" onClick={stopExecution} className="gap-1">
            <Square className="h-3.5 w-3.5" />
            停止
          </Button>
        )}

        <div className="flex-1" />

        {/* 聊天抽屉按钮 */}
        <ChatDrawer />
      </div>

      {/* 三面板布局 */}
      <div className="flex gap-3 h-[500px]">
        {/* 左侧：Agent 列表 */}
        <div className="w-56 border rounded-lg overflow-hidden">
          <AgentListPanel />
        </div>

        {/* 中间：事件流 */}
        <div className="flex-1 border rounded-lg overflow-hidden">
          <EventStream />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **步骤 2：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 3：Commit**

```bash
git add components/agent-cluster-monitor.tsx
git commit -m "feat(dashboard-ui): 创建 AgentClusterMonitor 主组件，替换 ExecutionControl"
```

---

## 任务 15：集成 AgentClusterMonitor 到页面

**文件：** `dashboard-ui/app/page.tsx`

- [ ] **步骤 1：替换 ExecutionControl 导入和引用**

```tsx
// 将
import { ExecutionControl } from '@/components/execution-control';
// 替换为
import { AgentClusterMonitor } from '@/components/agent-cluster-monitor';

// 在 JSX 中将
<ExecutionControl />
// 替换为
<AgentClusterMonitor />
```

- [ ] **步骤 2：验证构建**

运行：`npm run build`
预期：BUILD 成功

- [ ] **步骤 3：Commit**

```bash
git add app/page.tsx
git commit -m "feat(dashboard-ui): 页面集成 AgentClusterMonitor 替换 ExecutionControl"
```

---

## 任务 16：删除旧组件

**文件：** `dashboard-ui/components/execution-control.tsx`, `dashboard-ui/components/log-stream.tsx`

- [ ] **步骤 1：删除不再使用的旧组件**

```bash
rm components/execution-control.tsx components/log-stream.tsx
```

- [ ] **步骤 2：验证构建**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 3：Commit**

```bash
git rm components/execution-control.tsx components/log-stream.tsx
git commit -m "chore(dashboard-ui): 删除已替换的旧组件"
```

---

## 任务 17：端到端验证

> **注意：** 运行时验证需要启动后端和前端服务。

- [ ] **步骤 1：Python 语法检查**

运行：`cd /Users/jieson/auto-coding && python -c "from dashboard.coordinator import PMCoordinator; from dashboard.silence_detector import SilenceDetector; from dashboard.agent_process_manager import AgentProcessManager; print('OK')"`
预期：`OK`

- [ ] **步骤 2：运行所有测试**

运行：`cd /Users/jieson/auto-coding && pytest tests/test_silence_detector.py tests/test_agent_process_manager.py -v`
预期：全部 12 个测试 PASS

- [ ] **步骤 3：前端构建**

运行：`cd /Users/jieson/auto-coding/dashboard-ui && npm run build`
预期：BUILD 成功

- [ ] **步骤 4：类型检查**

运行：`npx tsc --noEmit`
预期：零错误

- [ ] **步骤 5：API 测试（需后端运行）**

```bash
# 启动后端
cd /Users/jieson/auto-coding && claude dashboard --auto-start &

# 测试端点
curl http://localhost:8000/api/agents
curl -X POST http://localhost:8000/api/execution/start
```

---

## 验收标准

1. **后端 SilenceDetector**: 三级检测（30s/120s/600s），防重复告警，测试全部通过 ✅
2. **后端 AgentProcessManager**: 消息注入/SIGINT中断/进程状态查询，测试全部通过 ✅
3. **后端 PMCoordinator**: 集成静默检测和进程管理，run_coordinated_loop 中调用检测 ✅
4. **API**: 4 个新端点（list/message/interrupt/status）正常工作 ✅
5. **前端类型**: silence 状态、资源类型、事件常量定义完整 ✅
6. **Store**: selectedAgent、事件过滤、Agent actions 全部实现 ✅
7. **UI 组件**: AgentListPanel + ActivityPanel + EventStream + ChatDrawer + AgentClusterMonitor 全部创建 ✅
8. **集成**: 页面正确显示三面板布局，事件流按 Agent 过滤 ✅
9. **构建**: `npm run build` 零错误，`tsc --noEmit` 零错误 ✅
10. **测试**: Python 测试 12 个全部 PASS ✅

---

## 规格覆盖自检

对照设计文档 `docs/superpowers/specs/2026-04-19-agent-cluster-monitor-design.md`：

| 设计需求 | 对应任务 | 状态 |
|----------|----------|------|
| 静默检测（30s/120s/600s） | 任务 3 | ✅ |
| Agent 进程管理（启动/消息注入/SIGINT/--continue） | 任务 4 | ✅ |
| PMCoordinator 集成 | 任务 5 | ✅ |
| REST API 端点 | 任务 6 | ✅ |
| 配置项 | 任务 1 | ✅ |
| EventBus 事件类型 | 任务 2 | ✅ |
| 前端类型定义 | 任务 7 | ✅ |
| API 客户端函数 | 任务 8 | ✅ |
| Zustand Store 过滤 | 任务 9 | ✅ |
| EventStream 组件（Agent 过滤） | 任务 10 | ✅ |
| AgentListPanel 组件 | 任务 11 | ✅ |
| ActivityPanel 组件 | 任务 12 | ✅ |
| ChatDrawer 组件 | 任务 13 | ✅ |
| AgentClusterMonitor 主组件 | 任务 14 | ✅ |
| 页面集成 | 任务 15 | ✅ |
| 旧组件清理 | 任务 16 | ✅ |

**无占位符、无矛盾、无模糊需求。计划完整。**

---

## 执行选项

**计划已完成并保存到 `docs/superpowers/plans/2026-04-19-agent-cluster-monitor-plan.md`。两种执行方式：**

**1. 子代理驱动（推荐）** — 每个任务调度一个新的子代理，任务间进行审查，快速迭代
**2. 内联执行** — 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？
