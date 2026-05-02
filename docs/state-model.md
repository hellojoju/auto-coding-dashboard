# 状态模型

## Feature

- 主键：`id`
- 状态：`pending | in_progress | review | done | blocked`
- 关键字段：
  - `assigned_to`
  - `assigned_instance`
  - `dependencies`
  - `files_changed`
  - `blocking_issues`

## AgentInstance

- 主键：`id`
- 状态：`idle | busy | paused | error | waiting_approval | waiting_pm`
- 关键字段：
  - `role`
  - `current_feature`
  - `workspace_id`
  - `workspace_path`

## Command

- 主键：`command_id`
- 状态：`pending | accepted | applied | rejected | failed | cancelled`
- 关键字段：
  - `type`
  - `target_id`
  - `payload`

## Event

- 主键：`event_id`
- 特点：单调递增、不可变
- 关键字段：
  - `type`
  - `timestamp`
  - `payload`

## BlockingIssue

- 主键：`issue_id`
- 状态：`resolved=false/true`
- 关键字段：
  - `issue_type`
  - `feature_id`
  - `description`
  - `context`
  - `resolution`

## Snapshot

快照用于前端首屏与断线重连，包含：

- agents
- features
- chat_history
- module_assignments
- blocking_issues
- last_event_id
