# Ralph Runtime Console 前端设计方案

版本：v1.0 草案
日期：2026-05-02
文档语言：中文
依赖文档：

```text
Ralph docs/auto-coding-ralph-orchestrator-prd.zh.md
Ralph docs/auto-coding-ralph-orchestrator-phase2-design.zh.md
Ralph docs/auto-coding-ralph-orchestrator-implementation-plan.zh.md
Ralph docs/auto-coding-ralph-orchestrator-mvp-checklist.zh.md
dashboard-ui/RALPH_FRONTEND_STANDARDS.md
```

---

## 1. 现状诊断

### 1.1 已实现页面

| 路由 | 内容 | 评价 |
|------|------|------|
| `/ralph` | 概览：4 统计卡片 + WorkUnit 列表 + 连接状态 + 状态分布 | 信息密度低，只是"统计面板"而非"指挥中心" |
| `/ralph/[id]` | WorkUnit 详情：纵向堆砌所有字段 | 无锚点导航，无固定操作栏，翻阅困难 |
| `/ralph/approvals` | 审批中心：PendingAction + Blocker 列表 | 缺少关联上下文，Blocker 孤立展示 |

### 1.2 已实现组件

`sidebar` / `tab-bar` / `work-unit-list` / `work-unit-detail` / `approval-center` / `evidence-viewer` / `run-status-header`

### 1.3 核心问题

1. **信息密度低**：API 返回的 `pending_commands`、`last_updated`、成功率、WebSocket 实时事件流，前端均未展示
2. **页面分配不合理**：3 个页面覆盖不足，缺少命令中心、事件日志、配置中心、执行日志等关键页面
3. **配置项缺失**：PRD 明确要求的 LLM Provider 配置、ToolAdapter 配置、Issue 治理配置，前端零实现
4. **布局问题**：概览页右栏浪费、详情页无导航、缺少固定操作区
5. **无数据可视化**：状态分布纯文字列表、依赖关系不可见、无趋势图
6. **无全局搜索**：WorkUnit ID、命令 ID、文件名无处快速检索

---

## 2. 设计目标

Ralph Runtime Console 的定位不是"好看的仪表盘"，而是**运维指挥中心**。用户打开它应该能回答三个问题：

1. **系统在跑什么？** — 当前运行状态、活跃任务、执行进度
2. **需要我做什么？** — 待审批事项、阻塞项、危险操作确认
3. **之前发生了什么？** — 最近事件、命令历史、执行日志

额外目标：
- 为 PRD 9.14/9.15/9.16 节的配置需求提供前端界面
- 为 Phase 2 的记忆系统、知识图谱预留展示入口
- 所有 API 已返回的数据不能有"死数据"——要么展示，要么说明为什么不展示

---

## 3. 信息架构

### 3.1 页面树

```
Ralph Console
├── /ralph                      指挥中心（Dashboard）
├── /ralph/work-units           工作单元列表
├── /ralph/work-units/[id]      工作单元详情
├── /ralph/commands             命令中心
├── /ralph/events               事件日志
├── /ralph/approvals            审批中心
├── /ralph/settings             配置中心
│   ├── /ralph/settings/providers    LLM Provider 管理
│   ├── /ralph/settings/tools        工具链配置
│   └── /ralph/settings/issues       Issue 治理策略
└── /ralph/memory               记忆系统（Phase 2）
```

### 3.2 侧边栏导航

```
┌─────────────────────┐
│ Ralph Console       │
├─────────────────────┤
│ 🏠 指挥中心         │  ← 默认首页
│ 📋 工作单元         │
│ ⚡ 命令中心         │
│ 📡 事件日志         │
│ ✅ 审批中心     (3) │  ← 待处理数 badge
│ ⚙️ 配置中心         │
│ 🧠 记忆系统         │  ← Phase 2，可先 disabled
├─────────────────────┤
│ ● 系统运行中        │
└─────────────────────┘
```

---

## 4. 页面详细设计

### 4.1 指挥中心 `/ralph`

**定位**：一眼看全局。不用滚动就能掌握系统状态。

**布局**：三行式

```
┌──────────────────────────────────────────────────────────┐
│ 第一行：关键指标卡片（6 个，横排）                          │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│ │总任务│ │运行中│ │待审批│ │阻塞项│ │成功率│ │待命令│  │
│ │  42  │ │  5   │ │  3   │ │  2   │ │ 87%  │ │  4   │  │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │
├──────────────────────────┬───────────────────────────────┤
│ 第二行左：状态分布        │ 第二行右：最近活动时间线        │
│ (堆叠条形图或环形图)      │ (最近 20 条 event，实时更新)   │
│                          │                               │
│ running     ████████ 5   │ 12:03 wu-xxx 进入 needs_review│
│ needs_review ██████ 3    │ 12:01 cmd-xxx applied          │
│ blocked     ████ 2       │ 11:58 wu-yyy 创建              │
│ accepted    ██████████ 18│ 11:55 blocker-zzz 已解决       │
│ failed      ██ 1         │                               │
│ draft       ██ 2         │                               │
│ ready       ██████ 8     │                               │
│ needs_rework ██ 3        │                               │
├──────────────────────────┴───────────────────────────────┤
│ 第三行：快速入口                                          │
│ [3 个待审批] →  [2 个阻塞项] →  [4 个待处理命令] →       │
│ [最新报告] →    [运行中的 WorkUnit] →                    │
└──────────────────────────────────────────────────────────┘
```

**数据来源**：
- 指标卡片：`GET /api/ralph/summary` + store 实时数据
- 状态分布：同上
- 最近活动：WebSocket `handleEvent` 事件流，保留最近 50 条
- 快速入口：store 中的 `pendingActions`、`blockers` 计数

**关键改动**：
- 成功率 = `accepted / (accepted + failed) * 100%`
- 待命令 = 从 summary 的 `pending_commands` 或 `GET /api/ralph/commands?status=pending` 获取
- 最近活动时间线：复用 WebSocket 事件，存入 store 的 `recentEvents: RalphEvent[]`（最多 50 条，超出 FIFO）

### 4.2 工作单元列表 `/ralph/work-units`

**定位**：现有概览页的主内容区独立出来。

**布局**：筛选栏 + 列表 + 分页

```
┌──────────────────────────────────────────────────────────┐
│ 筛选：[全部] [运行中] [待审查] [已通过] [待返工] ...      │
│ 搜索：[________________] 🔍         排序：[最近更新 ▼]   │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │
│ │ wu-042  │ 实现JWT登录接口          │ ✅ accepted     │ │
│ │ development │ 2分钟前 │ 依赖: wu-038, wu-040        │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ wu-041  │ 修复token过期不刷新的bug  │ 🔴 needs_review│ │
│ │ fix │ 5分钟前 │ 无依赖                              │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ ...                                                │ │
│ └──────────────────────────────────────────────────────┘ │
│                        < 1 2 3 ... 8 >                   │
└──────────────────────────────────────────────────────────┘
```

**新增功能**：
- 全局搜索（按 work_id、title、target 模糊匹配）
- 排序（按创建时间、更新时间、状态）
- 分页（后端 API 已有 `limit`/`offset` 参数）
- 批量操作入口（预留）

### 4.3 工作单元详情 `/ralph/work-units/[id]`

**定位**：保留现有纵向布局，但加三大改进。

**改进 1：固定顶部操作栏**

```
┌──────────────────────────────────────────────────────────┐
│ ← 返回列表    wu-042    实现JWT登录接口    ✅ accepted    │
│ [批准] [请求返工] [重试] [取消] [扩展范围]  ...         │
└──────────────────────────────────────────────────────────┘
```

操作栏按钮根据当前状态动态显示可用操作（从 `STATUS_TRANSITIONS` 推算）。

**改进 2：右侧锚点导航**

```
页面内容                      ｜ 锚点导航（sticky）
┌─────────────────────────┐  ｜ ┌──────────────┐
│ 头部（ID/标题/状态）     │  ｜ │ 基本信息      │
├─────────────────────────┤  ｜ │ 目标          │
│ 目标                    │  ｜ │ 验收标准      │
├─────────────────────────┤  ｜ │ 允许/禁止修改 │
│ 验收标准                │  ｜ │ Context Pack  │
├─────────────────────────┤  ｜ │ Task Harness  │
│ 允许修改 / 禁止修改      │  ｜ │ 证据          │
├─────────────────────────┤  ｜ │ 审查结果      │
│ Context Pack            │  ｜ │ 状态流转      │
├─────────────────────────┤  ｜ │ 执行日志      │
│ Task Harness            │  ｜ │ 元信息        │
├─────────────────────────┤  ｜ └──────────────┘
│ 证据                    │  ｜
├─────────────────────────┤  ｜
│ 审查结果                │  ｜
├─────────────────────────┤  ｜
│ 状态流转                │  ｜
├─────────────────────────┤  ｜
│ 执行日志（新增）         │  ｜
├─────────────────────────┤  ｜
│ 元信息                  │  ｜
└─────────────────────────┘  ｜
```

**改进 3：执行日志区（新增）**

```
┌──────────────────────────────────────────┐
│ 执行日志                          [自动滚动 ▼] │
├──────────────────────────────────────────┤
│ [12:03:15] Running preflight checks...   │
│ [12:03:16] ✓ preflight passed            │
│ [12:03:20] Generating JWT token handler  │
│ [12:03:45] Running unit tests...         │
│ [12:03:52] ✓ 12/12 tests passed          │
│ [12:03:53] Saving evidence...            │
│ [12:03:54] Work unit completed           │
└──────────────────────────────────────────┘
```

数据来源：store 中的 `streamChunks[workId]`（由 `ralph_stream_chunk` WebSocket 事件填充），如果为空则调用 API 获取历史日志。

### 4.4 命令中心 `/ralph/commands`（新增）

**定位**：查看所有命令的历史和状态，支持取消 pending 命令。

**布局**：

```
┌──────────────────────────────────────────────────────────┐
│ 筛选：[全部] [pending] [processing] [completed] [failed] │
├──────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────┐│
│ │ cmd-039 │ accept_review │ wu-042 │ ✅ completed       ││
│ │ 12:01   │ idempotency: abc123                         ││
│ ├────────────────────────────────────────────────────────┤│
│ │ cmd-038 │ request_rework │ wu-041 │ ⏳ pending        ││
│ │ 11:58   │ idempotency: def456          [取消]         ││
│ ├────────────────────────────────────────────────────────┤│
│ │ ...                                                  ││
│ └────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

**数据来源**：`GET /api/ralph/commands`、`POST /api/ralph/commands/{id}/cancel`

**每个命令卡片展开后**：
- 完整 payload
- 创建时间 / 完成时间
- 错误信息（如果 failed）
- 关联的 WorkUnit 链接

### 4.5 事件日志 `/ralph/events`（新增）

**定位**：实时事件流查看器，用于调试和监控。

**布局**：

```
┌──────────────────────────────────────────────────────────┐
│ 事件类型过滤：[全选] [WorkUnit] [Command] [Blocker] ...  │
│ 暂停 ⏸  / 继续 ▶  / 清空 🗑        自动滚动：[开/关]   │
├──────────────────────────────────────────────────────────┤
│ 12:03:54 │ work_unit_status_changed │ wu-042 │ running→needs_review │
│ 12:03:15 │ work_unit_status_changed │ wu-042 │ ready→running        │
│ 12:01:22 │ command_applied          │ cmd-039│ accept_review        │
│ 11:58:00 │ command_failed           │ cmd-037│ missing_dep          │
│ 11:55:30 │ blocker_created          │ bl-012 │ permission           │
│ ...                                                      │
└──────────────────────────────────────────────────────────┘
```

**数据来源**：WebSocket 实时事件 + `GET /api/ralph/events`（如果后端提供历史查询）

**关键设计**：
- 可暂停/继续滚动（方便排查问题时仔细看）
- 可过滤事件类型
- 每条事件可展开看完整 data payload
- 高亮 `command_failed`、`blocker_created` 等异常事件

### 4.6 审批中心 `/ralph/approvals`（增强）

**定位**：保留现有结构，增强上下文信息。

**增强点**：
- PendingAction 卡片增加：关联 WorkUnit 当前状态、WorkUnit 标题、之前是否出现过同类 action
- Blocker 卡片增加：关联 WorkUnit 状态、Blocker 持续时间（创建至今多久了）
- 增加"全部已处理"历史视图（当前只展示未处理的）

```
┌──────────────────────────────────────────────┐
│ ⚠️ 危险操作                        2分钟前   │
│ wu-042 实现JWT登录接口  [当前状态: running]   │
│ 描述：该操作将删除 src/auth/ 目录下的旧代码    │
│ 影响文件：src/auth/legacy.ts, src/auth/old.ts │
│ [批准]  [拒绝]                                │
└──────────────────────────────────────────────┘
```

### 4.7 配置中心 `/ralph/settings`（新增）

**定位**：PRD 9.14/9.15/9.16 的前端落地。

**子页面**：

#### 4.7.1 LLM Provider 管理 `/ralph/settings/providers`

```
┌──────────────────────────────────────────────────────────┐
│ LLM Provider 管理                          [+ 新增 Provider] │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Claude (默认)                          [编辑] [测试] │ │
│ │ base_url: https://api.anthropic.com                  │ │
│ │ 默认模型: claude-opus-4-7                             │ │
│ │ 状态: ✅ 连通                                         │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ DeepSeek                               [编辑] [测试] │ │
│ │ base_url: https://api.deepseek.com                   │ │
│ │ 默认模型: deepseek-v4-pro                             │ │
│ │ 状态: ✅ 连通                                         │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ Qwen                                   [编辑] [测试] │ │
│ │ base_url: https://dashscope.aliyuncs.com/compatible...│ │
│ │ 默认模型: qwen-max                                    │ │
│ │ 状态: ⚠️ 未测试                                       │ │
│ └──────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ 模型路由规则                                              │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ brainstorm   → Claude (轻量模型)                      │ │
│ │ code_gen     → DeepSeek (强模型)                      │ │
│ │ review       → Claude (独立模型)                      │ │
│ │ test         → Qwen  (经济模型)                       │ │
│ └──────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ 降级策略                                                  │
│ 主 Provider 不可用时 → 自动切换至 [DeepSeek ▼]            │
└──────────────────────────────────────────────────────────┘
```

**新增/编辑 Provider 表单**：
```
┌─────────────────────────────────────┐
│ Provider 名称：[_______________]    │
│ API Base URL：[_______________]     │
│ API Key：    [_______________] 🔒   │
│ 默认模型：   [_______________]      │
│ 模型预设：                          │
│   temperature: [0.7___]             │
│   max_tokens:  [4096_]             │
│   top_p:       [1.0__]             │
│              [测试连通性] [保存]     │
└─────────────────────────────────────┘
```

**数据来源**：
- Provider 列表：`GET /api/ralph/settings/providers`（需后端新增）
- 连通性测试：`POST /api/ralph/settings/providers/test`
- 路由规则：`GET/PUT /api/ralph/settings/model-assignments`

#### 4.7.2 工具链配置 `/ralph/settings/tools`

```
┌──────────────────────────────────────────────────────────┐
│ 工具链配置                                                │
├──────────────────────────────────────────────────────────┤
│ 启用的工具：                                              │
│ ☑ Claude Code (默认)                                     │
│ ☐ Codex                                                   │
│ ☐ Aider                                                   │
│ ☐ Cline                                                   │
│                                                           │
│ 优先级策略：[Claude Code ▼] > [DeepSeek ▼]                │
│ 回退策略：  [自动切换 ▼]                                   │
└──────────────────────────────────────────────────────────┘
```

**数据来源**：`GET/PUT /api/ralph/settings/toolchain`（需后端新增），或直接读写 `.ralph/config/toolchain.yaml`

#### 4.7.3 Issue 治理策略 `/ralph/settings/issues`

```
┌──────────────────────────────────────────────────────────┐
│ Issue 治理策略                                            │
├──────────────────────────────────────────────────────────┤
│ Issue 源：                                                │
│ ☑ 本地文件 (.ralph/issues/)                               │
│ ☐ GitHub Issues (api.github.com/repos/...)               │
│                                                           │
│ 自动分类规则：                                            │
│ bug        → [auto_fix ▼]     严重级别 critical → 立即   │
│ feature    → [require_approval ▼]                        │
│ refactor   → [needs_investigation ▼]                     │
│ security   → [auto_fix ▼]     严重级别 critical → 立即   │
│ docs       → [ignore ▼]                                  │
│                                                           │
│ 拉取间隔：[手动 ▼]                                        │
└──────────────────────────────────────────────────────────┘
```

### 4.8 记忆系统 `/ralph/memory`（Phase 2 预留）

**定位**：展示记忆系统状态，不追求完全可视化，先做信息展示。

```
┌──────────────────────────────────────────────────────────┐
│ 记忆系统状态                                              │
├──────────────────────────────────────────────────────────┤
│ 短期记忆：10/10 条    中期记忆：23 条    长期记忆：156 条  │
│ 上次压缩：12:00        知识图谱节点：342  边：891         │
├──────────────────────────────────────────────────────────┤
│ 最近压缩记录：                                            │
│ 12:00 wu-038 → 摘要已生成 (1.2k tokens → 0.3k)           │
│ 11:45 wu-037 → 摘要已生成 (2.1k tokens → 0.4k)           │
└──────────────────────────────────────────────────────────┘
```

---

## 5. 全局组件

### 5.1 全局搜索

```
快捷键：Cmd/Ctrl + K

┌──────────────────────────────────────┐
│ 🔍 搜索 WorkUnit、命令、文件...       │
├──────────────────────────────────────┤
│ WorkUnit                             │
│   wu-042 实现JWT登录接口  [accepted] │
│   wu-040 JWT中间件重构    [running]  │
│ Commands                             │
│   cmd-039 accept_review   [completed]│
│ Files                                │
│   src/auth/login.ts                  │
└──────────────────────────────────────┘
```

### 5.2 通知 Toast

现有 sonner toast 保留，增加：
- 阻塞项创建时通知
- 审批请求时通知
- 命令失败时通知
- WebSocket 断连时通知

### 5.3 状态栏

底部固定状态栏（可选，Phase 2）：

```
┌──────────────────────────────────────────────────────────┐
│ ✅ 已连接 │ 运行中: 5 │ 待审批: 3 │ 最后更新: 12:03:54  │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Store 改动

### 6.1 新增 state 字段

```typescript
interface RalphState {
  // 新增
  recentEvents: RalphEvent[]       // 最近 50 条事件（FIFO）
  summary: RalphSummary | null     // 从 /api/ralph/summary 获取
  commands: RalphCommand[]         // 命令列表
  eventLogPaused: boolean          // 事件日志是否暂停滚动
  
  // Provider 配置（Phase 1）
  providers: LLMProvider[]
  modelAssignments: ModelAssignment[]
  
  // 搜索
  searchQuery: string
  searchResults: SearchResult[]
}
```

### 6.2 新增 actions

```typescript
interface RalphActions {
  fetchSummary: () => Promise<void>
  fetchCommands: (status?: string) => Promise<void>
  cancelCommand: (commandId: string) => Promise<void>
  fetchProviders: () => Promise<void>
  testProviderConnection: (providerId: string) => Promise<void>
  search: (query: string) => Promise<void>
  // ...
}
```

---

## 7. 路由设计

```typescript
// app/ralph/layout.tsx — 共享 Sidebar + TabBar
// 新增路由：

/ralph/page.tsx                    // 指挥中心
/ralph/work-units/page.tsx         // 工作单元列表
/ralph/work-units/[id]/page.tsx    // 工作单元详情（保留）
/ralph/commands/page.tsx           // 命令中心（新增）
/ralph/events/page.tsx             // 事件日志（新增）
/ralph/approvals/page.tsx          // 审批中心（保留增强）
/ralph/settings/page.tsx           // 配置中心入口（新增）
/ralph/settings/providers/page.tsx // LLM Provider（新增）
/ralph/settings/tools/page.tsx     // 工具链（新增）
/ralph/settings/issues/page.tsx    // Issue 治理（新增）
/ralph/memory/page.tsx             // 记忆系统（Phase 2）
```

---

## 8. 组件拆分

新增组件：

```
components/ralph/
├── command-card.tsx          // 命令卡片
├── command-list.tsx          // 命令列表
├── event-log.tsx             // 事件日志流
├── event-item.tsx            // 单条事件
├── global-search.tsx         // 全局搜索弹窗
├── provider-card.tsx         // Provider 卡片
├── provider-form.tsx         // Provider 表单
├── model-assignment-table.tsx // 模型路由表
├── issue-policy-form.tsx     // Issue 策略表单
├── status-chart.tsx          // 状态分布图
├── recent-activity.tsx       // 最近活动时间线
├── anchor-nav.tsx            // 详情页锚点导航
├── operation-bar.tsx         // 固定操作栏
├── stream-log.tsx            // 执行日志流
├── quick-entry.tsx           // 快速入口
├── status-bar.tsx            // 底部状态栏
└── memory-status.tsx         // 记忆系统状态
```

---

## 9. 实施优先级

### P0 — 立刻（补齐基础信息展示）

| 改动 | 说明 |
|------|------|
| 概览页重构为指挥中心 | 6 指标卡片 + 状态可视化 + 最近活动 + 快速入口 |
| 命令中心 `/ralph/commands` | 列表 + 状态过滤 + 取消操作 |
| 详情页执行日志 | 消费 `streamChunks` 数据 |
| 详情页锚点导航 | sticky 右侧导航 |
| 详情页固定操作栏 | 根据状态动态显示可用操作 |

### P1 — 下一步（补齐配置能力）

| 改动 | 说明 |
|------|------|
| 事件日志 `/ralph/events` | 实时流 + 暂停 + 过滤 |
| 配置中心 LLM Provider | 增删改查 + 连通性测试 |
| 全局搜索 | Cmd+K 弹窗 |
| 审批中心增强 | 关联 WorkUnit 上下文信息 |
| WorkUnit 列表独立页 | 搜索 + 排序 + 分页 |

### P2 — 后续（Phase 2 功能）

| 改动 | 说明 |
|------|------|
| 工具链配置 | ToolAdapter UI |
| Issue 治理策略 | 策略表单 |
| 记忆系统状态页 | 短期/中期/长期记忆统计 |
| 知识图谱可视化 | DAG 图展示依赖关系 |
| 趋势分析图 | 成功率变化、阻塞率变化 |

---

## 10. 与现有标准的兼容

本方案完全遵循 `RALPH_FRONTEND_STANDARDS.md`：

- 圆角策略：`rounded-none` 为主，`rounded-sm` 为辅
- 颜色系统：使用 `statusColor()` / `statusLabel()` 映射
- 组件模板：`'use client'` + props 类型 + store 读取
- 样式规范：`cn()` 合并类名
- 图标：`lucide-react`
- 测试：80%+ 覆盖率

本方案不推翻现有代码，而是在现有基础上：
1. 重构概览页
2. 新增缺失页面
3. 增强现有页面
4. 保持现有组件尽可能不变

---

## 11. 后端 API 缺口

以下 API 当前后端未提供，但前端设计依赖：

| API | 用途 | 优先级 |
|-----|------|--------|
| `GET /api/ralph/commands` | 命令列表（前端 API 层有 `listCommands` 但后端 routes.py 未实现） | P0 |
| `GET /api/ralph/events?limit=&offset=` | 事件历史查询 | P1 |
| `GET/POST/PUT/DELETE /api/ralph/settings/providers` | LLM Provider CRUD | P1 |
| `POST /api/ralph/settings/providers/test` | Provider 连通性测试 | P1 |
| `GET/PUT /api/ralph/settings/toolchain` | 工具链配置 | P2 |
| `GET/PUT /api/ralph/settings/issue-policy` | Issue 治理策略 | P2 |
| `GET /api/ralph/memory/status` | 记忆系统状态 | P2 |

---

## 12. 不改的东西

1. **Tab 机制**：保留，性能 ok，逻辑清晰
2. **Sidebar 折叠**：保留
3. **WebSocket 连接管理**：保留
4. **EvidenceViewer 双栏布局**：保留
5. **审批中心的批准/拒绝交互**：保留
6. **状态标签和颜色映射**：保留 `ralph-utils.ts` 的现有实现
7. **ChatDrawer**：保留，不影响主流程
