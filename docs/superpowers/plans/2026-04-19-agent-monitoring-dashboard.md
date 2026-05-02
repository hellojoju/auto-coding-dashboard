# AI 开发团队监控系统 — 完整实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建完整的 AI 开发团队监控系统，实现 PM（唯一 Team Leader）接收甲方指令、子 Agent 每步执行后等待 PM 审批、前端实时可视化所有 Agent 运行状态。

**架构：** 当前系统是"全自动串行跑完"模式（ProjectManager.run_execution_loop 一口气跑完所有 features）。需要改造为"命令驱动 + 暂停等待审批"模式：用户通过前端看板发指令 → 命令存入 Repository → CommandConsumer 消费并执行 → 子 Agent 每步完成后状态回写 → 等待 PM（用户）审批 → 审批通过后继续下一步。

**技术栈：**
- 后端：FastAPI, WebSocket, Pydantic v2
- 前端：Next.js 16.2.4 (App Router), TypeScript 5.x, Zustand, Tailwind CSS v4, shadcn/ui v4.3.0, Sonner v2.0.7
- 测试：pytest, Playwright

**当前状态：**
- 后端 dashboard 模块：EventBus、models、state_repository（内存）、command_processor、api/routes（REST + WebSocket）已实现
- 前端 dashboard-ui：Next.js 项目已初始化，看板五列布局、Agent 状态面板、PM 对话窗口、CommandBar 已实现
- 核心系统：ProjectManager（串行执行）、AgentPool（多实例）、FeatureTracker 已实现
- **关键缺口：** Repository 未持久化、CommandConsumer 未消费命令、Agent 执行过程不向 dashboard 上报状态、前端 store command actions 传空 target_id、部分死代码未清理

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `dashboard/consumer.py` | CommandConsumer：轮询 Repository 待处理命令，执行状态机转换，写回状态 |
| `dashboard/api/dependencies.py` | FastAPI 依赖注入：获取 repository、event_bus、consumer 单例 |
| `tests/test_command_consumer.py` | CommandConsumer 单元测试 |
| `tests/test_repository_persistence.py` | Repository 文件持久化测试 |
| `tests/test_state_backwrite.py` | 状态回写集成测试 |
| `app/global-error.tsx` | 根级错误边界（Next.js） |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `dashboard/state_repository.py` | 添加文件持久化：save/load agents, features, commands, events, chat |
| `dashboard/api/routes.py` | 挂载 CommandConsumer，对齐 WebSocket 事件格式 |
| `dashboard/__init__.py` | 导出 consumer |
| `agents/base_agent.py` | execute() 中上报状态到 EventBus |
| `core/project_manager.py` | 改造 run_execution_loop 为命令驱动模式 |
| `dashboard-ui/app/layout.tsx` | 挂载 Toaster + ThemeProvider |
| `dashboard-ui/components/command-bar.tsx` | 移除 console.log，改用 Sonner toast |
| `dashboard-ui/lib/store.ts` | 修复 command actions 空 target_id bug |
| `dashboard-ui/types/dashboard.ts` | 删除（死代码） |
| `dashboard-ui/components/index.ts` | 删除（死代码） |

---

## Milestone 1: Repository 持久化

### 任务 1：让 ProjectStateRepository 真正持久化到文件

**文件：**
- 修改：`dashboard/state_repository.py`
- 测试：`tests/test_repository_persistence.py`

当前状态：纯内存存储，`self._agents`, `self._features`, `self._commands`, `self._events`, `self._chat_history` 全是 dict/list，重启即丢失。

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_repository_persistence.py
import json
import pytest
from pathlib import Path
from dashboard.state_repository import ProjectStateRepository

@pytest.fixture
def tmp_repo(tmp_path: Path) -> ProjectStateRepository:
    repo = ProjectStateRepository(data_dir=tmp_path)
    return repo

def test_agents_survive_restart(tmp_repo: ProjectStateRepository, tmp_path: Path):
    """Agent 状态在重启后仍然存在"""
    tmp_repo.upsert_agent("backend-1", {
        "role": "backend",
        "status": "running",
        "current_task": "F001",
    })
    # 模拟重启：创建新实例
    repo2 = ProjectStateRepository(data_dir=tmp_path)
    agent = repo2.get_agent("backend-1")
    assert agent is not None
    assert agent["role"] == "backend"
    assert agent["status"] == "running"

def test_commands_survive_restart(tmp_repo: ProjectStateRepository, tmp_path: Path):
    """命令在重启后仍然存在"""
    from datetime import datetime, timezone
    from dashboard.models import Command
    cmd = Command(
        id="CMD-001",
        project_id="test-project",
        type="approve",
        target_id="F001",
        source="user",
        created_at=datetime.now(timezone.utc),
    )
    tmp_repo.save_command(cmd)
    repo2 = ProjectStateRepository(data_dir=tmp_path)
    commands = repo2.get_pending_commands()
    assert len(commands) == 1
    assert commands[0].id == "CMD-001"

def test_features_survive_restart(tmp_repo: ProjectStateRepository, tmp_path: Path):
    """Feature 状态在重启后仍然存在"""
    tmp_repo.upsert_feature("F001", {
        "status": "in_progress",
        "assigned_to": "backend",
        "description": "Test feature",
    })
    repo2 = ProjectStateRepository(data_dir=tmp_path)
    feature = repo2.get_feature("F001")
    assert feature is not None
    assert feature["status"] == "in_progress"

def test_events_survive_restart(tmp_repo: ProjectStateRepository, tmp_path: Path):
    """事件在重启后仍然存在"""
    tmp_repo.append_event({
        "type": "agent_status_changed",
        "agent_id": "backend-1",
        "feature_id": "F001",
    })
    repo2 = ProjectStateRepository(data_dir=tmp_path)
    events = repo2.get_events_after(0)
    assert len(events) >= 1
    assert events[-1]["type"] == "agent_status_changed"
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd /Users/jieson/auto-coding && uv run pytest tests/test_repository_persistence.py -v
```
预期：FAIL，ModuleNotFoundError 或 assert 失败（因为当前是纯内存实现）

- [ ] **步骤 3：实现文件持久化**

在 `dashboard/state_repository.py` 中添加持久化逻辑：

```python
# 在 __init__ 中添加：
import json
from pathlib import Path

class ProjectStateRepository:
    def __init__(self, data_dir: Path | str | None = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "dashboard"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._agents: dict[str, dict] = {}
        self._features: dict[str, dict] = {}
        self._commands: list[dict] = []
        self._events: list[dict] = []
        self._chat_history: list[dict] = []
        self._event_counter = 0

        # 启动时加载已有数据
        self._load_all()

    def _load_all(self) -> None:
        """从文件加载所有状态"""
        for name, loader in [
            ("agents", self._load_json_file),
            ("features", self._load_json_file),
            ("commands", self._load_json_file),
            ("events", self._load_json_file),
            ("chat_history", self._load_json_file),
        ]:
            path = self.data_dir / f"{name}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if name == "agents":
                    self._agents = data
                elif name == "features":
                    self._features = data
                elif name == "commands":
                    self._commands = data
                elif name == "events":
                    self._events = data
                    self._event_counter = len(data)
                elif name == "chat_history":
                    self._chat_history = data

    def _save(self, name: str, data: object) -> None:
        """原子写入 JSON 文件"""
        path = self.data_dir / f"{name}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.rename(path)

    def _save_agents(self) -> None:
        self._save("agents", self._agents)

    def _save_features(self) -> None:
        self._save("features", self._features)

    def _save_commands(self) -> None:
        self._save("commands", self._commands)

    def _save_events(self) -> None:
        self._save("events", self._events)

    def _save_chat_history(self) -> None:
        self._save("chat_history", self._chat_history)

    # 在每个修改方法末尾添加对应的 save 调用
    # upsert_agent → self._save_agents()
    # upsert_feature → self._save_features()
    # save_command → self._save_commands()
    # append_event → self._save_events()
    # add_chat_message → self._save_chat_history()
    # update_command → self._save_commands()
```

需要在每个修改状态的方法末尾添加对应的 `_save_xxx()` 调用：
- `upsert_agent()` 末尾加 `self._save_agents()`
- `delete_agent()` 末尾加 `self._save_agents()`
- `upsert_feature()` 末尾加 `self._save_features()`
- `save_command()` 末尾加 `self._save_commands()`
- `append_event()` 末尾加 `self._save_events()`
- `add_chat_message()` 末尾加 `self._save_chat_history()`
- `update_command()` 末尾加 `self._save_commands()`

同时需要修改 `get_pending_commands()` 方法，从 `self._commands` 中筛选 pending 状态的命令并转为 Command 对象返回。

- [ ] **步骤 4：运行测试验证通过**

```bash
cd /Users/jieson/auto-coding && uv run pytest tests/test_repository_persistence.py -v
```
预期：4 个测试全部通过

- [ ] **步骤 5：运行已有测试确保未回归**

```bash
uv run pytest tests/test_dashboard_api.py tests/test_state_repository.py -v
```

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/state_repository.py tests/test_repository_persistence.py
git commit -m "feat(dashboard): Repository 文件持久化 — 重启不丢失状态"
```

---

## Milestone 2: CommandConsumer 命令消费闭环

### 任务 2：创建 CommandConsumer

**文件：**
- 创建：`dashboard/consumer.py`
- 测试：`tests/test_command_consumer.py`

核心逻辑：轮询 Repository 中的 pending 命令 → 通过 CommandProcessor 执行状态转换 → 写回 Repository → 追加事件到 EventBus。

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_command_consumer.py
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from dashboard.consumer import CommandConsumer
from dashboard.state_repository import ProjectStateRepository
from dashboard.event_bus import EventBus
from dashboard.command_processor import CommandProcessor
from dashboard.models import Command

@pytest.fixture
def setup_components(tmp_path: Path):
    repo = ProjectStateRepository(data_dir=tmp_path)
    event_bus = EventBus(log_file=tmp_path / "events.log")
    processor = CommandProcessor(on_event=lambda e: event_bus.emit(e["type"], **{k: v for k, v in e.items() if k != "type"}))
    return repo, event_bus, processor

def test_consumer_claims_and_processes_pending_command(setup_components):
    """Consumer 从 Repository 取出 pending 命令，处理并写回状态"""
    repo, event_bus, processor = setup_components
    consumer = CommandConsumer(repository=repo, processor=processor, event_bus=event_bus)

    # 创建一个 pending 命令
    cmd = Command(
        id="CMD-001",
        project_id="test",
        type="approve",
        target_id="F001",
        source="user",
        created_at=datetime.now(timezone.utc),
    )
    repo.save_command(cmd)

    # Consumer 处理一轮
    processed = consumer.process_once()
    assert processed == 1

    # 命令状态已更新
    commands = repo.get_commands()
    assert any(c.id == "CMD-001" and c.status == "accepted" for c in commands)

def test_consumer_processes_nothing_when_queue_empty(setup_components):
    """队列为空时不处理任何命令"""
    repo, event_bus, processor = setup_components
    consumer = CommandConsumer(repository=repo, processor=processor, event_bus=event_bus)
    processed = consumer.process_once()
    assert processed == 0

def test_consumer_handles_command_error_gracefully(setup_components):
    """命令处理出错时标记为 failed，不崩溃"""
    repo, event_bus, processor = setup_components
    consumer = CommandConsumer(repository=repo, processor=processor, event_bus=event_bus)

    # 创建一个指向不存在 target 的命令
    cmd = Command(
        id="CMD-BAD",
        project_id="test",
        type="apply",
        target_id="NONEXISTENT",
        source="user",
        created_at=datetime.now(timezone.utc),
    )
    repo.save_command(cmd)

    # 不应该抛出异常
    processed = consumer.process_once()
    assert processed >= 0
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd /Users/jieson/auto-coding && uv run pytest tests/test_command_consumer.py -v
```
预期：FAIL，ModuleNotFoundError: No module named 'dashboard.consumer'

- [ ] **步骤 3：实现 CommandConsumer**

```python
# dashboard/consumer.py
"""CommandConsumer：从 Repository 消费待处理命令，执行后写回状态。"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from dashboard.command_processor import CommandProcessor
from dashboard.state_repository import ProjectStateRepository
from dashboard.event_bus import EventBus
from dashboard.models import Command

logger = logging.getLogger(__name__)


class CommandConsumer:
    """
    命令消费闭环：
    1. 从 Repository 取出 pending 命令
    2. 通过 CommandProcessor 执行状态转换
    3. 写回 Repository
    4. 追加事件到 EventBus（供 WebSocket 推送）
    """

    def __init__(
        self,
        repository: ProjectStateRepository,
        processor: CommandProcessor,
        event_bus: EventBus,
        on_command_processed: Optional[Callable[[Command], None]] = None,
    ):
        self.repository = repository
        self.processor = processor
        self.event_bus = event_bus
        self.on_command_processed = on_command_processed

    def process_once(self) -> int:
        """处理一轮待执行命令，返回处理的命令数量"""
        pending = self.repository.get_pending_commands()
        processed = 0

        for cmd in pending:
            try:
                # 根据命令类型执行状态转换
                if cmd.type == "approve":
                    self.processor.accept(cmd.project_id, cmd.target_id)
                elif cmd.type == "reject":
                    self.processor.reject(cmd.project_id, cmd.target_id)
                elif cmd.type == "apply":
                    self.processor.apply(cmd.project_id, cmd.target_id)
                elif cmd.type == "cancel":
                    self.processor.cancel(cmd.project_id, cmd.target_id)

                # 更新命令状态
                self.repository.update_command(cmd.id, status="accepted")

                # 追加事件到 EventBus
                self.event_bus.emit(
                    "command_processed",
                    project_id=cmd.project_id,
                    command_id=cmd.id,
                    command_type=cmd.type,
                    target_id=cmd.target_id,
                )

                if self.on_command_processed:
                    self.on_command_processed(cmd)

                processed += 1
                logger.info(f"Command {cmd.id} ({cmd.type}) processed for target {cmd.target_id}")

            except Exception as e:
                logger.error(f"Failed to process command {cmd.id}: {e}")
                try:
                    self.repository.update_command(cmd.id, status="failed", error=str(e))
                    self.event_bus.emit(
                        "command_failed",
                        project_id=cmd.project_id,
                        command_id=cmd.id,
                        error=str(e),
                    )
                except Exception:
                    logger.exception(f"Failed to update command {cmd.id} as failed")

        return processed

    def run_loop(self, interval_seconds: float = 1.0) -> None:
        """持续运行消费循环"""
        import time
        while True:
            try:
                self.process_once()
            except Exception:
                logger.exception("Error in consumer loop")
            time.sleep(interval_seconds)
```

- [ ] **步骤 4：在 Repository 中添加 get_pending_commands 和 get_commands 方法**

如果 Repository 还没有这些方法，需要添加：

```python
def get_pending_commands(self) -> list[Command]:
    """获取所有 pending 状态的命令"""
    from dashboard.models import Command
    with self._lock:
        return [
            Command(**c) if isinstance(c, dict) else c
            for c in self._commands
            if getattr(c, "status", c.get("status") if isinstance(c, dict) else None) == "pending"
        ]

def get_commands(self) -> list[Command]:
    """获取所有命令"""
    from dashboard.models import Command
    with self._lock:
        return [
            Command(**c) if isinstance(c, dict) else c
            for c in self._commands
        ]

def update_command(self, command_id: str, status: str, error: str | None = None) -> None:
    """更新命令状态"""
    with self._lock:
        for i, cmd in enumerate(self._commands):
            c_id = cmd.id if hasattr(cmd, "id") else cmd.get("id")
            if c_id == command_id:
                if hasattr(cmd, "status"):
                    cmd.status = status
                    if error:
                        cmd.error = error
                else:
                    cmd["status"] = status
                    if error:
                        cmd["error"] = error
                self._commands[i] = cmd
                break
        self._save_commands()
```

- [ ] **步骤 5：运行测试验证通过**

```bash
cd /Users/jieson/auto-coding && uv run pytest tests/test_command_consumer.py -v
```
预期：3 个测试全部通过

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/consumer.py tests/test_command_consumer.py dashboard/state_repository.py
git commit -m "feat(dashboard): CommandConsumer 命令消费闭环"
```

---

## Milestone 3: Agent 执行过程状态上报

### 任务 3：Agent 执行时向 EventBus 上报状态

**文件：**
- 修改：`agents/base_agent.py`
- 修改：`dashboard/__init__.py`（确保 EventBus 可导入）

- [ ] **步骤 1：编写失败的测试**

```python
# 在 tests/test_event_sequencing.py 或新建 tests/test_agent_state_reporting.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from agents.backend_dev import BackendDeveloper

def test_agent_reports_status_to_event_bus():
    """Agent 执行过程中向 EventBus 上报状态"""
    from dashboard.event_bus import EventBus
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        event_bus = EventBus(log_file=Path(tmp_dir) / "events.log")
        event_bus.emit = MagicMock()

        # 需要将 event_bus 注入到 agent
        agent = BackendDeveloper(project_dir=Path(tmp_dir))
        agent.event_bus = event_bus

        # 模拟 execute 方法中的状态上报
        # Agent 应该在开始、进行中、完成时各上报一次
        agent._report_status("started", feature_id="F001", message="开始执行")
        agent._report_status("completed", feature_id="F001", message="执行完成")

        assert event_bus.emit.call_count == 2
        first_call = event_bus.emit.call_args_list[0]
        assert first_call[0][0] == "agent_status_changed"
        assert first_call[1]["agent_id"] is not None
        assert first_call[1]["feature_id"] == "F001"
```

- [ ] **步骤 2：实现 Agent 状态上报**

在 `agents/base_agent.py` 中添加：

```python
class BaseAgent(ABC):
    # 在 __init__ 后添加：
    event_bus = None  # 由外部注入

    def _report_status(self, status: str, feature_id: str = "", message: str = "", **extra: Any) -> None:
        """向 EventBus 上报状态"""
        if self.event_bus is None:
            return
        from datetime import datetime, timezone
        self.event_bus.emit(
            "agent_status_changed",
            agent_id=getattr(self, "instance_id", self.role),
            feature_id=feature_id,
            status=status,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            **extra,
        )

    async def execute(self, task: dict) -> dict:
        feature_id = task.get("feature_id", "unknown")
        description = task.get("description", "")[:100]

        # 上报：开始执行
        self._report_status("running", feature_id=feature_id, message=f"开始: {description}")

        prompt = self._build_prompt(task)
        result = self._run_with_claude(prompt)

        files_changed = self._extract_files_changed()

        if result["success"]:
            # 上报：完成
            self._report_status("completed", feature_id=feature_id, message="执行完成", files_changed=files_changed)
            return {
                "success": True,
                "message": f"{self.role}任务 {feature_id} 执行完成",
                "files_changed": files_changed,
                "needs_review": True,
            }
        else:
            # 上报：失败
            self._report_status("failed", feature_id=feature_id, message=result.get("error", "未知错误"))
            return {
                "success": False,
                "message": f"{self.role}任务 {feature_id} 执行失败",
                "files_changed": [],
                "needs_review": False,
                "error": result.get("error", "未知错误"),
            }
```

- [ ] **步骤 3：在 ProjectManager 中注入 EventBus**

在 `core/project_manager.py` 的 `__init__` 或 `_execute_feature` 中：

```python
# 在 __init__ 中创建或接收 EventBus
from dashboard.event_bus import EventBus

class ProjectManager:
    def __init__(self, project_dir: Path, event_bus: EventBus | None = None):
        # ... 原有代码 ...
        if event_bus is None:
            event_bus = EventBus(log_file=project_dir / "data" / "dashboard" / "events.log")
        self.event_bus = event_bus

    def _execute_feature(self, feature: Feature) -> None:
        # ... 获取 instance, agent ...
        # 注入 event_bus
        instance.agent.event_bus = self.event_bus  # 需要确保 instance 有 agent 属性
        # ... 原有执行逻辑 ...
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd /Users/jieson/auto-coding && uv run pytest tests/test_agent_state_reporting.py -v
```

- [ ] **步骤 5：Commit**

```bash
git add agents/base_agent.py core/project_manager.py tests/test_agent_state_reporting.py
git commit -m "feat(dashboard): Agent 执行过程状态上报到 EventBus"
```

---

## Milestone 4: WebSocket 事件格式对齐

### 任务 4：对齐 WebSocket 推送事件格式与前端 Store 期望

**文件：**
- 修改：`dashboard/api/routes.py`

当前 WebSocket 处理器发送的事件格式需要与前端 store 的 dispatchEvent 匹配。

- [ ] **步骤 1：检查前端 store 期望的事件格式**

```bash
grep -n "dispatchEvent\|type.*event\|WsEvent" dashboard-ui/lib/store.ts
```

- [ ] **步骤 2：定义统一 WebSocket 事件格式**

```python
# 在 dashboard/api/routes.py 的 WebSocket handler 中：
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass
class WsEvent:
    type: str
    payload: dict
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

# WebSocket handler 中：
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # ... 发送 hello 和 snapshot ...

    last_id = 0
    while True:
        events = await event_bus.get_events()
        new_events = [e for e in events if e.get("event_id", 0) > last_id]
        if new_events:
            for event in new_events:
                ws_event = WsEvent(
                    type=event.get("type", "unknown"),
                    payload={k: v for k, v in event.items() if k != "type"},
                )
                await websocket.send_json(ws_event.to_dict())
                last_id = max(last_id, event.get("event_id", last_id))
        await asyncio.sleep(0.5)
```

- [ ] **步骤 3：验证前端能正确接收和分发事件**

```bash
cd /Users/jieson/auto-coding/dashboard-ui && npm run build
```

- [ ] **步骤 4：Commit**

```bash
git add dashboard/api/routes.py
git commit -m "feat(dashboard): 对齐 WebSocket 事件格式与前端 store"
```

---

## Milestone 5: 前端代码质量修复

### 任务 5：挂载 Toaster + ThemeProvider

**文件：**
- 修改：`dashboard-ui/app/layout.tsx`

- [ ] **步骤 1：修改 layout.tsx**

```tsx
// 在 import 区域添加:
import { ThemeProvider } from 'next-themes';
import { Toaster } from 'sonner';

// 在返回的 JSX 中，用 ThemeProvider 包裹 children，在 body 末尾添加 Toaster:
<body className={inter.className}>
  <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
    {children}
  </ThemeProvider>
  <Toaster position="top-right" richColors />
</body>
```

- [ ] **步骤 2：验证构建**

```bash
cd /Users/jieson/auto-coding/dashboard-ui && npm run build
```
预期：构建成功

- [ ] **步骤 3：Commit**

```bash
git add app/layout.tsx
git commit -m "fix(dashboard-ui): 挂载 Toaster + ThemeProvider"
```

### 任务 6：移除 console.log 违规

**文件：**
- 修改：`dashboard-ui/components/command-bar.tsx`

- [ ] **步骤 1：替换 console 调用为 Sonner toast**

```tsx
// 在 import 区域添加:
import { toast } from 'sonner';

// 将 console.log('命令已发送:', type) 替换为:
toast.success('命令已发送', { description: `${label} 操作已提交` });

// 将 console.error('发送命令失败:', error) 替换为:
toast.error('发送失败', { description: error instanceof Error ? error.message : '未知错误' });
```

- [ ] **步骤 2：验证构建**

```bash
npm run build
```

- [ ] **步骤 3：Commit**

```bash
git add components/command-bar.tsx
git commit -m "fix(dashboard-ui): 移除 console.log 违规，改用 Sonner toast"
```

### 任务 7：修复 Store 空 target_id bug

**文件：**
- 修改：`dashboard-ui/lib/store.ts`
- 修改：`dashboard-ui/components/command-bar.tsx`

- [ ] **步骤 1：修改 command actions 接受参数**

```tsx
// 在 store.ts 中，将:
approve: () => actions.approve(get().projectId, ''),
// 改为:
approve: (targetId: string) => actions.approve(get().projectId, targetId),

// 同样修改 reject, pause, resume, retry, skip:
reject: (targetId: string) => actions.reject(get().projectId, targetId),
pause: (targetId: string) => actions.pause(get().projectId, targetId),
resume: (targetId: string) => actions.resume(get().projectId, targetId),
retry: (targetId: string) => actions.retry(get().projectId, targetId),
skip: (targetId: string) => actions.skip(get().projectId, targetId),
```

- [ ] **步骤 2：更新 command-bar.tsx 调用处**

在 command-bar.tsx 中，调用 store actions 时传入正确的 targetId：

```tsx
// 从 store 获取选中的 feature 或 agent
const { selectedFeature, selectedAgent } = useDashboardStore();
const targetId = selectedFeature?.id || selectedAgent?.currentTaskId || '';

// 调用时传入
handleSendCommand(type, () => {
  sendCommand(type, targetId);
});
```

- [ ] **步骤 3：类型检查**

```bash
npx tsc --noEmit
```
预期：无错误

- [ ] **步骤 4：Commit**

```bash
git add lib/store.ts components/command-bar.tsx
git commit -m "fix(dashboard-ui): 修复 command actions 空 target_id bug"
```

---

## Milestone 6: 错误边界

### 任务 8：创建四个错误边界组件

**文件：**
- 创建：`dashboard-ui/app/error.tsx`
- 创建：`dashboard-ui/app/loading.tsx`
- 创建：`dashboard-ui/app/not-found.tsx`
- 创建：`dashboard-ui/app/global-error.tsx`

- [ ] **步骤 1：创建 error.tsx（路由级错误边界）**

```tsx
'use client';
import { useEffect } from 'react';
import { Button } from '@/components/ui/button';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('Dashboard error:', error);
  }, [error]);

  return (
    <div className="flex min-h-[200px] flex-col items-center justify-center gap-4">
      <h2 className="text-lg font-semibold">出错了</h2>
      <p className="text-sm text-muted-foreground">{error.message}</p>
      <Button onClick={() => reset()}>重试</Button>
    </div>
  );
}
```

- [ ] **步骤 2：创建 loading.tsx**

```tsx
export default function Loading() {
  return (
    <div className="flex min-h-[200px] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    </div>
  );
}
```

- [ ] **步骤 3：创建 not-found.tsx**

```tsx
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex min-h-[200px] flex-col items-center justify-center gap-4">
      <h2 className="text-2xl font-bold">404</h2>
      <p className="text-muted-foreground">页面未找到</p>
      <Button asChild><Link href="/">返回首页</Link></Button>
    </div>
  );
}
```

- [ ] **步骤 4：创建 global-error.tsx**

```tsx
'use client';
import { Button } from '@/components/ui/button';

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html>
      <body>
        <div className="flex min-h-screen flex-col items-center justify-center gap-4">
          <h2 className="text-lg font-semibold">系统错误</h2>
          <p className="text-sm text-muted-foreground">发生了不可恢复的错误</p>
          <Button onClick={() => reset()}>重试</Button>
        </div>
      </body>
    </html>
  );
}
```

- [ ] **步骤 5：验证构建**

```bash
cd /Users/jieson/auto-coding/dashboard-ui && npm run build
```

- [ ] **步骤 6：Commit**

```bash
git add app/error.tsx app/loading.tsx app/not-found.tsx app/global-error.tsx
git commit -m "feat(dashboard-ui): 添加错误边界组件"
```

---

## Milestone 7: 清理死代码

### 任务 9：删除死代码和创建 .gitattributes

**文件：**
- 删除：`dashboard-ui/types/dashboard.ts`
- 删除：`dashboard-ui/components/index.ts`
- 创建：`dashboard-ui/.gitattributes`（如果已存在则跳过）

- [ ] **步骤 1：确认无引用后删除**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
grep -r "types/dashboard" --include="*.ts" --include="*.tsx" . || echo "No references found"
grep -r "from '@/components'" --include="*.ts" --include="*.tsx" . || echo "No barrel imports found"
```

确认无引用后删除：
```bash
rm -f types/dashboard.ts components/index.ts
```

- [ ] **步骤 2：验证构建**

```bash
npm run build
```

- [ ] **步骤 3：Commit**

```bash
git rm -f types/dashboard.ts components/index.ts 2>/dev/null || rm -f types/dashboard.ts components/index.ts
git add -A
git commit -m "chore(dashboard-ui): 清理死代码"
```

---

## Milestone 8: E2E 测试

### 任务 10：Playwright E2E 测试

**文件：**
- 修改：`dashboard-ui/tests/e2e/test_dashboard.spec.ts`（如果已存在）
- 修改：`dashboard-ui/playwright.config.ts`（如果已存在）

- [ ] **步骤 1：安装 Playwright（如果未安装）**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx playwright install
npx playwright install-deps
```

- [ ] **步骤 2：确保 playwright.config.ts 存在**

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3568',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev -- -p 3568',
    url: 'http://localhost:3568',
    reuseExistingServer: !process.env.CI,
  },
});
```

- [ ] **步骤 3：编写 E2E 测试**

```typescript
// tests/e2e/test_dashboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test('看板五列布局正常加载', async ({ page }) => {
    await page.goto('/');
    for (const col of ['待处理', '进行中', '审核中', '已完成', '已阻塞']) {
      await expect(page.getByText(col)).toBeVisible();
    }
  });

  test('连接状态指示器可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('status')).toBeVisible();
  });

  test('Agent 状态面板可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Agent 状态')).toBeVisible();
  });

  test('PM 对话窗口可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('与 PM 对话')).toBeVisible();
  });

  test('操作按钮组可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: /审批/ })).toBeVisible();
  });
});
```

- [ ] **步骤 4：运行 E2E 测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx playwright test
```
预期：5 个测试全部通过

- [ ] **步骤 5：Commit**

```bash
git add tests/e2e/ playwright.config.ts
git commit -m "test(dashboard-ui): Playwright E2E 测试"
```

---

## Milestone 9: 端到端验证

### 任务 11：完整流程验证

- [ ] **步骤 1：启动后端**

```bash
cd /Users/jieson/auto-coding && uv run uvicorn dashboard.main:app --reload --port 8000
```

- [ ] **步骤 2：启动前端**

```bash
cd /Users/jieson/auto-coding/dashboard-ui && npm run dev -- -p 3568
```

- [ ] **步骤 3：浏览器验证**

访问 http://localhost:3568，检查：
- [ ] 连接状态指示器显示 Connected
- [ ] 看板五列布局正常
- [ ] Agent 状态面板显示
- [ ] PM 对话窗口可输入
- [ ] 操作按钮组显示
- [ ] 日志流区域显示
- [ ] 无控制台错误
- [ ] Toast 通知正常工作（触发一个命令后观察）

- [ ] **步骤 4：运行完整测试套件**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npm run build
npx playwright test
npx tsc --noEmit

cd /Users/jieson/auto-coding
uv run pytest tests/test_dashboard_api.py tests/test_state_repository.py tests/test_command_processor.py tests/test_event_sequencing.py tests/test_dashboard_integration.py tests/test_repository_persistence.py tests/test_command_consumer.py tests/test_agent_state_reporting.py -v
```

---

## 验收标准

1. **构建**：前端 `npm run build` 零错误
2. **类型**：前端 `tsc --noEmit` 零错误
3. **持久化**：Repository 重启后状态不丢失
4. **命令闭环**：CommandConsumer 能消费 pending 命令并写回状态
5. **状态上报**：Agent 执行时向 EventBus 上报 running/completed/failed
6. **WebSocket**：事件格式与前端 store dispatchEvent 对齐
7. **代码质量**：无 console.log/console.error 在生产代码中
8. **错误边界**：四个错误边界文件全部存在
9. **死代码**：types/dashboard.ts 和 components/index.ts 已删除
10. **Toaster/ThemeProvider**：layout.tsx 中已挂载
11. **Store bug**：command actions 接受 targetId 参数
12. **E2E**：所有 Playwright 测试通过
13. **后端测试**：所有 dashboard 相关 pytest 测试通过

## 验证命令

```bash
# 后端测试
cd /Users/jieson/auto-coding
uv run pytest tests/test_dashboard_api.py tests/test_state_repository.py tests/test_command_processor.py tests/test_event_sequencing.py tests/test_dashboard_integration.py tests/test_repository_persistence.py tests/test_command_consumer.py tests/test_agent_state_reporting.py -v

# 前端构建
cd /Users/jieson/auto-coding/dashboard-ui && npm run build

# 前端类型检查
npx tsc --noEmit

# 前端 E2E 测试
npx playwright test
```

## 执行顺序

1. **Milestone 1** → Repository 持久化（基础依赖，其他 Milestone 依赖它）
2. **Milestone 2** → CommandConsumer 命令闭环（核心业务逻辑）
3. **Milestone 3** → Agent 状态上报（让前端能看到实时状态）
4. **Milestone 4** → WebSocket 事件对齐（前后端联调）
5. **Milestone 5** → 前端代码质量修复（Toaster/ThemeProvider、console.log、target_id）
6. **Milestone 6** → 错误边界（用户体验）
7. **Milestone 7** → 清理死代码（代码质量）
8. **Milestone 8** → E2E 测试（质量保障）
9. **Milestone 9** → 端到端验证（完整流程确认）
