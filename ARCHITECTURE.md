# Auto-Coding 架构契约

本文档定义系统的模块边界、状态归属和禁止事项。

## 模块边界

### `core/`
- 负责项目初始化、Feature 规划、执行编排、验收、Git 服务。
- 不负责 REST API、WebSocket 广播、前端状态。

### `dashboard/`
- 负责 Repository、命令处理、WebSocket、Dashboard API、观测能力。
- 不直接生成 PRD，不直接拼 Agent prompt。

### `agents/`
- 负责角色 prompt 组合、Claude CLI 执行、执行结果与活动上报。
- 不负责最终状态裁决，不直接修改前端状态。

### `dashboard-ui/`
- 负责展示快照、消费事件、发送控制命令。
- 不复写后端状态机，不作为业务事实源。

## 状态归属

| 数据 | 事实源 | 备注 |
|------|--------|------|
| Feature 生命周期 | `ProjectStateRepository` | `features.json` 保留为兼容/审计副本 |
| Command | `ProjectStateRepository` | 仅通过 API + Consumer 推进 |
| Event | `ProjectStateRepository` | EventBus 只做广播与短期缓存 |
| Agent 状态 | `ProjectStateRepository` | 前端只缓存 |
| BlockingIssue | `ProjectStateRepository` | 作为一等对象管理 |
| Execution Ledger | `data/execution-plan.json` | 审计与人类可读台账 |
| UI 状态 | Zustand | 不持久化到后端 |

## 事件流

1. 业务状态先写 Repository。
2. Repository 追加事实事件。
3. WebSocket 只广播快照与增量事件。
4. 前端收到事件后更新缓存，不自行推导最终业务状态。

## 命令流

1. 前端创建 `Command`。
2. Repository 持久化为 `pending`。
3. `CommandConsumer` 消费并驱动状态机。
4. 结果回写 Repository，并广播事件。

## 禁止事项

1. 禁止一个业务事实同时存在两套长期真源。
2. 禁止把 WebSocket 广播当长期状态存储。
3. 禁止前端复写后端状态机。
4. 禁止在 `ProjectManager` 中直接堆叠新的 API / WebSocket 逻辑。
