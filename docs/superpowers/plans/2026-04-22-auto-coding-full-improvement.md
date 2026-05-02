# Auto-Coding 全量改进实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 按照 three-project-roadmap.md 的 9 个 Phase，将 auto-coding 项目从"能跑"推进到"可维护、可扩展、可交付"

**架构：** 基于三项目对比（multica、auto-coding-agent-demo、当前项目）的改进路线，通过文档契约、状态统一、工作流外置、前端治理等手段系统性提升工程质量

**技术栈：** Python 3.12+, FastAPI, Zustand, TypeScript, Playwright, pytest

**计划基于：** `docs/three-project-roadmap.md`

---

## Phase 0：基线冻结与设计准备

### 任务 0.1：记录系统基线文档

**文件：**
- 创建：`docs/baselines/current-system-baseline.md`

- [ ] **步骤 1：创建基线目录**

```bash
mkdir -p docs/baselines
```

- [ ] **步骤 2：编写系统基线文档**

```markdown
# 系统基线文档

> 记录时间：2026-04-22
> 目的：为后续改造建立对照基线

## 1. 命令入口

| 命令 | 功能 | 状态 |
|------|------|------|
| `ai-dev init` | 初始化项目 | 可用 |
| `ai-dev run` | 运行项目 | 可用 |
| `ai-dev status` | 查看状态 | 可用 |
| `ai-dev tail` | 查看日志 | 可用 |
| `ai-dev dashboard` | 启动 Dashboard | 可用 |

入口文件：`cli.py`

## 2. 后端接口

### REST API
- `GET /api/features` - 获取 Feature 列表
- `GET /api/agents` - 获取 Agent 列表
- `POST /api/commands` - 发送命令
- `GET /api/events` - 获取事件列表

### WebSocket
- `ws://localhost:8000/ws` - 实时事件推送

服务入口：`start_dashboard.py`

## 3. 状态文件

| 文件 | 内容 | 格式 |
|------|------|------|
| `data/features.json` | Feature 状态 | JSON |
| `data/dashboard/state.json` | Dashboard 状态 | JSON |
| SQLite `tasks` | 任务队列 | SQLite |
| `claude-progress.txt` | 进度日志 | 文本 |

## 4. 核心模块

| 模块 | 职责 | 文件 |
|------|------|------|
| ProjectManager | 项目编排 | `core/project_manager.py` |
| FeatureTracker | Feature 状态跟踪 | `core/feature_tracker.py` |
| TaskQueue | 任务队列调度 | `core/task_queue.py` |
| Coordinator | Agent 协调 | `dashboard/coordinator.py` |
| StateRepository | 状态仓储 | `dashboard/state_repository.py` |

## 5. 前端结构

| 文件 | 职责 |
|------|------|
| `dashboard-ui/lib/store.ts` | Zustand 全局状态 |
| `dashboard-ui/lib/api.ts` | API 请求层 |
| `dashboard-ui/lib/types.ts` | TypeScript 类型定义 |
| `dashboard-ui/lib/websocket.ts` | WebSocket 连接 |

## 6. 测试基线

```bash
# 运行全量测试
cd /Users/jieson/auto-coding
uv run pytest tests/ -v
```

当前测试通过情况待记录。

## 7. Agent 角色

9 个角色 Agent：
1. Product Manager
2. Architect
3. Backend Developer
4. Frontend Developer
5. Test Engineer
6. Code Reviewer
7. Security Reviewer
8. DevOps Engineer
9. Coordinator
```

- [ ] **步骤 3：Commit**

```bash
git add docs/baselines/current-system-baseline.md
git commit -m "docs: add system baseline document for refactoring reference"
```

---

## Phase 1：架构契约文档

### 任务 1.1：创建 ARCHITECTURE.md

**文件：**
- 创建：`ARCHITECTURE.md`

- [ ] **步骤 1：编写架构契约文档**

```markdown
# Auto-Coding 架构契约

> 本文档定义系统各模块的职责边界、状态归属、事件规则和禁止事项。
> 所有 PR 的代码评审应引用此文档。

## 1. 系统总览

```
┌─────────────────────────────────────────────────────┐
│                    CLI (cli.py)                      │
│         ai-dev init / run / status / tail            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                     core/                            │
│  ProjectManager / FeatureTracker / TaskQueue         │
│  职责：项目初始化、Feature 规划、Agent 编排流程        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   dashboard/                         │
│  API / WebSocket / Coordinator / StateRepository     │
│  职责：对外 API、事件广播、命令处理、仓储持久化         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  dashboard-ui/                       │
│  Next.js / Zustand / WebSocket Client                │
│  职责：数据展示、用户交互、API 调用、事件消费           │
└─────────────────────────────────────────────────────┘
```

## 2. 模块职责边界

### `core/`

**负责：**
- 项目初始化流程
- Feature 规划与排序
- Agent 编排相关的业务流程
- Feature 执行协调
- 验收流程

**不负责：**
- WebSocket 推送（→ dashboard/）
- REST API 定义（→ dashboard/）
- 前端状态结构（→ dashboard-ui/）
- Agent prompt 内容（→ agents/）

### `dashboard/`

**负责：**
- 对外 REST API
- WebSocket 广播
- 命令接收与处理
- 状态仓储持久化
- 协调器运行与观测
- Event Bus 管理

**不负责：**
- 直接生成 PRD（→ core/）
- 直接写业务 prompt（→ agents/）
- 最终状态裁决（→ Repository）

### `agents/`

**负责：**
- 角色 prompt 组合
- 调用 Claude CLI 执行具体任务
- 上报执行状态（success/failed/blocked）

**不负责：**
- 最终状态裁决（→ Repository）
- 任务编排（→ core/）
- 直接操作 dashboard store
- 直接修改 features.json

### `dashboard-ui/`

**负责：**
- 数据展示
- 用户交互
- 调用后端 API
- WebSocket 事件消费与增量更新

**不负责：**
- 定义业务事实源（→ Repository）
- 复写后端状态机逻辑
- 持久化纯 UI 状态到后端

## 3. 状态源归属

| 数据类型 | 唯一事实源 | 允许缓存位置 | 禁止行为 |
|----------|------------|--------------|----------|
| Feature 状态 | `ProjectStateRepository` | 前端 Query Cache | FeatureTracker 和 Dashboard 各自维护两套最终状态 |
| Task 状态 | `ProjectStateRepository` | TaskQueue 调度缓存 | SQLite TaskQueue 成为孤立任务系统 |
| Command 状态 | `ProjectStateRepository` | 前端 Query Cache | 前端本地直接推断最终命令结果 |
| Event 历史 | `ProjectStateRepository` | WebSocket 增量缓存 | EventBus 队列被当成长期存储 |
| Agent 实例状态 | `ProjectStateRepository` | WebSocket 增量缓存 | 仅前端 store 知道 Agent 状态 |
| BlockingIssue | `ProjectStateRepository` | 前端 Query Cache | 阻塞信息只存在于日志中 |
| UI 开关/抽屉/选中项 | Zustand | 无 | 后端持久化纯 UI 状态 |
| ExecutionRun | `ProjectStateRepository` | 前端 Query Cache | 执行轮次信息分散在多处 |

## 4. 事件流规则

1. 所有事件必须先追加到 `ProjectStateRepository`
2. 事件写入后，通过 EventBus 广播给订阅者
3. WebSocket 仅作为事件的实时推送通道，不是事实源
4. 前端收到 WebSocket 事件后，应通过 HTTP API 重新拉取或增量更新

## 5. 命令流规则

1. 用户通过 CLI 或 UI 发送 Command
2. Command 由 `CommandProcessor` 接收并验证
3. 合法 Command 写入 Repository
4. Command 执行结果回写 Repository
5. 结果通过 WebSocket 推送给前端

## 6. Agent 执行流规则

1. `ProjectManager` 选择下一个可执行的 Feature
2. 创建 ExecutionRun 记录
3. 按顺序调度各角色 Agent
4. Agent 上报执行结果（含 blocked 状态）
5. 结果写入 Repository
6. 验证服务执行验收
7. 根据验收结果决定是否进入下一轮

## 7. 前端状态管理规则

1. 服务端数据（features/agents/events）通过 React Query 管理
2. 纯 UI 状态（选中项/抽屉开关）通过 Zustand 管理
3. 页面首次加载走 HTTP 快照
4. WebSocket 仅做增量更新，触发 Query invalidate
5. 不在前端重复实现后端状态机

## 8. 禁止事项

- **禁止**在前端重复实现后端状态机
- **禁止**一个业务事实同时写入两个长期事实源
- **禁止**把 WebSocket 事件当成唯一事实源
- **禁止**`ProjectManager` 继续新增与 API / WebSocket 直接耦合的逻辑
- **禁止**在代码中硬编码密钥
- **禁止**Agent 直接修改 features.json 或 state.json
```

- [ ] **步骤 2：Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs: add architecture contract defining module boundaries and state ownership"
```

---

## Phase 2：工作流协议外置

### 任务 2.1：创建 WORKFLOW.md

**文件：**
- 创建：`WORKFLOW.md`

- [ ] **步骤 1：编写工作流协议文档**

```markdown
# Auto-Coding 工作流协议

> 本文档定义 Agent 的执行规则，让"如何开始、如何执行、如何结束"显式可见。

## 1. 执行单元定义

### Feature
- **含义：** 用户需求拆出的业务项
- **输入：** PRD 分解的功能列表
- **输出：** 可验收的代码和文档
- **生命周期：** pending → in_progress → verifying → completed / failed / blocked

### Task
- **含义：** 可执行工作单元，是 Feature 的子项
- **输入：** Feature 分解的具体工作
- **输出：** 完成的代码变更
- **生命周期：** pending → assigned → running → completed / failed / blocked
- **单次执行边界：** 一次执行最多完成一个 Task 或一个明确子目标

### Command
- **含义：** 人对系统的控制指令
- **输入：** 用户操作（CLI 或 UI）
- **输出：** 系统响应
- **类型：** approve / reject / pause / resume / reset

### 三者关系
```
Feature = "实现任务看板"
  ├── Task = "前端实现看板列组件"
  ├── Task = "后端实现看板 API"
  └── Task = "E2E 测试看板交互"

Command = "approve" → 验收通过后进入下一个 Feature
Command = "reject"  → 退回重新执行
Command = "pause"   → 暂停当前 Feature
Command = "resume"  → 恢复执行
```

## 2. Agent 如何选择下一个任务

1. 从 Repository 读取 Feature 列表
2. 找到第一个 `pending` 且依赖已满足的 Feature
3. 检查是否有未解决的 BlockingIssue
4. 无阻塞 → 创建 ExecutionRun → 开始执行
5. 有阻塞 → 标记 blocked → 等待人工介入

## 3. 一次执行允许做几件事

**原则：单次执行只完成一个 Task 或一个明确子目标**

- 不允许在一次执行中同时完成多个 Task
- 如果当前 Task 完成，应停止并汇报
- 如果当前 Task 无法完成，应上报 blocked

## 4. 什么时候必须跑测试

- 每次修改代码后必须跑相关单元测试
- 修改核心逻辑后必须跑全量测试
- 测试不通过不得标记 Task 为 completed

## 5. 什么情况下可以标记完成

满足以下全部条件：
1. 所有代码已提交
2. 相关测试已通过
3. 验收检查清单已通过
4. 无未解决的阻塞项

## 6. 什么情况下必须进入阻塞

- 缺少必要环境变量 → `missing_env`
- 缺少必要凭据（API Key 等） → `missing_credentials`
- 外部服务不可用 → `external_service_down`
- 依赖的前置 Feature 未完成 → `dependency_not_met`
- 代码错误导致无法继续 → `code_error`
- 资源耗尽（配额/额度） → `resource_exhausted`

## 7. 什么情况下必须请求 PM 审批

- Feature 执行完成，等待验收前
- 遇到需要人工决策的阻塞项
- 需要修改 PRD 或功能范围

## 8. 阻塞上报结构

```json
{
  "success": false,
  "blocked": true,
  "blocking_type": "missing_env",
  "blocking_message": "缺少 OPENAI_API_KEY",
  "required_human_action": "请在 .env 中配置 OPENAI_API_KEY"
}
```
```

- [ ] **步骤 2：Commit**

```bash
git add WORKFLOW.md
git commit -m "docs: add workflow protocol defining execution rules and agent behavior"
```

### 任务 2.2：创建 execution-plan.json 方案

**文件：**
- 创建：`docs/execution-plan-schema.json`
- 创建：`data/execution-plan.json`（示例）

- [ ] **步骤 1：定义执行计划 Schema**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ExecutionPlan",
  "type": "object",
  "required": ["project_id", "run_id", "features"],
  "properties": {
    "project_id": { "type": "string" },
    "run_id": { "type": "string" },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" },
    "features": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["feature_id", "title", "status", "tasks"],
        "properties": {
          "feature_id": { "type": "string" },
          "title": { "type": "string" },
          "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed", "failed", "blocked"]
          },
          "current_task_id": { "type": "string" },
          "tasks": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["task_id", "title", "owner_role", "status"],
              "properties": {
                "task_id": { "type": "string" },
                "title": { "type": "string" },
                "owner_role": { "type": "string" },
                "status": {
                  "type": "string",
                  "enum": ["pending", "assigned", "running", "completed", "failed", "blocked"]
                },
                "blocking_reason": { "type": "string" },
                "started_at": { "type": "string" },
                "completed_at": { "type": "string" }
              }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **步骤 2：创建示例执行计划文件**

```json
{
  "project_id": "demo-project",
  "run_id": "run-001",
  "created_at": "2026-04-22T00:00:00Z",
  "updated_at": "2026-04-22T00:00:00Z",
  "features": [
    {
      "feature_id": "F-001",
      "title": "实现 Agent 监控页",
      "status": "pending",
      "current_task_id": null,
      "tasks": [
        {
          "task_id": "T-001",
          "title": "补后端 agents 列表接口",
          "owner_role": "backend",
          "status": "pending",
          "blocking_reason": ""
        }
      ]
    }
  ]
}
```

- [ ] **步骤 3：Commit**

```bash
git add docs/execution-plan-schema.json data/execution-plan.json
git commit -m "docs: add execution plan schema and example for auditability"
```

### 任务 2.3：CLI 新增只读查看命令

**文件：**
- 修改：`cli.py`

- [ ] **步骤 1：在 cli.py 中新增 plan 命令**

找到 cli.py 中的命令定义区域（Typer/Cli 注册处），新增：

```python
@app.command()
def plan():
    """输出当前执行计划"""
    import json
    from pathlib import Path
    
    plan_file = Path("data/execution-plan.json")
    if not plan_file.exists():
        print("执行计划文件不存在。请先运行 ai-dev init 初始化项目。")
        return
    
    with open(plan_file) as f:
        plan = json.load(f)
    
    print(f"项目: {plan['project_id']}")
    print(f"轮次: {plan['run_id']}")
    print()
    
    for feature in plan["features"]:
        status_icon = {"pending": "○", "in_progress": "▶", "completed": "✓", "failed": "✗", "blocked": "⏸"}.get(feature["status"], "?")
        print(f"{status_icon} {feature['feature_id']}: {feature['title']} ({feature['status']})")
        for task in feature.get("tasks", []):
            task_icon = {"pending": "  ○", "running": "  ▶", "completed": "  ✓", "failed": "  ✗", "blocked": "  ⏸"}.get(task["status"], "  ?")
            print(f"  {task_icon} {task['task_id']}: {task['title']} [{task['owner_role']}]")
            if task.get("blocking_reason"):
                print(f"    ⚠ 阻塞: {task['blocking_reason']}")
        print()
```

- [ ] **步骤 2：新增 explain-state 命令**

```python
@app.command()
def explain_state():
    """输出当前项目中 Feature / Task / Command 的状态说明"""
    from pathlib import Path
    import json
    
    print("=== 当前项目状态 ===")
    print()
    
    # 读取 features.json
    features_file = Path("data/features.json")
    if features_file.exists():
        with open(features_file) as f:
            features = json.load(f)
        print(f"Feature 总数: {len(features)}")
        for f_item in features:
            print(f"  - {f_item.get('id', '?')}: {f_item.get('title', '?')} ({f_item.get('status', '?')})")
    else:
        print("features.json 不存在")
    
    print()
    
    # 读取 state.json
    state_file = Path("data/dashboard/state.json")
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        print(f"Agent 数量: {len(state.get('agents', []))}")
        print(f"Event 数量: {len(state.get('events', []))}")
    else:
        print("state.json 不存在")
```

- [ ] **步骤 3：新增 blocked 命令**

```python
@app.command()
def blocked():
    """输出当前所有阻塞项"""
    from pathlib import Path
    import json
    
    print("=== 当前阻塞项 ===")
    print()
    
    # 从执行计划中查找
    plan_file = Path("data/execution-plan.json")
    found = False
    if plan_file.exists():
        with open(plan_file) as f:
            plan = json.load(f)
        for feature in plan["features"]:
            for task in feature.get("tasks", []):
                if task.get("blocking_reason"):
                    found = True
                    print(f"⏸ {feature['feature_id']} / {task['task_id']}: {task['title']}")
                    print(f"   原因: {task['blocking_reason']}")
                    print()
    
    # 从 state.json 中查找
    state_file = Path("data/dashboard/state.json")
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        for issue in state.get("blocking_issues", []):
            if issue.get("status") == "open":
                found = True
                print(f"⏸ {issue.get('related_feature_id', '?')} / {issue.get('blocking_id', '?')}: {issue.get('title', '?')}")
                print(f"   类型: {issue.get('type', '?')}")
                print(f"   需要: {issue.get('required_human_action', '?')}")
                print()
    
    if not found:
        print("当前没有阻塞项。")
```

- [ ] **步骤 4：Commit**

```bash
git add cli.py
git commit -m "feat: add CLI read-only commands for plan, state, and blocked items"
```

---

## Phase 3：统一状态源

### 任务 3.1：定义统一状态模型文档

**文件：**
- 创建：`docs/state-model.md`

- [ ] **步骤 1：编写状态模型文档**

```markdown
# 统一状态模型

> 定义系统中每种业务事实的唯一归属、生命周期和流转规则。

## Feature

- **主键：** `feature_id` (string, e.g. "F-001")
- **状态：** pending → in_progress → verifying → completed / failed / blocked
- **谁能改：** ProjectManager（编排层）、FeatureExecutionService（执行层）
- **从哪里读：** ProjectStateRepository
- **何时广播：** 状态变更时通过 EventBus → WebSocket

## Task

- **主键：** `task_id` (string, e.g. "T-001")
- **状态：** pending → assigned → running → completed / failed / blocked
- **谁能改：** TaskQueue（调度层）、FeatureExecutionService（执行层）
- **从哪里读：** ProjectStateRepository
- **何时广播：** 状态变更时通过 EventBus → WebSocket

## AgentInstance

- **主键：** `agent_id` (string, e.g. "agent-pm-001")
- **状态：** idle → running → completed / failed / blocked
- **谁能改：** Coordinator（协调层）
- **从哪里读：** ProjectStateRepository
- **何时广播：** 状态变更时通过 EventBus → WebSocket

## Command

- **主键：** `command_id` (string, e.g. "cmd-001")
- **状态：** pending → processing → completed / failed
- **谁能改：** CommandProcessor
- **从哪里读：** ProjectStateRepository
- **何时广播：** 状态变更时通过 EventBus → WebSocket

## Event

- **主键：** `event_id` (string, UUID)
- **类型：** feature_started, feature_completed, task_assigned, agent_error, blocking_created, blocking_resolved
- **谁能改：** 任何业务服务（追加写入，不可修改）
- **从哪里读：** ProjectStateRepository
- **何时广播：** 写入后立即通过 EventBus 广播

## BlockingIssue

- **主键：** `blocking_id` (string, e.g. "BLK-001")
- **状态：** open → resolved
- **谁能改：** Agent（创建）、人工（解决）
- **从哪里读：** ProjectStateRepository
- **何时广播：** 创建和解决时通过 EventBus → WebSocket

## ExecutionRun

- **主键：** `run_id` (string, e.g. "run-001")
- **状态：** running → completed / failed
- **谁能改：** ProjectManager
- **从哪里读：** ProjectStateRepository
- **何时广播：** 创建和结束时通过 EventBus → WebSocket
```

- [ ] **步骤 2：Commit**

```bash
git add docs/state-model.md
git commit -m "docs: add unified state model defining all entity lifecycles and ownership"
```

### 任务 3.2：扩展 ProjectStateRepository

**文件：**
- 修改：`dashboard/models.py`
- 修改：`dashboard/state_repository.py`

- [ ] **步骤 1：在 models.py 中扩展数据模型**

读取当前 `dashboard/models.py`，确认已有的模型定义。新增 Task、BlockingIssue、ExecutionRun 的 dataclass 定义：

```python
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class BlockingIssueType(str, Enum):
    MISSING_ENV = "missing_env"
    MISSING_CREDENTIALS = "missing_credentials"
    EXTERNAL_SERVICE_DOWN = "external_service_down"
    DEPENDENCY_NOT_MET = "dependency_not_met"
    CODE_ERROR = "code_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"

class BlockingStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"

class ExecutionRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Task:
    task_id: str
    feature_id: str
    title: str
    owner_role: str
    status: TaskStatus = TaskStatus.PENDING
    blocking_reason: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        data["status"] = TaskStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class BlockingIssue:
    blocking_id: str
    related_feature_id: str
    related_task_id: Optional[str] = None
    type: str = ""
    title: str = ""
    details: str = ""
    required_human_action: str = ""
    status: BlockingStatus = BlockingStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BlockingIssue":
        data["status"] = BlockingStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

@dataclass
class ExecutionRun:
    run_id: str
    feature_id: str
    status: ExecutionRunStatus = ExecutionRunStatus.RUNNING
    agent_id: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionRun":
        data["status"] = ExecutionRunStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
```

- [ ] **步骤 2：在 state_repository.py 中新增 Task / BlockingIssue / ExecutionRun 接口**

读取当前 `dashboard/state_repository.py`，在现有方法基础上新增：

```python
# 在 ProjectStateRepository 类中新增

def save_task(self, task: "Task") -> None:
    """保存或更新 Task"""
    task.updated_at = datetime.now().isoformat()
    self._data.setdefault("tasks", {})
    self._data["tasks"][task.task_id] = task.to_dict()
    self._save()

def get_task(self, task_id: str) -> Optional["Task"]:
    """获取单个 Task"""
    tasks = self._data.get("tasks", {})
    if task_id in tasks:
        return Task.from_dict(tasks[task_id])
    return None

def get_tasks_by_feature(self, feature_id: str) -> list["Task"]:
    """获取 Feature 下所有 Task"""
    tasks = self._data.get("tasks", {})
    return [Task.from_dict(t) for t in tasks.values() if t.get("feature_id") == feature_id]

def get_all_tasks(self) -> list["Task"]:
    """获取所有 Task"""
    tasks = self._data.get("tasks", {})
    return [Task.from_dict(t) for t in tasks.values()]

def save_blocking_issue(self, issue: "BlockingIssue") -> None:
    """保存或更新 BlockingIssue"""
    self._data.setdefault("blocking_issues", {})
    self._data["blocking_issues"][issue.blocking_id] = issue.to_dict()
    self._save()

def get_blocking_issue(self, blocking_id: str) -> Optional["BlockingIssue"]:
    """获取单个 BlockingIssue"""
    issues = self._data.get("blocking_issues", {})
    if blocking_id in issues:
        return BlockingIssue.from_dict(issues[blocking_id])
    return None

def get_open_blocking_issues(self) -> list["BlockingIssue"]:
    """获取所有未解决的阻塞项"""
    issues = self._data.get("blocking_issues", {})
    return [BlockingIssue.from_dict(i) for i in issues.values() if i.get("status") == "open"]

def save_execution_run(self, run: "ExecutionRun") -> None:
    """保存或更新 ExecutionRun"""
    self._data.setdefault("execution_runs", {})
    self._data["execution_runs"][run.run_id] = run.to_dict()
    self._save()

def get_execution_run(self, run_id: str) -> Optional["ExecutionRun"]:
    """获取单个 ExecutionRun"""
    runs = self._data.get("execution_runs", {})
    if run_id in runs:
        return ExecutionRun.from_dict(runs[run_id])
    return None

def get_current_run(self) -> Optional["ExecutionRun"]:
    """获取当前运行中的 ExecutionRun"""
    runs = self._data.get("execution_runs", {})
    for run_data in runs.values():
        if run_data.get("status") == "running":
            return ExecutionRun.from_dict(run_data)
    return None

def get_snapshot(self) -> dict:
    """返回完整状态快照"""
    return {
        "features": self._data.get("features", {}),
        "tasks": self._data.get("tasks", {}),
        "agents": self._data.get("agents", {}),
        "events": self._data.get("events", []),
        "commands": self._data.get("commands", {}),
        "blocking_issues": self._data.get("blocking_issues", {}),
        "execution_runs": self._data.get("execution_runs", {}),
        "chat_history": self._data.get("chat_history", []),
        "module_assignments": self._data.get("module_assignments", {}),
    }
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard/models.py dashboard/state_repository.py
git commit -m "feat: extend Repository with Task, BlockingIssue, ExecutionRun models and APIs"
```

### 任务 3.3：新增状态查询 API

**文件：**
- 创建：`dashboard/api/routes/state.py`
- 修改：`dashboard/api/server.py`（或对应的路由注册文件）

- [ ] **步骤 1：创建状态查询路由**

```python
from fastapi import APIRouter
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import Task, BlockingIssue, ExecutionRun

router = APIRouter(prefix="/api/state", tags=["state"])
repository = ProjectStateRepository()

@router.get("/snapshot")
async def get_snapshot():
    """返回完整当前快照"""
    return repository.get_snapshot()

@router.get("/tasks")
async def get_tasks():
    """返回 task 列表"""
    tasks = repository.get_all_tasks()
    return {"items": [t.to_dict() for t in tasks], "total": len(tasks)}

@router.get("/blocking-issues")
async def get_blocking_issues():
    """返回阻塞项"""
    issues = repository.get_open_blocking_issues()
    return {"items": [i.to_dict() for i in issues], "total": len(issues)}

@router.get("/runs/current")
async def get_current_run():
    """返回当前执行轮次"""
    run = repository.get_current_run()
    if run:
        return {"item": run.to_dict()}
    return {"item": None}
```

- [ ] **步骤 2：注册路由**

在 `dashboard/api/server.py`（或 FastAPI app 创建处）添加：

```python
from dashboard.api.routes.state import router as state_router

app.include_router(state_router)
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard/api/routes/state.py dashboard/api/server.py
git commit -m "feat: add state query API endpoints for snapshot, tasks, blocking, runs"
```

### 任务 3.4：编写状态迁移脚本

**文件：**
- 创建：`scripts/migrate_state.py`

- [ ] **步骤 1：创建迁移脚本**

```python
#!/usr/bin/env python3
"""
状态迁移脚本：合并旧数据源到统一 Repository

读取旧 features.json、SQLite tasks、dashboard state.json，
合并生成新的统一快照。
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

def migrate_state(data_dir: Path = Path("data")) -> dict:
    """执行迁移并返回报告"""
    report = {
        "started_at": datetime.now().isoformat(),
        "sources_read": [],
        "features_migrated": 0,
        "tasks_migrated": 0,
        "agents_migrated": 0,
        "events_migrated": 0,
        "issues": [],
    }

    merged = {
        "features": {},
        "tasks": {},
        "agents": {},
        "events": [],
        "commands": {},
        "blocking_issues": {},
        "execution_runs": {},
        "chat_history": [],
        "module_assignments": {},
    }

    # 1. 读取 features.json
    features_file = data_dir / "features.json"
    if features_file.exists():
        with open(features_file) as f:
            features = json.load(f)
        if isinstance(features, list):
            for feat in features:
                fid = feat.get("id", feat.get("feature_id", f"feat-{len(merged['features'])}"))
                merged["features"][fid] = feat
                report["features_migrated"] += 1
        else:
            merged["features"] = features
            report["features_migrated"] = len(features)
        report["sources_read"].append("features.json")
    else:
        report["issues"].append("features.json not found")

    # 2. 读取 dashboard state.json
    state_file = data_dir / "dashboard" / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        merged["agents"] = state.get("agents", {})
        merged["events"] = state.get("events", [])
        merged["commands"] = state.get("commands", {})
        merged["chat_history"] = state.get("chat_history", [])
        merged["module_assignments"] = state.get("module_assignments", {})
        merged["blocking_issues"] = state.get("blocking_issues", {})
        merged["execution_runs"] = state.get("execution_runs", {})
        report["agents_migrated"] = len(merged["agents"])
        report["events_migrated"] = len(merged["events"])
        report["sources_read"].append("state.json")
    else:
        report["issues"].append("state.json not found")

    # 3. 输出迁移报告
    report["completed_at"] = datetime.now().isoformat()
    report["merged_data"] = merged

    return report

def main():
    print("开始状态迁移...")
    report = migrate_state()
    
    print(f"\n迁移报告:")
    print(f"  数据源读取: {', '.join(report['sources_read'])}")
    print(f"  Feature 迁移: {report['features_migrated']}")
    print(f"  Agent 迁移: {report['agents_migrated']}")
    print(f"  Event 迁移: {report['events_migrated']}")
    
    if report["issues"]:
        print(f"\n警告:")
        for issue in report["issues"]:
            print(f"  - {issue}")
    
    # 保存合并结果
    output = Path("data/dashboard/state.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(report["merged_data"], f, indent=2, ensure_ascii=False)
    
    print(f"\n迁移完成。结果已保存到 {output}")

if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：Commit**

```bash
git add scripts/migrate_state.py
git commit -m "feat: add state migration script to consolidate legacy data sources"
```

### 任务 3.5：编写状态一致性测试

**文件：**
- 创建：`tests/test_state_model.py`
- 创建：`tests/test_state_migration.py`
- 创建：`tests/test_snapshot_api.py`

- [ ] **步骤 1：编写状态模型测试**

```python
import pytest
from dashboard.models import Task, TaskStatus, BlockingIssue, BlockingStatus, ExecutionRun, ExecutionRunStatus

class TestTask:
    def test_create_task(self):
        task = Task(task_id="T-001", feature_id="F-001", title="test", owner_role="backend")
        assert task.status == TaskStatus.PENDING
        assert task.task_id == "T-001"

    def test_task_to_dict(self):
        task = Task(task_id="T-001", feature_id="F-001", title="test", owner_role="backend")
        d = task.to_dict()
        assert d["task_id"] == "T-001"
        assert d["status"] == TaskStatus.PENDING

    def test_task_from_dict(self):
        data = {"task_id": "T-002", "feature_id": "F-001", "title": "test2", "owner_role": "frontend", "status": "running", "blocking_reason": "", "error": "", "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}
        task = Task.from_dict(data)
        assert task.status == TaskStatus.RUNNING

class TestBlockingIssue:
    def test_create_issue(self):
        issue = BlockingIssue(blocking_id="BLK-001", related_feature_id="F-001", type="missing_env", title="No env")
        assert issue.status == BlockingStatus.OPEN

    def test_issue_to_dict(self):
        issue = BlockingIssue(blocking_id="BLK-001", related_feature_id="F-001", type="missing_env", title="No env")
        d = issue.to_dict()
        assert d["blocking_id"] == "BLK-001"
        assert d["status"] == BlockingStatus.OPEN

class TestExecutionRun:
    def test_create_run(self):
        run = ExecutionRun(run_id="run-001", feature_id="F-001")
        assert run.status == ExecutionRunStatus.RUNNING

    def test_run_to_dict(self):
        run = ExecutionRun(run_id="run-001", feature_id="F-001")
        d = run.to_dict()
        assert d["run_id"] == "run-001"
```

- [ ] **步骤 2：编写迁移测试**

```python
import pytest
import json
from pathlib import Path
from unittest.mock import patch
from scripts.migrate_state import migrate_state

class TestStateMigration:
    def test_migrate_with_features_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        features = [{"id": "F-001", "title": "Test Feature", "status": "pending"}]
        with open(data_dir / "features.json", "w") as f:
            json.dump(features, f)

        report = migrate_state(data_dir)
        assert report["features_migrated"] == 1
        assert "features.json" in report["sources_read"]

    def test_migrate_with_state_file(self, tmp_path):
        data_dir = tmp_path / "data"
        (data_dir / "dashboard").mkdir(parents=True)
        state = {
            "agents": {"agent-1": {"role": "pm", "status": "idle"}},
            "events": [{"type": "started"}],
            "commands": {},
            "chat_history": [],
            "module_assignments": {},
            "blocking_issues": {},
            "execution_runs": {},
        }
        with open(data_dir / "dashboard" / "state.json", "w") as f:
            json.dump(state, f)

        report = migrate_state(data_dir)
        assert report["agents_migrated"] == 1
        assert report["events_migrated"] == 1

    def test_migrate_missing_files(self, tmp_path):
        report = migrate_state(tmp_path / "data")
        assert "features.json not found" in report["issues"]
        assert "state.json not found" in report["issues"]
```

- [ ] **步骤 3：编写快照 API 测试**

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

class TestSnapshotAPI:
    @pytest.fixture
    def client(self):
        # 需要在测试环境中启动 FastAPI app
        from dashboard.api.server import app
        return TestClient(app)

    def test_get_snapshot_returns_structure(self, client):
        response = client.get("/api/state/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "tasks" in data
        assert "agents" in data

    def test_get_tasks_returns_list(self, client):
        response = client.get("/api/state/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_get_blocking_issues_returns_list(self, client):
        response = client.get("/api/state/blocking-issues")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_get_current_run(self, client):
        response = client.get("/api/state/runs/current")
        assert response.status_code == 200
        data = response.json()
        assert "item" in data
```

- [ ] **步骤 4：运行测试验证**

```bash
uv run pytest tests/test_state_model.py tests/test_state_migration.py -v
```

预期：所有测试通过

- [ ] **步骤 5：Commit**

```bash
git add tests/test_state_model.py tests/test_state_migration.py tests/test_snapshot_api.py
git commit -m "test: add state model, migration, and snapshot API tests"
```

---

## Phase 4：阻塞处理协议

### 任务 4.1：扩展 BlockingIssue 模型和 Agent 阻塞上报

**文件：**
- 修改：`dashboard/models.py`（已在 Phase 3 完成）
- 修改：`agents/base_agent.py`

- [ ] **步骤 1：确认 models.py 中 BlockingIssue 已定义**（Phase 3 已完成）

- [ ] **步骤 2：让 Agent 可上报阻塞**

读取 `agents/base_agent.py`，找到执行结果返回处，确保支持阻塞返回结构：

```python
# 在 base_agent.py 的执行结果返回结构中增加 blocked 字段
# 如果已有 result dict，确保包含以下字段：

def report_blocked(self, blocking_type: str, message: str, required_action: str) -> dict:
    """上报阻塞状态"""
    return {
        "success": False,
        "blocked": True,
        "blocking_type": blocking_type,
        "blocking_message": message,
        "required_human_action": required_action,
        "agent_role": self.role,
    }
```

- [ ] **步骤 3：Commit**

```bash
git add agents/base_agent.py
git commit -m "feat: add blocked reporting method to base agent"
```

### 任务 4.2：阻塞项写入 Repository 和 WebSocket 广播

**文件：**
- 修改：`dashboard/state_repository.py`（已在 Phase 3 完成）
- 修改：`dashboard/coordinator.py` 或 `dashboard/event_bus.py`

- [ ] **步骤 1：在事件总线中新增阻塞事件广播**

读取 `dashboard/event_bus.py`，确认事件广播机制。确保阻塞创建时广播：

```python
# 在适当的业务逻辑位置（如 coordinator 处理 agent 结果时）
# 当检测到 agent 返回 blocked 时：

async def broadcast_blocking_issue(self, issue: BlockingIssue):
    """广播阻塞事件到 WebSocket"""
    event = {
        "type": "blocking_created",
        "data": issue.to_dict(),
        "timestamp": datetime.now().isoformat(),
    }
    await self.event_bus.broadcast(event)
```

- [ ] **步骤 2：Commit**

```bash
git add dashboard/coordinator.py
git commit -m "feat: broadcast blocking issues via event bus to WebSocket clients"
```

### 任务 4.3：CLI 阻塞查看和解除命令

**文件：**
- 修改：`cli.py`

- [ ] **步骤 1：新增 unblock 命令**

```python
@app.command()
def unblock(blocking_id: str):
    """解除指定的阻塞项"""
    from pathlib import Path
    import json
    from datetime import datetime

    state_file = Path("data/dashboard/state.json")
    if not state_file.exists():
        print("状态文件不存在。")
        return

    with open(state_file) as f:
        state = json.load(f)

    issues = state.get("blocking_issues", {})
    if blocking_id not in issues:
        print(f"阻塞项 {blocking_id} 不存在。")
        return

    issue = issues[blocking_id]
    if issue.get("status") == "resolved":
        print(f"阻塞项 {blocking_id} 已经是已解决状态。")
        return

    issue["status"] = "resolved"
    issue["resolved_at"] = datetime.now().isoformat()

    with open(state_file, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"✓ 阻塞项 {blocking_id} 已解除: {issue.get('title', '')}")
    print(f"  相关 Feature: {issue.get('related_feature_id', '')}")
```

- [ ] **步骤 2：Commit**

```bash
git add cli.py
git commit -m "feat: add CLI unblock command to resolve blocking issues"
```

---

## Phase 5：前端状态治理

### 任务 5.1：引入 React Query 层

**文件：**
- 创建：`dashboard-ui/lib/query-client.ts`
- 创建：`dashboard-ui/lib/query-keys.ts`
- 创建：`dashboard-ui/lib/hooks/use-features.ts`
- 创建：`dashboard-ui/lib/hooks/use-agents.ts`
- 创建：`dashboard-ui/lib/hooks/use-blocking-issues.ts`

- [ ] **步骤 1：安装 React Query**

```bash
cd dashboard-ui
npm install @tanstack/react-query
```

- [ ] **步骤 2：创建 QueryClient 实例**

```typescript
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30, // 30s 内数据视为新鲜
      gcTime: 1000 * 60 * 5, // 5 分钟后回收缓存
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})
```

- [ ] **步骤 3：定义 Query Keys**

```typescript
export const queryKeys = {
  features: {
    all: ['features'] as const,
    detail: (id: string) => ['features', id] as const,
  },
  agents: {
    all: ['agents'] as const,
    detail: (id: string) => ['agents', id] as const,
  },
  blockingIssues: {
    all: ['blocking-issues'] as const,
    open: ['blocking-issues', 'open'] as const,
  },
  executionRuns: {
    all: ['execution-runs'] as const,
    current: ['execution-runs', 'current'] as const,
  },
  snapshot: {
    all: ['snapshot'] as const,
  },
} as const
```

- [ ] **步骤 4：创建 Feature Hooks**

```typescript
import { useQuery } from '@tanstack/react-query'
import { queryKeys } from './query-keys'
import { api } from '../api'
import type { Feature } from '../types'

export function useFeatures() {
  return useQuery({
    queryKey: queryKeys.features.all,
    queryFn: () => api.getFeatures(),
  })
}

export function useFeature(id: string) {
  return useQuery({
    queryKey: queryKeys.features.detail(id),
    queryFn: () => api.getFeature(id),
    enabled: !!id,
  })
}
```

- [ ] **步骤 5：创建 Agent Hooks**

```typescript
import { useQuery } from '@tanstack/react-query'
import { queryKeys } from './query-keys'
import { api } from '../api'

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents.all,
    queryFn: () => api.getAgents(),
  })
}
```

- [ ] **步骤 6：创建 Blocking Issues Hooks**

```typescript
import { useQuery } from '@tanstack/react-query'
import { queryKeys } from './query-keys'
import { api } from '../api'

export function useBlockingIssues() {
  return useQuery({
    queryKey: queryKeys.blockingIssues.open,
    queryFn: () => api.getBlockingIssues(),
  })
}
```

- [ ] **步骤 7：在 App 中包裹 QueryClientProvider**

读取 `dashboard-ui/app/layout.tsx` 或 `dashboard-ui/pages/_app.tsx`（取决于 Next.js 版本），添加 Provider：

```typescript
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '../lib/query-client'

// 在 App 组件中包裹
<QueryClientProvider client={queryClient}>
  {children}
</QueryClientProvider>
```

- [ ] **步骤 8：Commit**

```bash
git add dashboard-ui/lib/query-client.ts dashboard-ui/lib/query-keys.ts dashboard-ui/lib/hooks/
git commit -m "feat: introduce React Query layer for server state management"
```

### 任务 5.2：重构 API 层

**文件：**
- 修改：`dashboard-ui/lib/api.ts`

- [ ] **步骤 1：统一 API 返回结构**

读取当前 `dashboard-ui/lib/api.ts`，改造为 Query 友好的 fetcher 层：

```typescript
// 统一响应结构
interface ApiResponse<T> {
  items?: T[]
  item?: T
  total?: number
}

// 列表接口统一返回 { items, total? }
export async function getFeatures(): Promise<Feature[]> {
  const res = await fetch('/api/features')
  if (!res.ok) throw new Error('Failed to fetch features')
  const data = await res.json()
  // 兼容两种返回格式
  return data.items || data.features || data
}

export async function getAgents(): Promise<Agent[]> {
  const res = await fetch('/api/agents')
  if (!res.ok) throw new Error('Failed to fetch agents')
  const data = await res.json()
  return data.items || data.agents || data
}

export async function getBlockingIssues(): Promise<BlockingIssue[]> {
  const res = await fetch('/api/state/blocking-issues')
  if (!res.ok) throw new Error('Failed to fetch blocking issues')
  const data = await res.json()
  return data.items || []
}

export async function getSnapshot(): Promise<Snapshot> {
  const res = await fetch('/api/state/snapshot')
  if (!res.ok) throw new Error('Failed to fetch snapshot')
  return res.json()
}

// 命令执行接口统一返回 { command }
export async function executeCommand(command: CommandRequest): Promise<{ command: Command }> {
  const res = await fetch('/api/commands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
  })
  if (!res.ok) throw new Error('Failed to execute command')
  return res.json()
}
```

- [ ] **步骤 2：Commit**

```bash
git add dashboard-ui/lib/api.ts
git commit -m "refactor: unify API response format for Query compatibility"
```

### 任务 5.3：收缩 Zustand 职责

**文件：**
- 修改：`dashboard-ui/lib/store.ts`

- [ ] **步骤 1：重构 store，只保留 UI 状态**

读取当前 `dashboard-ui/lib/store.ts`，移除服务端数据（features/agents/events），只保留：

```typescript
import { create } from 'zustand'

interface UISlice {
  selectedFeature: string | null
  selectedAgent: string | null
  drawerOpen: boolean
  filterStatus: string | null
  setSelectedFeature: (id: string | null) => void
  setSelectedAgent: (id: string | null) => void
  setDrawerOpen: (open: boolean) => void
  setFilterStatus: (status: string | null) => void
}

export const useStore = create<UISlice>((set) => ({
  selectedFeature: null,
  selectedAgent: null,
  drawerOpen: false,
  filterStatus: null,
  setSelectedFeature: (id) => set({ selectedFeature: id }),
  setSelectedAgent: (id) => set({ selectedAgent: id }),
  setDrawerOpen: (open) => set({ drawerOpen: open }),
  setFilterStatus: (status) => set({ filterStatus: status }),
}))
```

- [ ] **步骤 2：更新组件引用**

搜索所有使用 store 中 features/agents/events 的组件，改为使用对应的 useFeatures/useAgents hooks：

```bash
# 查找需要更新的位置
grep -r "useStore.*features\|useStore.*agents\|useStore.*events" dashboard-ui/
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard-ui/lib/store.ts
git commit -m "refactor: shrink Zustand to UI-only state, move server data to React Query"
```

### 任务 5.4：WebSocket 改为增量更新

**文件：**
- 修改：`dashboard-ui/lib/websocket.ts`

- [ ] **步骤 1：WebSocket 收到事件后 invalidate Query**

```typescript
import { queryClient } from './query-client'
import { queryKeys } from './query-keys'

export function setupWebSocket() {
  const ws = new WebSocket(`ws://${window.location.host}/ws`)

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)

    // 根据事件类型 invalidate 对应的 query
    switch (data.type) {
      case 'feature_updated':
        queryClient.invalidateQueries({ queryKey: queryKeys.features.all })
        break
      case 'agent_updated':
        queryClient.invalidateQueries({ queryKey: queryKeys.agents.all })
        break
      case 'blocking_created':
      case 'blocking_resolved':
        queryClient.invalidateQueries({ queryKey: queryKeys.blockingIssues.open })
        break
      default:
        // 其他事件 invalidate 完整快照
        queryClient.invalidateQueries({ queryKey: queryKeys.snapshot.all })
    }
  }

  return ws
}
```

- [ ] **步骤 2：Commit**

```bash
git add dashboard-ui/lib/websocket.ts
git commit -m "refactor: WebSocket triggers query invalidation instead of storing state"
```

---

## Phase 6：统一操作入口

### 任务 6.1：创建顶层 Makefile

**文件：**
- 创建：`Makefile`

- [ ] **步骤 1：创建 Makefile**

```makefile
.PHONY: setup test test-backend test-frontend lint build-ui run-dashboard run-cli status clean-state doctor

setup:
	@echo "Setting up project..."
	uv sync
	cd dashboard-ui && npm install
	cd dashboard-ui && npx playwright install

test: test-backend test-frontend

test-backend:
	uv run pytest tests/ -v

test-frontend:
	cd dashboard-ui && npm run test

lint:
	uv run ruff check .
	cd dashboard-ui && npm run lint

build-ui:
	cd dashboard-ui && npm run build

run-dashboard:
	uv run python start_dashboard.py

run-cli:
	@echo "Usage: uv run python cli.py <command>"
	uv run python cli.py --help

status:
	uv run python cli.py status

clean-state:
	@echo "Cleaning project state..."
	rm -rf data/features.json data/dashboard/state.json data/execution-plan.json claude-progress.txt
	@echo "State cleaned."

doctor:
	uv run python scripts/doctor.py
```

- [ ] **步骤 2：Commit**

```bash
git add Makefile
git commit -m "feat: add top-level Makefile for standardized project operations"
```

### 任务 6.2：创建诊断脚本

**文件：**
- 创建：`scripts/doctor.py`

- [ ] **步骤 1：创建诊断脚本**

```python
#!/usr/bin/env python3
"""
项目诊断脚本：检查运行环境和依赖
"""

import sys
import shutil
import subprocess
from pathlib import Path

def check_python():
    """检查 Python 版本"""
    print(f"Python: {sys.version.split()[0]} ✓")

def check_uv():
    """检查 uv 是否安装"""
    if shutil.which("uv"):
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        print(f"uv: {result.stdout.strip()} ✓")
    else:
        print("uv: 未安装 ✗")

def check_dependencies():
    """检查 Python 依赖"""
    try:
        import fastapi
        import pydantic
        print(f"fastapi: {fastapi.__version__} ✓")
        print(f"pydantic: {pydantic.__version__} ✓")
    except ImportError as e:
        print(f"Python 依赖缺失: {e} ✗")

def check_node():
    """检查 Node.js 是否安装"""
    if shutil.which("node"):
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        print(f"Node: {result.stdout.strip()} ✓")
    else:
        print("Node: 未安装 ✗")

def check_npm_deps():
    """检查前端依赖"""
    node_modules = Path("dashboard-ui/node_modules")
    if node_modules.exists():
        print("dashboard-ui node_modules: 存在 ✓")
    else:
        print("dashboard-ui node_modules: 不存在，运行 cd dashboard-ui && npm install ✗")

def check_data_dirs():
    """检查数据目录"""
    dirs = [Path("data"), Path("data/dashboard")]
    for d in dirs:
        if d.exists():
            print(f"Directory {d}: 存在 ✓")
        else:
            print(f"Directory {d}: 不存在 ✗")

def check_claude_cli():
    """检查 Claude CLI 是否可用"""
    if shutil.which("claude"):
        print("Claude CLI: 可用 ✓")
    else:
        print("Claude CLI: 不可用 ✗")

def check_playwright():
    """检查 Playwright 是否可用"""
    try:
        import playwright
        print("Playwright: 可用 ✓")
    except ImportError:
        print("Playwright: 不可用 ✗")

def check_state_files():
    """检查状态文件是否损坏"""
    state_files = [
        Path("data/features.json"),
        Path("data/dashboard/state.json"),
    ]
    import json
    for f in state_files:
        if f.exists():
            try:
                with open(f) as fh:
                    json.load(fh)
                print(f"State file {f}: 有效 ✓")
            except json.JSONDecodeError:
                print(f"State file {f}: 损坏 ✗")
        else:
            print(f"State file {f}: 不存在 (正常，如果项目未初始化)")

def main():
    print("=== Auto-Coding 项目诊断 ===\n")

    check_python()
    check_uv()
    print()

    check_dependencies()
    print()

    check_node()
    check_npm_deps()
    print()

    check_claude_cli()
    check_playwright()
    print()

    check_data_dirs()
    check_state_files()

    print("\n=== 诊断完成 ===")

if __name__ == "__main__":
    main()
```

- [ ] **步骤 2：Commit**

```bash
git add scripts/doctor.py
git commit -m "feat: add doctor script for environment and dependency diagnostics"
```

### 任务 6.3：CLI 新增 doctor 和 reset 命令

**文件：**
- 修改：`cli.py`

- [ ] **步骤 1：新增 doctor 命令**

```python
@app.command()
def doctor():
    """运行项目诊断检查"""
    import subprocess
    result = subprocess.run(["uv", "run", "python", "scripts/doctor.py"])
    raise SystemExit(result.returncode)
```

- [ ] **步骤 2：新增 reset-project-state 命令**

```python
@app.command()
def reset_project_state():
    """重置项目状态（清除所有运行数据）"""
    import shutil
    from pathlib import Path

    confirm = input("⚠ 这将清除所有项目运行数据（features、状态、进度）。确定继续？(y/N): ")
    if confirm.lower() != "y":
        print("已取消。")
        return

    files_to_remove = [
        Path("data/features.json"),
        Path("data/dashboard/state.json"),
        Path("data/execution-plan.json"),
        Path("claude-progress.txt"),
    ]

    for f in files_to_remove:
        if f.exists():
            f.unlink()
            print(f"已删除: {f}")

    print("✓ 项目状态已重置。")
```

- [ ] **步骤 3：Commit**

```bash
git add cli.py
git commit -m "feat: add CLI doctor and reset-project-state commands"
```

---

## Phase 7：任务账本与观测面

### 任务 7.1：ExecutionLedger 已在 core/ 存在，新增 API 端点

**文件：**
- 创建：`dashboard/api/routes/ledger.py`
- 修改：`dashboard/api/server.py`

- [ ] **步骤 1：确认 core/execution_ledger.py 已存在**（从之前 session 已完成）

- [ ] **步骤 2：创建 ledger API 路由**

```python
from fastapi import APIRouter
from dashboard.state_repository import ProjectStateRepository

router = APIRouter(prefix="/api/execution-ledger", tags=["ledger"])
repository = ProjectStateRepository()

@router.get("")
async def get_ledger():
    """返回完整执行账本"""
    snapshot = repository.get_snapshot()

    # 组织为账本格式
    ledger = {
        "current_run": snapshot.get("execution_runs", {}),
        "features": snapshot.get("features", {}),
        "tasks": snapshot.get("tasks", {}),
        "blocking_issues": snapshot.get("blocking_issues", {}),
    }

    return ledger
```

- [ ] **步骤 3：注册路由**

```python
from dashboard.api.routes.ledger import router as ledger_router

app.include_router(ledger_router)
```

- [ ] **步骤 4：Commit**

```bash
git add dashboard/api/routes/ledger.py dashboard/api/server.py
git commit -m "feat: add execution ledger API endpoint"
```

### 任务 7.2：前端新增执行账本面板组件

**文件：**
- 创建：`dashboard-ui/components/ExecutionLedgerPanel.tsx`

- [ ] **步骤 1：创建账本面板组件**

```typescript
'use client'

import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../lib/query-keys'

interface LedgerTask {
  task_id: string
  feature_id: string
  title: string
  owner_role: string
  status: string
  blocking_reason: string
  updated_at: string
}

interface LedgerFeature {
  id: string
  title: string
  status: string
}

export function ExecutionLedgerPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['ledger'],
    queryFn: () => fetch('/api/execution-ledger').then(r => r.json()),
  })

  if (isLoading) return <div className="p-4">加载中...</div>
  if (!data) return <div className="p-4">无数据</div>

  const tasks: LedgerTask[] = Object.values(data.tasks || {})
  const features: LedgerFeature[] = Object.values(data.features || {})

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">执行账本</h2>

      {/* 过滤条件 */}
      <div className="flex gap-2 mb-4">
        <select className="border rounded px-2 py-1">
          <option value="">所有 Agent</option>
          {[...new Set(tasks.map(t => t.owner_role))].map(role => (
            <option key={role} value={role}>{role}</option>
          ))}
        </select>
        <select className="border rounded px-2 py-1">
          <option value="">所有状态</option>
          <option value="pending">pending</option>
          <option value="running">running</option>
          <option value="completed">completed</option>
          <option value="blocked">blocked</option>
        </select>
      </div>

      {/* 账本表格 */}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left py-2">Feature</th>
            <th className="text-left py-2">状态</th>
            <th className="text-left py-2">Task</th>
            <th className="text-left py-2">Agent</th>
            <th className="text-left py-2">阻塞</th>
            <th className="text-left py-2">更新时间</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(task => (
            <tr key={task.task_id} className="border-b hover:bg-gray-50">
              <td className="py-2">
                {features.find(f => f.id === task.feature_id)?.title || task.feature_id}
              </td>
              <td className="py-2">
                <StatusBadge status={task.status} />
              </td>
              <td className="py-2">{task.title}</td>
              <td className="py-2">{task.owner_role}</td>
              <td className="py-2">
                {task.blocking_reason ? (
                  <span className="text-red-600">⚠ {task.blocking_reason}</span>
                ) : (
                  <span className="text-green-600">—</span>
                )}
              </td>
              <td className="py-2 text-gray-500">{task.updated_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: 'bg-gray-200 text-gray-700',
    running: 'bg-blue-200 text-blue-700',
    completed: 'bg-green-200 text-green-700',
    failed: 'bg-red-200 text-red-700',
    blocked: 'bg-yellow-200 text-yellow-700',
  }

  return (
    <span className={`px-2 py-1 rounded text-xs ${colors[status] || 'bg-gray-200'}`}>
      {status}
    </span>
  )
}
```

- [ ] **步骤 2：Commit**

```bash
git add dashboard-ui/components/ExecutionLedgerPanel.tsx
git commit -m "feat: add execution ledger panel with filtering and status display"
```

---

## Phase 8：PM / Coordinator 拆职责

### 任务 8.1：确认已有服务文件

**文件：**
- 已存在：`core/feature_execution_service.py`
- 已存在：`core/feature_verification_service.py`
- 已存在：`core/git_service.py`

- [ ] **步骤 1：确认文件已存在**

从之前的 session 中，这三个服务文件已经创建。确认它们的内容和职责是否清晰。

### 任务 8.2：让 ProjectManager 只负责编排

**文件：**
- 修改：`core/project_manager.py`

- [ ] **步骤 1：重构 ProjectManager，委托给服务层**

读取当前 `core/project_manager.py`（21749 字节，较大型），识别可以直接委托给已有服务的代码段：

- Feature 执行 → 委托给 `FeatureExecutionService`
- Feature 验收 → 委托给 `FeatureVerificationService`
- Git 操作 → 委托给 `GitService`

在 ProjectManager 中，将原来直接执行这些操作的代码替换为服务调用：

```python
from core.feature_execution_service import FeatureExecutionService
from core.feature_verification_service import FeatureVerificationService
from core.git_service import GitService

class ProjectManager:
    def __init__(self, ...):
        # ... 原有初始化
        self.feature_execution = FeatureExecutionService(...)
        self.feature_verification = FeatureVerificationService(...)
        self.git = GitService(...)

    async def execute_feature(self, feature_id: str) -> dict:
        """执行单个 Feature - 现在只负责编排"""
        # 原来这里直接调用 agent、写状态、commit
        # 现在委托给服务
        result = await self.feature_execution.execute(feature_id)
        if result["success"]:
            verification = self.feature_verification.verify(feature_id)
            if verification["passed"]:
                self.git.commit_changes(f"feat: complete {feature_id}")
                return {"status": "completed"}
        return result
```

- [ ] **步骤 2：运行测试验证重构未破坏功能**

```bash
uv run pytest tests/test_project_manager.py tests/test_feature_execution_service.py tests/test_feature_verification_service.py -v
```

- [ ] **步骤 3：Commit**

```bash
git add core/project_manager.py
git commit -m "refactor: thin out ProjectManager by delegating to service layer"
```

---

## 全量验收

### 任务 9.1：运行全量测试

- [ ] **步骤 1：运行所有测试**

```bash
uv run pytest tests/ -v --tb=short
```

- [ ] **步骤 2：运行前端构建**

```bash
cd dashboard-ui && npm run build
```

- [ ] **步骤 3：运行 doctor**

```bash
make doctor
```

- [ ] **步骤 4：确认所有阶段交付清单**

| 阶段 | 文档 | 代码 | 测试 |
|------|------|------|------|
| Phase 0 | ✅ baseline 文档 | ✅ | ✅ 基线记录 |
| Phase 1 | ✅ ARCHITECTURE.md | ✅ | ✅ 文档评审 |
| Phase 2 | ✅ WORKFLOW.md | ✅ CLI 命令 | ✅ CLI 测试 |
| Phase 3 | ✅ state-model.md | ✅ Repository 重构 | ✅ 状态模型与 API 测试 |
| Phase 4 | ✅ 阻塞协议（在 WORKFLOW.md） | ✅ BlockingIssue | ✅ 阻塞流测试 |
| Phase 5 | ✅ 前端状态约定 | ✅ Query 层 | ✅ hooks 测试 |
| Phase 6 | ✅ Makefile | ✅ doctor 脚本 | ✅ 脚本测试 |
| Phase 7 | ✅ 账本说明 | ✅ ledger API/UI | ✅ ledger 测试 |
| Phase 8 | ✅ 架构更新 | ✅ 服务拆分 | ✅ 服务层测试 |

---

## 执行顺序说明

严格按以下顺序执行，不要跳着做：

1. Phase 0 → Phase 1 → Phase 3 → Phase 2 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8

原因：
- Phase 1 先定义边界，否则后面会反复返工
- Phase 3 先统一状态源，否则前后端改造没有稳定基础
- Phase 2 和 Phase 4 让工作流和阻塞规则变得显式
- Phase 5/7 再做 UI 和观测面，才不会反复改接口
- Phase 8 最后拆服务，风险最小
