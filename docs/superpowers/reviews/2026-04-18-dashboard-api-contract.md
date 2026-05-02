# AI全自动开发平台 - Dashboard 前后端契约草案

> 适用范围: Dashboard V2
> 日期: 2026-04-18
> 状态: 草案

---

## 1. 契约目标

本契约用于统一 Dashboard 前后端的数据约定，避免设计文档、计划文档、后端实现、前端 store 之间再出现字段和路径漂移。

本草案遵循以下原则：

1. REST 负责快照和命令
2. WebSocket 负责事实事件
3. 前端初始化永远先拿快照
4. 所有 payload 围绕 `project_id`、`run_id`、`schema_version`

---

## 2. 基础约定

### 2.1 标识字段

1. `project_id`: 项目标识
2. `run_id`: 当前运行实例标识
3. `schema_version`: 数据结构版本
4. `event_id`: 事件单调递增序号
5. `command_id`: 命令唯一标识
6. `snapshot_version`: 快照版本号

### 2.2 时间字段

所有时间使用 ISO 8601 UTC 字符串，例如：

`2026-04-18T14:35:01Z`

### 2.3 错误响应格式

所有 REST 错误统一为：

```json
{
  "error": {
    "code": "COMMAND_TARGET_NOT_FOUND",
    "message": "Agent backend-1 not found",
    "details": {}
  }
}
```

---

## 3. REST API

建议统一前缀：

`/api/dashboard`

### 3.1 获取快照

`GET /api/dashboard/state`

#### Query

1. `project_id` 必填
2. `run_id` 可选

#### Response 200

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

### 3.2 获取事件增量

`GET /api/dashboard/events`

#### Query

1. `project_id` 必填
2. `run_id` 可选
3. `after_event_id` 可选
4. `limit` 可选，默认 200

#### Response 200

```json
{
  "schema_version": 1,
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "events": []
}
```

### 3.3 创建命令

`POST /api/dashboard/commands`

#### Request

```json
{
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "type": "pause_agent",
  "target_id": "backend-1",
  "payload": {}
}
```

#### Response 202

```json
{
  "schema_version": 1,
  "command_id": "cmd_20260418_0001",
  "status": "pending"
}
```

### 3.4 查询命令

`GET /api/dashboard/commands/{command_id}`

#### Response 200

```json
{
  "schema_version": 1,
  "command_id": "cmd_20260418_0001",
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "type": "pause_agent",
  "target_id": "backend-1",
  "status": "applied",
  "issued_at": "2026-04-18T14:35:00Z",
  "updated_at": "2026-04-18T14:35:01Z",
  "result": {
    "message": "Agent paused"
  }
}
```

### 3.5 获取聊天记录

`GET /api/dashboard/chat`

#### Query

1. `project_id` 必填
2. `run_id` 可选
3. `limit` 可选

### 3.6 发送 PM 消息

`POST /api/dashboard/chat`

#### Request

```json
{
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "content": "F007 先不做支付，改成做积分系统"
}
```

#### Response 202

```json
{
  "schema_version": 1,
  "command_id": "cmd_20260418_0002",
  "status": "pending"
}
```

---

## 4. WebSocket

建议路径：

`/ws/dashboard`

### 4.1 连接参数

1. `project_id` 必填
2. `run_id` 可选
3. `last_event_id` 可选

### 4.2 连接建立后的第一条消息

后端应返回握手确认，而不是全量状态替代 REST 快照。

```json
{
  "type": "hello",
  "schema_version": 1,
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "last_event_id": 128
}
```

### 4.3 事件消息格式

```json
{
  "type": "event",
  "event": {
    "schema_version": 1,
    "event_id": 129,
    "project_id": "todo-app",
    "run_id": "run_20260418_1430",
    "type": "feature_completed",
    "timestamp": "2026-04-18T14:36:00Z",
    "caused_by_command_id": null,
    "payload": {
      "feature_id": "F004",
      "files_changed": ["src/api/users.py"],
      "summary": "用户 API 完成"
    }
  }
}
```

### 4.4 服务端控制消息

#### 需要全量重同步

```json
{
  "type": "resync_required",
  "reason": "event_gap_detected"
}
```

#### 心跳

```json
{
  "type": "ping",
  "timestamp": "2026-04-18T14:36:10Z"
}
```

客户端可回复：

```json
{
  "type": "pong",
  "timestamp": "2026-04-18T14:36:10Z"
}
```

---

## 5. 核心对象 Schema

### 5.1 AgentInstance

```json
{
  "id": "backend-1",
  "role": "backend",
  "instance_number": 1,
  "status": "idle",
  "current_feature": null,
  "workspace_id": "ws_backend_1",
  "workspace_path": "/worktrees/backend-1",
  "total_tasks_completed": 5,
  "started_at": "2026-04-18T10:00:00Z"
}
```

状态允许值：

1. `idle`
2. `busy`
3. `paused`
4. `blocked`
5. `error`

### 5.2 Feature

```json
{
  "id": "F004",
  "category": "backend",
  "description": "创建用户 API",
  "priority": "P0",
  "assigned_to": "backend",
  "assigned_instance": "backend-1",
  "status": "in_progress",
  "dependencies": [],
  "workspace_id": "ws_backend_1",
  "files_changed": [],
  "started_at": "2026-04-18T14:20:00Z",
  "completed_at": null,
  "error_log": []
}
```

状态允许值：

1. `pending`
2. `in_progress`
3. `review`
4. `done`
5. `blocked`
6. `skipped`

### 5.3 Command

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
  "updated_at": "2026-04-18T14:35:01Z",
  "status": "applied",
  "result": {
    "message": "Agent paused"
  }
}
```

状态允许值：

1. `pending`
2. `accepted`
3. `applied`
4. `rejected`
5. `failed`
6. `cancelled`

### 5.4 ChatMessage

```json
{
  "id": "chat_001",
  "project_id": "todo-app",
  "run_id": "run_20260418_1430",
  "role": "user",
  "content": "F007 先不做支付，改成做积分系统",
  "timestamp": "2026-04-18T14:35:00Z",
  "related_command_id": "cmd_20260418_0002"
}
```

### 5.5 PendingApproval

```json
{
  "approval_id": "approval_001",
  "decision_type": "start_feature_batch",
  "title": "是否启动 F007",
  "content": "F004 已完成，准备启动 F007 支付集成",
  "created_at": "2026-04-18T14:34:00Z",
  "status": "pending"
}
```

---

## 6. 前端状态机约定

### 6.1 初始化流程

```text
Page Load
  -> GET /api/dashboard/state
  -> 保存 snapshot 和 last_event_id
  -> 连接 /ws/dashboard
  -> 若连接后发现服务端 last_event_id 更大，则拉取 events 增量
```

### 6.2 本地更新规则

1. 快照覆盖本地基线
2. 事件按 `event_id` 严格递增应用
3. 命令创建成功后只更新命令列表，不直接更新业务状态
4. 如果事件断档，则触发全量重同步

---

## 7. 事件类型清单

推荐最小事件集合：

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

---

## 8. 命令类型清单

推荐最小命令集合：

1. `approve_decision`
2. `reject_decision`
3. `send_pm_message`
4. `pause_agent`
5. `resume_agent`
6. `retry_feature`
7. `skip_feature`

---

## 9. 兼容性约束

为减少迁移风险，建议遵守以下兼容策略：

1. 旧字段迁移期间由后端做兼容适配，前端只依赖新契约
2. 若缺失 `event_id`，前端不允许做增量同步，只能全量快照
3. 若缺失 `run_id`，系统视为单运行实例模式
4. 若主页面仍需 mock，只允许在显式 demo 模式启用

---

## 10. 结论

这份契约草案的重点不在接口数量，而在约束边界：

1. 前端不再直接猜业务状态
2. 后端不再混用命令和事件
3. 快照、命令、事件成为三类清晰对象
4. 后续实现和测试都应以这份契约为准绳
