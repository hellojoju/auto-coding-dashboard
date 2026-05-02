# 当前 API 基线

## 关键 REST 接口

- `GET /api/dashboard/state`
- `GET /api/dashboard/events`
- `POST /api/dashboard/commands`
- `GET /api/dashboard/commands/{id}`
- `GET /api/agents`
- `GET /api/agents/{id}/status`
- `POST /api/agents/{id}/message`
- `POST /api/agents/{id}/interrupt`
- `GET /api/blocking-issues`
- `GET /api/execution-ledger`

## WebSocket

- `GET ws://.../ws/dashboard`
- 首帧：`hello`
- 后续：增量事实事件
