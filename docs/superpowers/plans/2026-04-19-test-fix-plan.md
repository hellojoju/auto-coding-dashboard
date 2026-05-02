# 测试修复计划：196 用例修复 + 前后端 API 契约对齐 + 覆盖率 80%

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 7 大已知问题，对齐前后端 API 契约，修复命令生命周期，补全前端测试，提升覆盖率到 80%+。

**架构：** 当前存在 3 层问题：1) 前后端命令类型不匹配（frontend 发 `pause_run`，backend 消费 `pause`），2) target_id 硬编码为 `'pm'` 导致 PMCoordinator 无法匹配正确命令，3) EventBus.emit 与 WebSocket broadcast_queue 桥接不完整。修复策略：先修后端 API 契约，再修前端 API 客户端和 Store，最后补测试。

**技术栈：** FastAPI, WebSocket, Zustand, Next.js 16.2.4, pytest, Playwright

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `dashboard/api/routes.py` | **修改** | 修复 CMD_TYPE_MAP 补充 pause/resume/retry/skip 映射，修复 on_event 接口签名 |
| `dashboard/consumer.py` | **修改** | 补充 pause_run/resume_run/retry_feature/skip_feature 命令识别 |
| `dashboard-ui/lib/api.ts` | **修改** | 修复硬编码 target_id，修正命令类型，适配嵌套 API 响应 |
| `dashboard-ui/lib/store.ts` | **修改** | 修复 fetchAgents 嵌套结构解析，修复 getAgentEvents 裸数组适配 |
| `dashboard-ui/lib/types.ts` | **修改** | 补充前端 Command 类型枚举常量 |
| `dashboard-ui/components/agent-cluster-monitor.tsx` | **新建** | Agent 集群监控面板（角色分组、静默检测、进程信息、操作按钮） |
| `dashboard-ui/app/page.tsx` | **修改** | 集成 AgentClusterMonitor |
| `dashboard-ui/tests/` | **新建** | 前端单元测试 |

---

## 任务 1：修复后端命令类型映射

**文件：** `dashboard/api/routes.py`

- [ ] **步骤 1：补充 CMD_TYPE_MAP**

当前 CMD_TYPE_MAP 只映射了 approve/reject，缺少 pause/resume/retry/skip：

```python
# 在现有 CMD_TYPE_MAP 后添加:
CMD_TYPE_MAP = {
    'approve_decision': 'approve',
    'reject_decision': 'reject',
    'pause_run': 'pause',
    'resume_run': 'resume',
    'retry_feature': 'retry',
    'skip_feature': 'skip',
}
```

- [ ] **步骤 2：验证语法**

```bash
cd /Users/jieson/auto-coding && python -c "import dashboard.api.routes; print('OK')"
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard/api/routes.py
git commit -m "fix(dashboard): 补充 CMD_TYPE_MAP 映射 pause/resume/retry/skip"
```

---

## 任务 2：修复后端 Consumer 命令识别

**文件：** `dashboard/consumer.py`

- [ ] **步骤 1：补充命令识别**

当前 `_process_command` 只识别 `pause`, `resume`, `retry`, `skip`，不识别前端发来的 `pause_run` 等。需要在命令处理逻辑中添加对原始命令类型的兼容：

```python
# 在 _process_command 的命令识别部分，添加:
command_aliases = {
    'pause': 'pause',
    'pause_run': 'pause',
    'resume': 'resume',
    'resume_run': 'resume',
    'retry': 'retry',
    'retry_feature': 'retry',
    'skip': 'skip',
    'skip_feature': 'skip',
}
normalized = command_aliases.get(cmd_type, cmd_type)
```

然后在后续处理中使用 `normalized` 而非原始 `cmd_type`。

- [ ] **步骤 2：验证语法**

```bash
cd /Users/jieson/auto-coding && python -c "import dashboard.consumer; print('OK')"
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard/consumer.py
git commit -m "fix(dashboard): Consumer 添加命令别名支持兼容前端发送类型"
```

---

## 任务 3：修复前端 API 客户端硬编码 target_id

**文件：** `dashboard-ui/lib/api.ts`

- [ ] **步骤 1：修复 actions 中的硬编码 target_id**

当前所有 actions 硬编码 `target_id: 'pm'`（第 79-97 行）。修改为接受参数：

```typescript
// 修改前:
const actions = {
  approve: (featureId: string) => sendCommand({ type: 'approve_decision', target_id: 'pm', payload: { feature_id: featureId } }),
  // ...
}

// 修改后:
const actions = {
  approve: (featureId: string, targetId?: string) => sendCommand({
    type: 'approve_decision',
    target_id: targetId || featureId,  // 默认用 featureId 作为 target_id
    payload: { feature_id: featureId },
  }),
  reject: (featureId: string, targetId?: string) => sendCommand({
    type: 'reject_decision',
    target_id: targetId || featureId,
    payload: { feature_id: featureId },
  }),
  pause: (agentId: string) => sendCommand({
    type: 'pause_run',
    target_id: agentId,  // 使用 agentId
    payload: { agent_id: agentId },
  }),
  resume: (agentId: string) => sendCommand({
    type: 'resume_run',
    target_id: agentId,
    payload: { agent_id: agentId },
  }),
  retry: (featureId: string) => sendCommand({
    type: 'retry_feature',
    target_id: featureId,
    payload: { feature_id: featureId },
  }),
  skip: (featureId: string) => sendCommand({
    type: 'skip_feature',
    target_id: featureId,
    payload: { feature_id: featureId },
  }),
}
```

- [ ] **步骤 2：修复 listAgents 嵌套结构解析**

当前 `listAgents()` 期望扁平数组但 API 返回嵌套结构。修改：

```typescript
export async function listAgents(projectId: string): Promise<AgentInstance[]> {
  const res = await fetch(`${API_BASE}/agents?project_id=${projectId}`)
  if (!res.ok) throw new Error('Failed to fetch agents')
  const data = await res.json()
  // API 返回 { agents: { backend_dev: [...], qa_tester: [...] }, ... }
  if (data.agents) {
    const nested = data.agents
    const flat: AgentInstance[] = []
    for (const role of Object.keys(nested)) {
      const agents = nested[role]
      if (Array.isArray(agents)) {
        flat.push(...agents.map((a: any) => ({ ...a, role })))
      }
    }
    return flat
  }
  return data.agents || data || []
}
```

- [ ] **步骤 3：修复 getAgentEvents 裸数组适配**

当前期望 `{events: [...]}` 但 `GET /api/events` 返回裸数组：

```typescript
export async function getAgentEvents(projectId: string): Promise<DashboardEvent[]> {
  const res = await fetch(`${API_BASE}/events?project_id=${projectId}`)
  if (!res.ok) return []
  const data = await res.json()
  // /api/events 返回裸数组，/api/dashboard/events 返回 {events: [...]}
  return Array.isArray(data) ? data : data.events || []
}
```

- [ ] **步骤 4：验证构建**

```bash
cd /Users/jieson/auto-coding/dashboard-ui && npx tsc --noEmit
```

- [ ] **步骤 5：Commit**

```bash
git add lib/api.ts
git commit -m "fix(dashboard-ui): 修复硬编码 target_id + 嵌套 API 响应适配"
```

---

## 任务 4：修复前端 Store 数据解析

**文件：** `dashboard-ui/lib/store.ts`

- [ ] **步骤 1：修复 fetchAgents 嵌套解析**

当前直接 cast apiAgents 为 AgentInstance[] 忽略嵌套：

```typescript
// 修改 fetchAgents:
fetchAgents: async () => {
  try {
    const agents = await listAgents(projectId)
    set({ agents })
  } catch (error) {
    console.error('Failed to fetch agents:', error)
  }
}
```

- [ ] **步骤 2：验证构建**

```bash
npx tsc --noEmit
```

- [ ] **步骤 3：Commit**

```bash
git add lib/store.ts
git commit -m "fix(dashboard-ui): Store 修复 fetchAgents 嵌套结构解析"
```

---

## 任务 5：修复 CommandProcessor on_event 接口签名

**文件：** `dashboard/api/routes.py`

- [ ] **步骤 1：修复 on_event 回调签名**

CommandProcessor._emit 调用 `self._on_event(Event(...))` 传入 Event 对象，但 routes.py 定义的 on_event 是 `(event_type: str, **kwargs)`。修复：

```python
# 修改 routes.py 中的 on_event 回调:
def on_event(event: Event) -> None:  # 接受 Event 对象
    """EventBus 事件回调，广播到 WebSocket。"""
    repository.append_event(event)  # 持久化
    _emit_to_ws(event)  # 推送到 WS 队列
```

确保 Event 类在 routes.py 中正确导入：
```python
from dashboard.event import Event  # 或正确的模块路径
```

- [ ] **步骤 2：验证语法**

```bash
cd /Users/jieson/auto-coding && python -c "import dashboard.api.routes; print('OK')"
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard/api/routes.py
git commit -m "fix(dashboard): 修复 CommandProcessor on_event 接口签名匹配 Event 对象"
```

---

## 任务 6：确保 EventBus 事件广播到 WebSocket

**文件：** `dashboard/api/routes.py`

- [ ] **步骤 1：验证 broadcast_queue 桥接**

检查 `_emit_to_ws` 函数是否正确将事件推送到 WebSocket 的 broadcast_queue。确保：

1. WebSocket handler 中正确初始化了 `broadcast_queue: Queue`
2. `_emit_to_ws(event)` 正确调用 `broadcast_queue.put_nowait(event_dict)`
3. WebSocket 读取循环正确消费 queue 并发送给客户端

当前代码结构应已正确实现（routes.py 第 49-56 行），但需确认 `broadcast_queue` 在 WebSocket handler 和 `_emit_to_ws` 之间正确共享。

- [ ] **步骤 2：添加事件桥接验证**

在 WebSocket handler 中添加调试日志确认桥接：

```python
# 在 WebSocket handler 的消费循环中:
try:
    event_dict = broadcast_queue.get_nowait()
    await websocket.send_json(event_dict)
except QueueEmpty:
    pass
```

- [ ] **步骤 3：Commit**

```bash
git add dashboard/api/routes.py
git commit -m "fix(dashboard): 确保 EventBus 事件正确广播到 WebSocket broadcast_queue"
```

---

## 任务 7：创建 AgentClusterMonitor 组件

**文件：** `dashboard-ui/components/agent-cluster-monitor.tsx`（新建）

- [ ] **步骤 1：创建组件**

创建 Agent 集群监控面板，包含：
- 按角色分组的 Agent 列表
- 每个 Agent 的当前状态（运行中/空闲/错误/等待审批）
- 当前正在执行的操作（从事件流推断）
- 静默检测指示器
- 进程信息（PID、运行状态）
- 操作按钮（暂停/恢复/重试）

- [ ] **步骤 2：验证构建**

```bash
npx tsc --noEmit
```

- [ ] **步骤 3：Commit**

```bash
git add components/agent-cluster-monitor.tsx
git commit -m "feat(dashboard-ui): 创建 AgentClusterMonitor 组件"
```

---

## 任务 8：集成 AgentClusterMonitor 到页面

**文件：** `dashboard-ui/app/page.tsx`

- [ ] **步骤 1：导入并挂载**

```tsx
import { AgentClusterMonitor } from '@/components/agent-cluster-monitor';
```

在页面合适位置（侧边栏或独立面板）添加：
```tsx
<AgentClusterMonitor />
```

- [ ] **步骤 2：验证构建**

```bash
npm run build
```

- [ ] **步骤 3：Commit**

```bash
git add app/page.tsx
git commit -m "feat(dashboard-ui): 页面集成 AgentClusterMonitor"
```

---

## 任务 9：修复 PM Chat 上下文退化

**文件：** `core/project_manager.py` + `agents/product_manager.py`

- [ ] **步骤 1：分析上下文退化原因**

PM chat 上下文随时间退化通常因为：
1. 对话历史被截断但未保留关键项目状态
2. Token 限制导致早期关键信息丢失
3. 缺少状态快照恢复机制

修复策略：在每次对话前注入当前项目状态快照作为系统提示的一部分。

- [ ] **步骤 2：实现状态注入**

在 ProductManager.chat_response 方法中，构建 prompt 时注入当前项目状态摘要。

- [ ] **步骤 3：Commit**

```bash
git add core/project_manager.py agents/product_manager.py
git commit -m "fix(dashboard): PM Chat 注入项目状态快照防止上下文退化"
```

---

## 任务 10：补充前端测试

**目录：** `dashboard-ui/tests/`（新建）

- [ ] **步骤 1：创建测试基础设施**

设置 jest/playwright 测试框架，配置 mock API。

- [ ] **步骤 2：编写 Store 测试**

测试 applyEventToState、fetchAgents、command actions 等核心逻辑。

- [ ] **步骤 3：编写 API 客户端测试**

测试 listAgents 嵌套解析、getAgentEvents 裸数组适配、command actions target_id 正确传递。

- [ ] **步骤 4：编写组件测试**

测试 ExecutionControl 和 AgentClusterMonitor 渲染和行为。

- [ ] **步骤 5：运行测试 + 验证覆盖率**

```bash
npm test -- --coverage
```

目标：80%+ 覆盖率。

- [ ] **步骤 6：Commit**

```bash
git add dashboard-ui/tests/
git commit -m "test(dashboard-ui): 补充前端测试覆盖率到 80%+"
```

---

## 验收标准

1. **命令生命周期**：approve/reject/pause/resume/retry/skip 全流程端到端可用 ✅
2. **API 契约**：前后端类型、字段、嵌套结构完全对齐 ✅
3. **WebSocket 广播**：EventBus.emit 事件实时推送到前端 ✅
4. **AgentClusterMonitor**：角色分组、状态、操作面板完整 ✅
5. **PM Chat 上下文**：对话质量稳定不退化 ✅
6. **前端测试**：80%+ 覆盖率，核心逻辑有测试保护 ✅

## 验证命令

```bash
# 后端语法检查
cd /Users/jieson/auto-coding && python -c "import dashboard.coordinator; print('OK')"

# 前端构建
cd /Users/jieson/auto-coding/dashboard-ui && npm run build

# 类型检查
npx tsc --noEmit

# 前端测试
npm test -- --coverage
```
