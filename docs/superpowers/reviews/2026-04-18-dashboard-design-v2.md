# AI全自动开发平台 - Dashboard 设计稿 V2

> 基于评审意见整理
> 日期: 2026-04-18
> 状态: 建议稿

---

## 1. 设计目标

Dashboard V2 的目标不是单纯提供一个“能看”的前端页面，而是提供一个可信的项目控制台。它必须同时满足以下要求：

1. 用户能看到真实执行状态，而不是前端本地推导状态
2. 用户发出的控制动作能被调度器消费，并能确认结果
3. 单实例模式简单可用，多实例模式可安全扩展
4. 断线、重连、服务重启后，状态能够恢复和追溯
5. 设计必须与现有自动开发主链路兼容，而不是再造一套平行运行时

---

## 2. 非目标

V2 明确不追求以下内容：

1. 不优先解决复杂视觉设计问题
2. 不优先支持多用户权限体系
3. 不在第一阶段引入 Redis、Kafka 等外部基础设施
4. 不把 EventBus 设计成状态真源
5. 不在共享工作区上强行支持高并发多实例写入

---

## 3. 核心设计原则

1. 单一状态源：所有 Dashboard 相关状态必须从同一份 project-scoped 存储中读取
2. 命令与事实分离：用户动作是 command，系统结果是 event
3. 快照优先：前端总是先拿快照，再接增量事件
4. 广播不是存储：EventBus 只负责推送，不负责定义真相
5. 并发要隔离：多实例执行以隔离工作区为前提
6. 设计先保守：优先保证一致性，再追求高并发和交互丰富度

---

## 4. 总体架构

### 4.1 组件划分

1. `ProjectManager`
   - 负责调度
   - 消费命令
   - 产出调度决策和事实事件

2. `ProjectStateRepository`
   - 持久化项目运行状态
   - 提供快照读取
   - 提供命令和事件的附加写入能力

3. `EventBus`
   - 将已提交到 repository 的事件广播给在线客户端
   - 不直接生成业务状态

4. `Dashboard API`
   - 提供快照读取接口
   - 接收命令创建请求
   - 提供 WebSocket 实时订阅

5. `AgentPool`
   - 管理 Agent 实例生命周期
   - 管理实例工作区
   - 单实例模式可共享工作区
   - 多实例模式必须使用隔离工作区

6. `Dashboard UI`
   - 渲染快照
   - 发送命令
   - 订阅事实事件
   - 不把本地推导结果当作最终真实状态

### 4.2 调整后的系统关系

```text
User
  -> Dashboard UI
      -> Dashboard API
          -> ProjectStateRepository
          -> Command Queue / Command Store
          -> EventBus
  -> ProjectManager
      -> ProjectStateRepository
      -> AgentPool
      -> EventBus
```

---

## 5. 数据分层

V2 将运行数据分为三层。

### 5.1 Snapshot

用途：表达“当前是什么状态”。

建议包含：

1. 项目信息
2. Agent 实例状态
3. Feature 状态
4. 当前待处理审批项
5. 最新聊天上下文
6. 最新事件游标 `last_event_id`

### 5.2 Event

用途：表达“发生过什么事实”。

要求：

1. 只追加
2. 带全局单调递增 `event_id`
3. 带 `project_id`
4. 带 `run_id`
5. 带 `schema_version`

### 5.3 Command

用途：表达“用户或系统想让调度器做什么”。

要求：

1. 独立状态机
2. 可审计
3. 可失败
4. 能关联到触发它的用户动作或系统动作

---

## 6. 建议的数据文件

以下为建议结构，均应位于 project-scoped 数据目录内。

1. `dashboard-state.json`
   - 最新快照

2. `commands.log`
   - 命令流

3. `events.log`
   - 事实事件流

4. `chat.json`
   - 聊天历史

5. `agents.json`
   - 实例描述和当前工作区信息

6. `features.json`
   - Feature 状态和调度归属

所有文件都应带 `schema_version`，避免未来调整结构时失控。

---

## 7. 命令模型

### 7.1 命令定义

推荐命令类型：

1. `approve_decision`
2. `reject_decision`
3. `send_pm_message`
4. `pause_agent`
5. `resume_agent`
6. `retry_feature`
7. `skip_feature`
8. `override_plan`

### 7.2 命令状态

命令状态统一为：

1. `pending`
2. `accepted`
3. `applied`
4. `rejected`
5. `failed`
6. `cancelled`

### 7.3 命令生命周期

```text
UI 创建命令
  -> API 持久化命令
  -> PM / CommandProcessor 消费命令
  -> 仓库更新命令状态
  -> 产出一个或多个事实事件
  -> 前端根据事实事件和快照更新
```

### 7.4 命令示例

```json
{
  "schema_version": 1,
  "command_id": "cmd_20260418_0001",
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "type": "pause_agent",
  "target_id": "backend-1",
  "payload": {},
  "issued_by": "user",
  "issued_at": "2026-04-18T14:35:00Z",
  "status": "pending"
}
```

---

## 8. 事件模型

### 8.1 事件原则

1. 事件必须表达已发生的事实
2. 一个命令可能产出多个事件
3. 事件必须能被重放
4. 事件必须能关联来源命令

### 8.2 推荐事件类型

1. `agent_status_changed`
2. `agent_log_emitted`
3. `feature_status_changed`
4. `feature_completed`
5. `feature_blocked`
6. `pm_message_created`
7. `pm_decision_requested`
8. `command_accepted`
9. `command_applied`
10. `command_failed`

### 8.3 事件示例

```json
{
  "schema_version": 1,
  "event_id": 128,
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "type": "agent_status_changed",
  "timestamp": "2026-04-18T14:35:01Z",
  "caused_by_command_id": "cmd_20260418_0001",
  "payload": {
    "agent_id": "backend-1",
    "feature_id": "F004",
    "old_status": "busy",
    "new_status": "paused"
  }
}
```

---

## 9. 快照模型

### 9.1 快照用途

快照用于：

1. 首屏加载
2. 断线重连后的快速恢复
3. 前端全量状态校正
4. 调试和排障

### 9.2 快照要求

1. 含 `project_id`
2. 含 `run_id`
3. 含 `snapshot_version`
4. 含 `last_event_id`
5. 可在任意时刻替代前端本地状态

### 9.3 快照示例

```json
{
  "schema_version": 1,
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "snapshot_version": 12,
  "last_event_id": 128,
  "project_name": "TODO 应用",
  "summary": {
    "total": 12,
    "done": 5,
    "in_progress": 3,
    "pending": 2,
    "blocked": 2
  },
  "agents": [],
  "features": [],
  "pending_approvals": [],
  "chat_history": []
}
```

---

## 10. 单实例与多实例执行模式

### 10.1 单实例模式

单实例模式适用于：

1. 当前默认开发模式
2. 小项目
3. 调试阶段

约束：

1. 共享工作区
2. 逻辑锁可以关闭或弱化
3. Dashboard 主要负责监控和人工干预

### 10.2 多实例模式

多实例模式适用于：

1. 已验证主链路可靠
2. Feature 切分边界清晰
3. 有明确工作区隔离机制

约束：

1. 每个实例必须有独立工作区
2. PM 只能合并隔离工作区的产物
3. 文件锁是辅助调度信号，不是最终隔离策略
4. 集成验证只能发生在合并阶段

---

## 11. Dashboard UI 行为要求

### 11.1 首屏加载

1. 页面初始化先请求快照
2. 快照加载成功后再建立 WebSocket
3. WebSocket 建立成功后使用 `last_event_id` 同步缺失增量

### 11.2 本地状态更新规则

1. 快照是基线
2. 事件是增量
3. 命令提交成功不等于业务状态已完成
4. 如果本地状态与快照冲突，快照优先

### 11.3 用户操作反馈

每个按钮都必须有明确反馈：

1. 已创建命令
2. 命令已被接收
3. 命令已执行
4. 命令失败

不要只在按钮点击后立即修改业务状态展示。

---

## 12. REST 与 WebSocket 设计原则

1. REST 负责快照和命令
2. WebSocket 负责事件推送
3. 不在 WebSocket 中塞整份状态，除非显式做重同步
4. 所有接口都必须围绕 `project_id` 和 `run_id`

---

## 13. 错误与恢复策略

1. API 返回标准错误体
2. WebSocket 断开后自动重连
3. 重连后优先请求快照校正
4. 若 `last_event_id` 不连续，则丢弃本地增量并重新同步全量快照
5. 命令执行失败要产生 `command_failed` 事件，并写入失败原因

---

## 14. 安全与边界

V2 暂按本地单用户场景设计，但仍建议保留以下边界：

1. 禁止前端直接改内存状态作为真实结果
2. 禁止未持久化的命令进入调度器
3. 禁止未隔离的多实例共享写入主工作区
4. 禁止 EventBus 跳过 repository 直接定义业务状态

---

## 15. 验收标准

Dashboard V2 至少应满足以下验收：

1. 单实例模式下，快照与 PM 实际执行结果一致
2. 用户点击任意控制按钮后，可以看到命令状态变化
3. 前端刷新页面后，状态能够从快照恢复
4. WebSocket 断开重连后，不会重复或遗漏关键状态变化
5. 多实例模式未开启前，不暴露“并行开发安全可用”的误导性承诺

---

## 16. 结论

V2 的关键变化不是多加几个接口或页面组件，而是重新定义 Dashboard 的角色：

1. 它是调度内核的可视化和控制入口
2. 它不拥有独立的状态真相
3. 它必须围绕快照、命令、事件三层模型构建
4. 它必须区分单实例模式和多实例模式

在这个前提下，Dashboard 才能从“演示界面”升级为“可信控制台”。
