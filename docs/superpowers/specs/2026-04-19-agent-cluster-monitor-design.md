# 实时 Agent 集群监控与执行控制 — 设计规格

> **版本:** v2.1 | **日期:** 2026-04-19 | **状态:** 待审批

## 1. 目标

将现有的 `ExecutionControl` 组件升级为完整的 **AgentClusterMonitor**，实现：
1. 实时监控所有 Agent 运行状态和具体活动
2. 点击 Agent 即可查看其完整事件流（tool 调用、输出、错误）
3. 可收起/弹出的聊天窗口，用于 PM 与运行中 Agent 的对话交互
4. 静默检测与阶梯告警（非粗暴超时）
5. 通过对话唤醒、`--continue` 恢复、优雅中断等手段保持上下文

## 2. 架构

### 2.1 后端架构

```
PMCoordinator (Python threading)
  ├── EventBus (发布事件)
  │     ├── agent_status_changed
  │     ├── agent_log
  │     ├── tool_use
  │     ├── tool_result
  │     ├── agent_silence (静默告警)
  │     ├── agent_timeout (超时，需 PM 介入)
  │     ├── resource_usage (CPU/MEM/Tokens)
  │     └── feature_completed / error_occurred
  ├── SilencDetector (监控各 agent 最后事件时间)
  │     ├── 30s → 静默标记 (silence 状态，不告警)
  │     ├── 120s → 通知 PM (agent_log: "XX 已静默 2 分钟")
  │     └── 600s → 强告警 (agent_timeout, 状态变为 waiting_pm)
  └── AgentProcessManager (管理 subprocess 生命周期)
        ├── stdin 管道保持打开（支持消息注入）
        ├── SIGINT 优雅中断（保存会话状态）
        ├── --continue 恢复（读取 JSONL 恢复上下文）
        └── SIGKILL 强制终止（最后手段）
```

### 2.2 前端架构

```
AgentClusterMonitor (主组件，替换 execution-control.tsx)
  ├── AgentListPanel (左侧栏)
  │     ├── 按 role 分组的 Agent 列表
  │     ├── 状态色块 + 当前任务摘要
  │     └── 点击选中 → 右侧事件流自动过滤到该 agent
  ├── ActivityPanel (中间栏)
  │     ├── 显示每个 busy agent 的具体动作
  │     └── 等待状态显示原因
  ├── EventStream (右侧栏)
  │     ├── 默认：选中第一个 busy agent，显示其完整事件流
  │     ├── 未选中：显示所有 agent 的聚合事件流
  │     ├── 点击 agent 切换过滤
  │     └── 自动滚动，支持暂停
  ├── ResourceBar (底部)
  │     └── CPU / MEM / Tokens / 运行时长
  └── ChatDrawer (右侧滑出)
        ├── 默认收起为小圆形按钮（带消息 badge）
        ├── 点击滑出完整聊天面板
        └── 复用现有 ChatWindow 组件
```

### 2.3 数据流

```
[Agent subprocess] ──stdout──→ [Coordinator 解析事件] ──publish──→ [EventBus]
                                                                    │
[SilenceDetector] ──检测最后事件时间──→ publish silence/timeout ────┤
                                                                    │
[WebSocket Handler] ──订阅 EventBus ──→ JSON push ──→ [前端 WebSocket]
                                                                    │
[Zustand Store] ──接收事件──→ 更新 agents[] / events[] / resources  │
                                                                    │
[AgentClusterMonitor] ──读取 store──→ 渲染三栏 UI                    │
                                                                    │
[用户点击 Agent] ──→ store.setSelectedAgent(id) ──→ 事件流重新过滤    │
                                                                    │
[用户发送消息] ──→ POST /api/agents/{id}/message ──→ stdin 写入 ──→ [Agent]
```

## 3. Agent 状态机

```
idle ──start──→ starting ──launched──→ running
                                                  │
                                    ┌─── 30s 无事件 ──→ silence (黄色脉冲)
                                    │                        │
                                    │           ┌── 2min 无事件 ──→ 通知 PM
                                    │           │
                                    │           └── 10min 无事件 ──→ waiting_pm (橙色告警)
                                    │                                     │
                                    │                            PM 决策:
                                    │                            ├── 发送诊断消息 → running
                                    │                            ├── --continue 恢复 → running
                                    │                            └── kill 重启 → starting
                                    │
                                    ├── task done ──→ completed ──→ idle
                                    └── error ──→ error ──→ idle
```

### 状态定义

| 状态 | 颜色 | 含义 |
|------|------|------|
| `idle` | 灰色 | 未分配任务 |
| `starting` | 黄色 | 正在启动进程 |
| `running` | 绿色 | 正常执行中 |
| `silence` | 黄色脉冲 | 超过 30s 无输出，仍在处理中 |
| `waiting_pm` | 橙色 | 超过 10min 静默，需 PM 介入 |
| `waiting_approval` | 橙色脉冲 | 等待代码审查/审批 |
| `completed` | 蓝色 | 任务完成 |
| `error` | 红色 | 执行失败 |

## 4. 事件类型

| 事件类型 | 触发时机 | 前端展示 |
|----------|----------|----------|
| `agent_status_changed` | Agent 状态变更 | 状态色块变化 |
| `agent_log` | Agent 输出文本 | 事件流文本行 |
| `tool_use` | Agent 调用工具 | 🔧 Write file.py |
| `tool_result` | 工具返回 | ✅/❌ 结果摘要 |
| `agent_silence` | 30s/2min 静默 | 黄色标记 |
| `agent_timeout` | 10min 静默 | 橙色告警横幅 |
| `resource_usage` | 定期采集 | 资源栏更新 |
| `feature_completed` | 功能完成 | 绿色标记 |
| `error_occurred` | 执行错误 | 红色标记 |

## 5. Agent 进程管理

### 5.1 启动

```python
process = subprocess.Popen(
    ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "stream-json"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,  # line buffered
)
```

### 5.2 消息注入

```python
def send_message_to_agent(self, agent_id: str, message: str) -> None:
    """向运行中的 agent 发送诊断/恢复消息。"""
    agent = self._agents[agent_id]
    if agent.process and agent.process.stdin and not agent.process.stdin.closed:
        prompt = f"\n--- System Message from PM: {message} ---\n请报告你当前的工作状态，遇到了什么问题，是否需要更多时间？\n"
        agent.process.stdin.write(prompt)
        agent.process.stdin.flush()
```

### 5.3 优雅中断

```python
def graceful_interrupt(self, agent_id: str) -> None:
    """发送 SIGINT，让 Claude Code 优雅退出并保存会话状态。"""
    agent = self._agents[agent_id]
    if agent.process:
        agent.process.send_signal(signal.SIGINT)
        agent.process.wait(timeout=10)
```

### 5.4 恢复执行

```python
def resume_agent(self, agent_id: str, additional_prompt: str = "") -> None:
    """使用 --continue 从上次会话恢复。"""
    # Claude Code 自动读取 ~/.claude/projects/<project-id>/*.jsonl
    process = subprocess.Popen(
        ["claude", "-p", "--dangerously-skip-permissions", "--continue",
         "--output-format", "stream-json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if additional_prompt and process.stdin:
        process.stdin.write(additional_prompt)
        process.stdin.flush()
```

## 6. 前端组件详述

### 6.1 AgentClusterMonitor

替换现有 `execution-control.tsx`。

```tsx
interface AgentClusterMonitorProps {
  // 无外部 props，全部从 Zustand store 读取
}

// 布局：
// ┌─ Header: 标题 + 启停按钮 ───────────────────┐
// ├─ AgentList │ Activity │ EventStream ────────┤
// ├─ ResourceBar ───────────────────────────────┤
// └─────────────────────────────────────────────┘
// 右侧浮动: ChatDrawer toggle button
```

### 6.2 AgentListPanel

```tsx
interface AgentListPanelProps {
  // 从 store 读取 agents
  // onClick: (agentId: string) => void  // 选中/取消选中
}

// 每项显示:
// [role_icon] AgentName  [status_dot] current_task_summary
// 例: [⚙] Backend Dev  [🟢] 写 API: POST /api/projects
// 例: [🧪] QA Tester    [🟡] 运行 pytest tests/test_agents.py
// 例: [👑] PM           [⚪] 等待 PM 指令
```

### 6.3 ActivityPanel

```tsx
interface ActivityPanelProps {
  // 显示 busy/silence/waiting 状态的 agent 的当前活动详情
  // 包括: 当前任务、进度百分比、预计剩余时间（如可估算）
}
```

### 6.4 EventStream（重写现有 log-stream.tsx）

```tsx
interface EventStreamProps {
  // selectedAgentId: string | null  // 从 store 读取
  // 如果 selectedAgentId 存在，仅显示该 agent 的事件
  // 否则显示所有 agent 的聚合事件
  // 自动滚动到底部
}

// 每行显示:
// [HH:MM:SS] [agent_name] [event_icon] event_content
// 例: [10:32:15] [Backend Dev] 🔧 Write backend/api/projects.py
// 例: [10:32:30] [QA Tester] ✅ test_create_project passed
// 例: [10:33:02] [Backend Dev] ⚠️ 静默中... (2m 无输出)
```

### 6.5 ChatDrawer

```tsx
interface ChatDrawerProps {
  // isOpen: boolean
  // onToggle: () => void
  // 复用现有 ChatWindow 组件作为内容
  // 从右侧滑出，宽度 360px
  // 收起时显示浮动按钮，带未读消息 badge
}
```

## 7. REST API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/execution/start` | 启动协调循环（已存在） |
| `POST` | `/api/execution/stop` | 停止协调循环（已存在） |
| `GET` | `/api/execution/status` | 获取执行状态（已存在） |
| `POST` | `/api/agents/{id}/message` | **新增** — 向 agent 发送消息 |
| `GET` | `/api/agents/{id}/last-output` | **新增** — 获取最后输出 |
| `POST` | `/api/agents/{id}/continue` | **新增** — 恢复执行 |
| `POST` | `/api/agents/{id}/kill` | **新增** — 强制终止 |

## 8. 配置项

在 `core/config.py` 中添加：

```python
silence_warning_seconds: int = 120    # 2 分钟，通知 PM
silence_timeout_seconds: int = 600    # 10 分钟，需 PM 介入
resource_poll_interval_seconds: int = 30  # 资源采集间隔
max_concurrent_agents: int = 10       # 最大并发 agent 数
```

## 9. WebSocket 事件格式

```json
{
  "type": "tool_use",
  "event_id": "evt_xxx",
  "timestamp": "2026-04-19T10:32:15Z",
  "payload": {
    "agent_id": "backend-dev-1",
    "agent_role": "backend",
    "tool_name": "Write",
    "tool_input": {"file_path": "backend/api/projects.py"},
    "content": "正在写入文件..."
  }
}
```

## 10. 错误处理

- **Agent 进程意外退出**：自动标记为 `error`，发布 `error_occurred` 事件，等待 PM 决策
- **WebSocket 断连**：前端自动重连，重连后拉取最新状态
- **stdin 写入失败**：agent 可能已退出，标记为 `error`，通知 PM
- **资源耗尽**：CPU/MEM 超过阈值时发布 `resource_usage` 告警事件
