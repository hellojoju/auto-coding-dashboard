# Auto-Coding Homepage Design Brief

本次重画对象是 `/Users/jieson/auto-coding` 仓库本体，不是 `auto-coding-agent-demo`。

## 设计对象

- 产品定位：多 Agent 自动编程平台
- 首页类型：主控制台首页 / 项目管理看板
- 不是：营销落地页、故事转视频工具、通用 AI 聊天首页

## 依据

- 顶层说明：`/Users/jieson/auto-coding/README.md`
- 架构契约：`/Users/jieson/auto-coding/AGENTS.md`
- 当前首页实现：`/Users/jieson/auto-coding/dashboard-ui/app/page.tsx`
- 关键组件：
  - `dashboard-ui/components/agent-status-panel.tsx`
  - `dashboard-ui/components/agent-cluster-monitor.tsx`
  - `dashboard-ui/components/module-assignment-panel.tsx`
  - `dashboard-ui/components/kanban-column.tsx`
  - `dashboard-ui/components/execution-control.tsx`
  - `dashboard-ui/components/chat-window.tsx`

## 首页应体现的真实功能

- ProjectManager / PMCoordinator 调度中枢
- Feature 看板流转：待处理、进行中、审查中、已完成、已阻塞
- Agent 集群监控：多角色、多实例、状态与静默检测
- 审批闸门：审批通过、驳回、暂停、恢复
- 模块分配与依赖关系
- PM 对话入口
- 实时日志 / 事件流

## 成品

- 设计图：`/Users/jieson/auto-coding/design/scene-mockups-v2/auto-coding-homepage-dashboard-v1.png`

## 视觉方向

- 不是传统后台灰盒子，也不是夸张科幻 UI
- 采用“工程控制台”语义：
  - 清晰的信息分区
  - 高密度但可读的状态视图
  - 以执行状态、审批、阻塞、协作为视觉主轴
  - 配色偏暖白、石墨、工程蓝、苔绿、琥珀
