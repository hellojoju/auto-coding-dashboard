# Dashboard 架构设计文档 — Ralph Runtime Console

## 1. 背景与范围

当前 auto-coding 项目已构建完整的 Ralph 编排引擎（WorkUnit Engine + 状态机 + 证据链 + 独立审查 + 中文报告），但所有 Ralph 产生的数据在前端完全没有展示。现有 `dashboard-ui/` 是一个单页 Next.js 应用，展示的是旧 Feature 系统的数据。

**决策：废弃旧 Feature 系统，Dashboard 纯 Ralph 化。** 两套系统共存会增加维护成本，且 Ralph 是完整替代。

**本文档范围**：`Ralph Runtime Console`（Ralph 运行控制台），覆盖 WorkUnit 生成后的执行、审查、证据、报告、干预流程。

**不包含**：需求共创（brainstorm）、PRD 管理、story/dev task 拆解、execution plan 审批——这些是上游"需求 → WorkUnit"流程，属于完整产品 UI 的第二阶段。当前设计从 WorkUnit 开始。

**完整产品 UI 后续需补充的路由**：`/brainstorm`、`/prd`、`/specs`、`/plan`、"确认执行计划/生成 WorkUnit"入口。

**目标**：设计完整的 Dashboard 前端架构，提供用户能理解、能干预的 Ralph 可视化界面。

---

## 2. 整体架构决策

### 2.0 事实来源与系统边界

> **核心原则**：Dashboard 是 Ralph 的可视化控制台，不是 Ralph 的状态来源。

```
.ralph/ 目录
  ├── work_units/        → WorkUnit 事实来源（RalphRepository 唯一读写）
  ├── evidence/          → 证据文件事实来源
  ├── reviews/           → Review 结论事实来源
  ├── blockers/          → 阻塞项事实来源
  ├── transitions.jsonl  → 状态转换日志
  └── reports/           → 研发报告

ProjectStateRepository（旧系统保留）
  ├── commands           → 用户操作命令队列（Dashboard ↔ Ralph 桥梁）
  ├── events             → 事件总线（含 Ralph 事件转发）
  ├── agents             → Agent 实例状态
  └── chat               → PM 对话历史

旧 Feature API
  → 保留兼容期，不删除。Dashboard 读取端适配为 WorkUnit，写入端暂保留
  → 兼容期结束后统一迁移
```

**关键规则**：
1. WorkUnit/Evidence/Review/Blocker 的事实来源是 `.ralph/` + `RalphRepository`
2. commands/events/agents/chat 继续走 `ProjectStateRepository`
3. 前端所有用户操作（启动、停止、审批、返工）→ 创建 Command → Coordinator 消费 → 更新 `.ralph/`
4. REST API 不做状态转换，只做数据读取和 Command 创建
5. 旧 Feature API 保留兼容期，不立即删除

### 2.2 Command 驱动架构

> **核心原则**：前端所有用户操作不直接改 Ralph 状态，统一通过 Command 由 Coordinator/Engine 消费。

**Command 类型**：

| Command | 触发场景 | 后端处理 | 前置条件 |
|---------|---------|---------|---------|
| `start_run` | 点击"启动执行" | WorkUnitEngine.start() | 有待执行的 WorkUnit |
| `stop_run` | 点击"停止" | WorkUnitEngine.stop() | 引擎运行中 |
| `prepare_work_unit` | 创建新 WorkUnit | PlanGenerator + Harness 生成 | PRD 已冻结 |
| `execute_work_unit` | 执行单个 WorkUnit | WorkUnitEngine.execute(id) | 状态为 ready |
| `retry_work_unit` | NEEDS_REWORK 后重新提交 | 状态重置为 ready，重新执行 | 状态为 needs_rework |
| `resolve_blocker` | 用户解决阻塞项 | Blocker.resolved = true | Blocker 存在 |
| `expand_scope` | 范围争议时扩大允许范围 | 更新 harness scope_allow + 重新 preflight | scope_deny 违规 |
| `accept_review` | 审查通过、证据完整 | 状态 → accepted | review 通过 + 证据完整 |
| `request_rework` | 审查不通过或人工驳回 | 状态 → needs_rework + 原因 | 状态为 needs_review |
| `override_accept` | 人工强制接受（审计风险） | 状态 → accepted + reason | 任意状态，必须写 reason |
| `generate_report` | 点击"生成报告" | ReportGenerator.generate() | 有待总结的 WorkUnit |

**Command 数据结构**：

```typescript
interface RalphCommand {
  command_id: string
  idempotency_key: string     // 幂等键（前端生成，防重复提交）
  type: CommandType
  work_id?: string
  payload?: Record<string, any>
  status: 'pending' | 'applied' | 'rejected' | 'failed'
  created_at: string
  updated_at: string
  applied_by?: string
  error_message?: string
}
```

**Command 生命周期**：

```
pending → applied   (Coordinator 成功消费)
pending → rejected  (前置条件不满足)
pending → failed    (执行出错)
```

**API 端点**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ralph/commands` | GET | 列出 Command |
| `/api/ralph/commands` | POST | 创建 Command（前端唯一写入点）|
| `/api/ralph/commands/:id` | GET | 查询 Command 状态 |

**幂等性保证**：
- 前端每次操作生成唯一 `idempotency_key`
- 后端按 key 去重，相同 key 返回已有结果
- 刷新页面后重试失败 Command

### 2.3 审批/干预中心

> **核心原则**：`needs_review` 由独立 review agent 自动处理，人工只处理异常分支。否则系统退化成"每步等人点"。

**AI Review（自动）**：
- WorkUnit 进入 `needs_review` → ReviewManager 自动触发独立审查
- 审查结论：通过 → 状态自动转 `accepted`；不通过 → 状态转 `needs_rework`
- 全程无需人工介入

**人工审批（异常分支）**：

| 类型 | 触发条件 | 操作 |
|------|---------|------|
| 危险操作 | Permission Guard BLOCKED | 批准 / 拒绝 |
| 范围争议 | harness scope_deny 违规 | 扩大范围 / 维持原范围 |
| 验收分歧 | Review 不通过但用户认为应接受 | 强制接受（写 reason，审计记录）/ 接受返工 |
| 依赖缺失 | 上游 WorkUnit 未完成导致下游阻塞 | 标记已满足 / 跳过 |
| 执行异常 | Command 连续失败 | 查看错误 / 重试 / 终止 |
| 主动干预 | 用户主动暂停/恢复 | 暂停 / 恢复 / 终止 |

**审批中心 API**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ralph/pending-actions` | GET | 获取所有待干预项 |
| `/api/ralph/commands` | POST | 创建审批 Command |

**前端入口**：
- Sidebar 增加"审批"项，显示未处理数量徽章（仅人工待处理项，不含 AI review 中）
- 概览页增加"待干预"区块
- 每个待处理项卡片：类型 + 关联 WorkUnit + 原因 + 操作按钮

### 2.4 布局模式：左侧可收起 Sidebar + Tab 页

```
┌──────────────────────────────────────────────────────────────────┐
│  Sidebar     │  Tab 栏: [概览][工作单元 ▾][报告][日志][Agent][+]  │
│  [可收起]    ├───────────────────────────────────────────────────┤
│              │                                                   │
│  📊 概览     │                                                   │
│  🔬 工作单元 │        当前 Tab 的页面内容                          │
│  📄 报告     │        可并排打开多个 WorkUnit 详情页               │
│  📡 日志     │        关闭不需要的页面，保持工作区整洁              │
│  👥 Agent    │                                                   │
│  ⚙️ 设置     │                                                   │
└──────────────┴───────────────────────────────────────────────────┘
```

**Sidebar**：
- 展开宽度 240px，收起 64px（仅显示图标 + hover tooltip）
- 默认展开，手动收起后状态存入 localStorage
- 图标 + 中文标签

**Tab 页**：
- 二级导航 + 可关闭 Tab，符合 IDE 心智模型
- Tab 标题格式：`W-003: list_reports()` 最多 20 字符
- Tab 颜色区分状态：accepted 绿色、blocked 红色、needs_review 黄色、其余灰色
- 上限 8 个 Tab，超限提示先关一个
- 刷新页面后保留最近打开的 Tab（localStorage 持久化）

**优势**：
- 快速切换不同 WorkUnit 详情，不用来回跳转
- 关闭不需要的页面，保持工作区整洁
- 长信息内容（WorkUnit 详情有 6 个区块）不会被其他导航元素挤压

### 2.2 路由设计

```
/                      → 概览仪表盘
/workunits             → WorkUnit 列表（6 状态看板）
/workunits/:id         → WorkUnit 详情（在 Tab 中打开）
/reports               → 研发报告列表 + 预览
/logs                  → 实时日志 + 事件流
/agents                → Agent 集群管理
/approvals             → 审批/干预中心
/settings              → 系统设置
```

点击 Sidebar 导航项 → 如果对应 Tab 未打开则新建 Tab 并激活，已存在则激活已有 Tab。
点击 WorkUnit 卡片 → 新建 `/workunits/:id` Tab。

**URL 与 Tab 状态关系**：
- URL 表示当前 active tab（支持深链、刷新、分享）
- localStorage 只保存打开过的 Tab 列表（恢复用），不作为事实来源
- 刷新页面后：从 localStorage 恢复 Tab 列表，URL 指向的 Tab 为 active

### 2.3 数据流

```
FastAPI Backend (dashboard/api/routes.py)
    │
    ├── Ralph API（只读 .ralph/）
    │   ├── /api/ralph/workunits         → WorkUnit 列表（含状态统计）
    │   ├── /api/ralph/workunits/:id     → WorkUnit 详情（含 harness + context_pack）
    │   ├── /api/ralph/transitions/:id   → 状态转换历史
    │   ├── /api/ralph/evidence/:id      → 证据列表
    │   ├── /api/ralph/evidence/:id/file → 证据文件内容（安全受限）
    │   ├── /api/ralph/reviews/:id       → Review 结果
    │   ├── /api/ralph/reports           → 报告列表
    │   ├── /api/ralph/reports/:name     → 报告内容
    │   ├── /api/ralph/reports/generate  → 生成新报告
    │   ├── /api/ralph/blockers          → 阻塞项
    │   └── /api/ralph/pending-actions   → 待干预项汇总
    │
    ├── Command API（写入 .ralph/ 的唯一入口）
    │   ├── /api/ralph/commands          → 创建 Command（GET 列表 + POST 创建）
    │   └── /api/ralph/commands/:id      → 查询 Command 状态
    │
    ├── ProjectState API（旧系统保留）
    │   ├── /api/agents                  → Agent 实例状态
    │   ├── /api/events                  → 事件流
    │   └── /api/chat                    → PM 对话
    │
    └── WebSocket
        └── /ws/dashboard                → 实时事件推送（含 Ralph 事件转发）

Frontend (Next.js)
    │
    ├── Zustand Store（全局状态）
    │   ├── ralphState: WorkUnit + Evidence + Review + Reports + Blockers
    │   ├── commands: RalphCommand[]      ← Command 队列
    │   ├── pendingActions: PendingAction[] ← 待干预项
    │   ├── agents: AgentInstance[]
    │   ├── events: EventStreamItem[]
    │   ├── tabs: TabState[]              ← Tab 状态管理
    │   └── connectionStatus: WebSocket 连接
    │
    ├── Layout
    │   ├── Sidebar（可收起 + 审批徽章）
    │   └── TabBar（可关闭 Tab）
    │
    ├── Pages
    │   ├── DashboardHome   → 概览
    │   ├── WorkUnitList    → WorkUnit 列表
    │   ├── WorkUnitDetail  → WorkUnit 详情
    │   ├── Approvals       → 审批/干预中心
    │   ├── Reports         → 研发报告
    │   ├── LogStream       → 实时日志
    │   ├── AgentManager    → Agent 管理
    │   └── Settings        → 系统设置
    │
    └── Shared Components
        ├── StatusBadge          → 状态标签
        ├── EvidenceList         → 证据文件列表
        ├── EvidenceViewer       → 证据内容查看器（模态框）
        ├── ReviewCard           → Review 结论卡片
        ├── TransitionTimeline   → 状态转换时间线
        ├── ContextPackViewer    → 上下文包展示
        ├── ApprovalCard         → 审批项卡片
        ├── LogTable             → 日志表格
        ├── AgentCard            → Agent 信息卡片
        └── MarkdownRenderer     → Markdown 渲染
```

---

## 3. 页面设计

### 3.1 概览页 (/)

**目的**：一眼看到系统整体健康状态。

```
┌────────────────────────────────────────────────────────────┐
│  项目概览                                          [刷新]  │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ 🟢 已验收 │  │ 🟡 执行中 │  │ 🔴 阻塞   │  │ 📊 成功率  │  │
│  │   12     │  │    3     │  │    1     │  │   94.2%   │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                                                             │
│  ┌──────────── 最近活动 ──────────────┐                     │
│  │ 12:01  W-003  → accepted     ✅    │                     │
│  │ 11:58  W-005  → needs_review 🔍   │                     │
│  │ 11:40  W-002  → blocked      ⚠️    │                     │
│  └────────────────────────────────────┘                     │
│                                                             │
│  ┌──────────── 执行引擎 ──────────────┐                     │
│  │ ● 运行中    已验收 12 / 总计 16     │ [停止] [生成报告]  │
│  └────────────────────────────────────┘                     │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**交互**：
- 点击统计卡片 → 在 Tab 中打开 WorkUnit 列表并过滤对应状态
- 点击活动条目 → 在 Tab 中打开对应 WorkUnit 详情
- 执行引擎按钮 → 创建 `stop_run` / `start_run` Command，WebSocket 推送状态更新
- 生成报告 → 创建 `generate_report` Command，完成后在 Tab 中打开报告页

---

### 3.2 WorkUnit 列表页 (/workunits)

**目的**：展示所有 WorkUnit，按状态分组。

```
┌───────────────────────────────────────────────────────────┐
│  工作单元                              [搜索] [过滤 ▾]    │
│                                                           │
│  已验收(12)  执行中(3)  待审查(1)  需返工(0)  已失败(1) 阻塞(1)│
│  ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐  ┌─────┐│
│  │W-001│  │W-003│  │W-008│  │     │  │W-002│  │W-009││
│  │W-004│  │W-005│  │     │  │     │  │     │  │     ││
│  │W-006│  │W-007│  │     │  │     │  │     │  │     ││
│  │...  │  │     │  │     │  │     │  │     │  │     ││
│  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘│
└───────────────────────────────────────────────────────────┘
```

**卡片内容**：work_id + 标题、work_type 标签、状态标签、producer_role、依赖指示。

**交互**：点击卡片 → 在 Tab 中打开 `/workunits/:id`。状态筛选点击 → 仅显示该状态。

---

### 3.3 WorkUnit 详情页 (/workunits/:id)

**目的**：单个工作单元的完整信息。信息量大，所以在独立 Tab 中展示。

**Tab 标题**：`W-003: list_reports()` + 状态颜色点

**页面内容**：

```
┌──────────────────────────────────────────────────────────┐
│  W-003: ReportGenerator 增加 list_reports()        [×]  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─── 基本信息 ────────────────────────────────────────┐ │
│  │ 状态: ● accepted   类型: 开发   生成者: backend     │ │
│  │ 目标: 在 ReportGenerator 中增加 list_reports()...  │ │
│  │ 范围: ralph/report_generator.py                    │ │
│  │ 禁止: .env, .env.*, credentials                    │ │
│  │ 依赖: 无                                            │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── 状态时间线 ──────────────────────────────────────┐ │
│  │ draft → ready → running → needs_review → accepted  │ │
│  │ 09:01   09:02     09:05       09:12          09:15 │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── 验收标准 ────────────────────────────────────────┐ │
│  │ ✅ 方法返回报告 Path 列表                             │ │
│  │ ✅ 支持 since 参数过滤                                │ │
│  │ ✅ 支持 until 参数过滤                                │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── 证据文件 ────────────────────────────────────────┐ │
│  │ 📄 diff.txt (2.3 KB)        [查看]                  │ │
│  │ 📄 files_changed.txt (18 B)  [查看]                 │ │
│  │ 📄 test_output.txt (24 B)    [查看]                 │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── Review 结论 ─────────────────────────────────────┐│
│  │ 审查: 功能完整性   结论: ✅ 通过   建议: 接受        │ │
│  │ 审查者: reviewer-1   harness 检查: ✅               │ │
│  │ 证据: diff.txt, files_changed.txt, test_output.txt │ │
│  │ 问题: (无)                                          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── Harness 约束 ────────────────────────────────────┐ │
│  │ 目标: 在 ReportGenerator 中增加 list_reports()     │ │
│  │ 上下文: PRD, 接口文档   验收者: qa                   │ │
│  │ 必需证据: diff.txt, test_output.txt                 │ │
│  │ 停止条件: 批量删除                                   │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── ContextPack 上下文包 ────────────────────────────┐ │
│  │ Token 估算: 2,840  (预算: 8,000)  ● 正常             │ │
│  │ ┌─ 受信数据 ─────────────────────────────────────┐  │ │
│  │ │ • PRD §4.2 ReportGenerator 接口定义              │  │ │
│  │ │ • src/ralph/report_generator.py (180行) 摘要     │  │ │
│  │ │ • 上游 W-001: PRD 解析完成                       │  │ │
│  │ └────────────────────────────────────────────────┘  │ │
│  │ ┌─ 非受信数据 ───────────────────────────────────┐  │ │
│  │ │ • 外部 API 文档链接                              │  │ │
│  │ └────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─── 风险说明 ────────────────────────────────────────┐ │
│  │ (无)                                                │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**交互**：
- 点击证据文件 → 弹出 EvidenceViewer 模态框（diff 语法高亮）
- 状态时间线节点悬停 → 显示转换原因 + 时间 + 角色
- NEEDS_REWORK 状态 → 底部显示"重新提交"按钮

---

### 3.4 审批/干预中心 (/approvals)

**目的**：集中展示所有需要人类决策的项，是 Ralph "安全无人值守" 的核心入口。

```
┌───────────────────────────────────────────────────────────┐
│  审批中心                                        [刷新]   │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─── 统计 ───────────────────────────────────────────┐  │
│  │ 危险操作: 1    范围争议: 1    执行异常: 1    总计: 3  │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─── 待干预项 ───────────────────────────────────────┐  │
│  │                                                     │  │
│  │ ┌─ W-002: API 重构 ───────────────────────────┐   │  │
│  │ │ 类型: 危险操作 (BLOCKED)                       │  │  │
│  │ │ 原因: scope_deny 违规 — 尝试修改 .env          │  │  │
│  │ │ [批准操作] [拒绝操作] [扩大范围]                │  │  │
│  │ └───────────────────────────────────────────────┘   │  │
│  │                                                     │  │
│  │ ┌─ W-015: 数据库迁移 ─────────────────────────┐    │  │
│  │ │ 类型: 范围争议                                │  │  │
│  │ │ 原因: 需要修改 config/db.yml 但不在 scope 内   │  │  │
│  │ │ [扩大范围] [维持原范围]                         │  │  │
│  │ └───────────────────────────────────────────────┘    │  │
│  │                                                     │  │
│  │ ┌─ W-009: 缓存优化 ───────────────────────────┐    │  │
│  │ │ 类型: 执行异常                                │  │  │
│  │ │ 原因: Command execute_work_unit 连续失败 3 次  │  │  │
│  │ │ [查看错误] [重试] [终止]                        │  │  │
│  │ └───────────────────────────────────────────────┘    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─── 历史已处理 ─────────────────────────────────────┐  │
│  │ 04-30  W-005  批准操作    04-29  W-003  解决阻塞  │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**交互**：
- 点击"批准操作" → 创建 `accept_review` Command → WebSocket 推送
- 点击"拒绝操作" → 创建 `request_rework` Command + 原因 → 状态 → needs_rework
- 点击"扩大范围" → 创建 `expand_scope` Command + payload 新 scope → 重新 preflight
- 点击"维持原范围" → 创建 `request_rework` Command → 不修改 scope
- 点击"重试" → 创建 `retry_work_unit` Command
- 点击"终止" → 创建 `stop_run` Command
- 历史已处理可折叠，默认收起

---

### 3.5 研发报告页 (/reports)

**目的**：查看和管理 Ralph 生成的中文研发报告。

```
┌───────────────────────────────────────────────────────────┐
│  研发报告                                  [生成新报告]    │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ 2026-05-01 07:12  Ralph 自举验证报告  [查看] [下载] │ │
│  │ 2026-04-30 18:30  Sprint 1 完成报告   [查看] [下载] │ │
│  │ 2026-04-29 14:15  Phase 2 验收报告    [查看] [下载] │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌──────────── 报告预览（点击"查看"后展开）─────────────┐ │
│  │                                                      │ │
│  │  # Ralph 自举验证报告                                │ │
│  │  ## 任务完成情况                                     │ │
│  │  - 已验收: 1 个                                      │ │
│  │  ...                                                 │ │
│  │                                                      │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

**交互**：点击"查看" → 下方展开 Markdown 渲染预览。点击"下载" → 下载 .md 文件。

---

### 3.6 实时日志页 (/logs)

**目的**：实时查看所有 Ralph 事件。

```
┌───────────────────────────────────────────────────────────┐
│  实时日志流                              [清空] [导出]    │
│  ┌──────────── 过滤 ───────────────────────────────────┐ │
│  │ [严重: 全部▾] [搜索] [自动滚动 ✓]                    │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  12:01:34  INFO    work_unit  W-003 → accepted           │
│  12:01:30  INFO    review     W-003: 审查通过            │
│  11:58:15  WARN    harness    W-008: postflight 警告     │
│  11:40:02  ERROR   blocker    W-002: scope 违规          │
│  ...                                                      │
└───────────────────────────────────────────────────────────┘
```

**交互**：点击日志条目 → 在 Tab 中打开关联的 WorkUnit 详情。

---

### 3.7 Agent 集群管理页 (/agents)

**目的**：Agent 实例状态、静默检测、进程管理。

```
┌───────────────────────────────────────────────────────────┐
│  Agent 管理                                      [刷新]   │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🏗️  Architect       ● 工作中    当前: W-003        │  │
│  │                      静默: 正常   PID: 12345       │  │
│  │                      已完成: 12    角色: producer   │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 🔍 QA             ○ 空闲       等待中              │  │
│  │                      静默: 需要关注  PID: 12346     │  │
│  │                      已完成: 8     角色: reviewer   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  [暂停]  [恢复]  [中断]  [强制终止]  [查看历史]            │
└───────────────────────────────────────────────────────────┘
```

---

### 3.8 系统设置页 (/settings)

```
┌───────────────────────────────────────────────────────────┐
│  系统设置                                                  │
│  ┌─── 项目路径 ─────────────────────────────────────────┐ │
│  │ 工作目录: /Users/jieson/auto-coding/project            │ │
│  │ [浏览]                                                │ │
│  └──────────────────────────────────────────────────────┘ │
│  ┌─── Agent 池 ─────────────────────────────────────────┐ │
│  │ 最大并发: 3    超时: 600s    重试: 3                  │ │
│  │ [保存]                                                │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

---

## 4. Tab 状态管理

### 4.1 Tab 数据结构

```typescript
interface Tab {
  id: string              // tab-1717190400000
  type: 'overview' | 'workunits' | 'workunit-detail' | 'reports' | 'logs' | 'agents' | 'settings'
  label: string           // '概览' | '工作单元' | 'W-003: list_reports()' | '报告' | ...
  path: string            // '/' | '/workunits' | '/workunits/W-003' | '/reports' | ...
  statusColor?: string    // WorkUnit 状态颜色
  closable: boolean       // 概览页不可关闭
}
```

### 4.2 Tab 操作

| 操作 | 行为 |
|------|------|
| 新建 | Sidebar 点击 → 如果 Tab 已存在则激活，否则新建并激活 |
| 关闭 | 关闭当前 Tab → 激活左侧相邻 Tab |
| 超限 | 已有 8 个 Tab 时新建 → 弹出 Toast 提示 |
| 持久化 | 页面刷新后从 localStorage 恢复最近的 Tab |
| 更新 | WorkUnit 状态变更 → 更新对应 Tab 的状态颜色 |

---

## 5. 组件树

```
App (layout.tsx)
├── Sidebar（可收起）
│   ├── SidebarToggle
│   ├── NavItem × 7 (+ 审批徽章)
│   └── ConnectionStatus
│
├── TabBar
│   ├── Tab × N (closable, statusColor)
│   └── NewTabButton (+)
│
└── TabContent
    ├── Route: / (DashboardHome)
    │   ├── RunStatusHeader           ← P0 最小概览
    │   └── PendingActionsSummary    ← 新增
    │
    ├── Route: /workunits (WorkUnitList)
    │   ├── WorkUnitHeader (搜索 + 过滤)
    │   ├── WorkUnitColumn × 6
    │   │   └── WorkUnitCard × N
    │   └── EmptyState
    │
    ├── Route: /workunits/:id (WorkUnitDetail)
    │   ├── WorkUnitBasicInfo
    │   ├── TransitionTimeline
    │   ├── AcceptanceCriteriaList
    │   ├── EvidenceList + EvidenceViewer (模态框)
    │   ├── ReviewCard
    │   ├── ContextPackViewer          ← 新增
    │   ├── HarnessConstraints
    │   └── RiskNotes
    │
    ├── Route: /approvals (Approvals)  ← 新增
    │   ├── ApprovalStats
    │   ├── ApprovalCard × N
    │   └── ApprovalHistory
    │
    ├── Route: /reports (Reports)
    │   ├── ReportList
    │   ├── ReportPreview (MarkdownRenderer)
    │   └── GenerateReportButton
    │
    ├── Route: /logs (LogStream)
    │   ├── LogFilterBar
    │   └── LogTable
    │
    ├── Route: /agents (AgentManager)
    │   ├── AgentCard × N
    │   └── AgentActionBar
    │
    └── Route: /settings (Settings)
        ├── ProjectPathConfig
        └── AgentPoolConfig
```

---

## 6. 跨页面交互

### 6.1 导航流

```
概览
  ├── 点击统计卡片 → Tab 打开 WorkUnit 列表（过滤对应状态）
  ├── 点击活动条目 → Tab 打开 WorkUnit 详情
  └── 点击生成报告 → 调用 Command API → Tab 打开报告页

WorkUnit 列表
  ├── 点击卡片 → Tab 打开 WorkUnit 详情
  └── 点击状态筛选 → 仅显示该状态

WorkUnit 详情
  ├── 点击证据 → EvidenceViewer 模态框
  ├── 点击依赖 → Tab 打开关联 WorkUnit
  ├── 点击 ContextPack 文件 → 只读查看
  └── 需要操作 → 创建 Command → 审批中心处理

审批中心
  ├── 批准操作 → 创建 `accept_review` Command → 状态 → accepted
  ├── 拒绝操作 → 创建 `request_rework` Command + 原因 → 状态 → needs_rework
  ├── 扩大范围 → 创建 `expand_scope` Command + payload 新 scope
  ├── 维持原范围 → 创建 `request_rework` Command
  ├── 重试 → 创建 `retry_work_unit` Command
  ├── 终止 → 创建 `stop_run` Command
  └── 点击关联 WorkUnit → Tab 打开 WorkUnit 详情

Agent 管理
  ├── 暂停/恢复 → 创建 Command → WebSocket 推送
  └── 查看历史 → 侧边抽屉显示该 Agent 的 WorkUnit 历史

报告
  ├── 查看 → 展开 Markdown 预览
  └── 下载 → 下载 .md 文件

日志
  └── 点击条目 → Tab 打开关联 WorkUnit 详情
```

### 6.2 WebSocket 事件契约

> **核心原则**：所有状态变更通过 WebSocket 推送，前端不轮询。

**统一事件 Payload**：

```typescript
interface RalphEvent {
  event_id: string          // UUID
  type: RalphEventType
  work_id?: string          // 关联 WorkUnit
  actor_role?: string       // 'scheduler' | 'producer' | 'reviewer' | 'user' | 'system'
  from_status?: WorkUnitStatus
  to_status?: WorkUnitStatus
  reason?: string           // 状态转换原因
  timestamp: string         // ISO 8601
  payload: Record<string, any>  // 事件特定数据
  sequence: number          // 单调递增序列号（去重用）
  last_event_id?: string    // 前一个事件 ID（断线续传用）
}

type RalphEventType =
  | 'work_unit_transition'
  | 'evidence_saved'
  | 'review_completed'
  | 'agent_status_changed'
  | 'blocker_created'
  | 'blocker_resolved'
  | 'report_generated'
  | 'command_applied'
  | 'command_rejected'
  | 'command_failed'
  | 'approval_required'     // 需要人工干预
  | 'heartbeat'             // 心跳
```

**断线恢复**：
- 前端维护 `last_sequence`（单调递增整数），断线重连后发送该值
- 后端从 `sequence > last_sequence` 补发所有未接收事件
- 前端按 `sequence` 递增应用事件，丢弃小于等于 `last_sequence` 的重复事件
- `event_id`（UUID）仅用于日志追踪和调试，不作为恢复游标

**WebSocket 事件联动**：

| 事件类型 | 更新内容 | 影响的 Tab |
|---------|---------|-----------|
| `work_unit_transition` | WorkUnit 状态 | 列表 Tab 重排 + 详情 Tab 状态颜色 + 概览统计 |
| `evidence_saved` | 证据列表 | 详情 Tab 证据区 |
| `review_completed` | Review 结论 | 详情 Tab Review 区 |
| `agent_status_changed` | Agent 状态 | Agent Tab + 概览 |
| `blocker_created` | 阻塞项 | 概览统计 + 列表 Tab + 审批徽章 |
| `blocker_resolved` | 阻塞项解决 | 审批中心 + 概览 |
| `report_generated` | 新报告 | 报告 Tab + 概览活动流 |
| `command_applied` | Command 成功 | 所有 Tab（全局状态）|
| `command_rejected` | Command 被拒 | 触发 Tab 的审批中心 |
| `command_failed` | Command 失败 | 触发 Tab 的审批中心 |
| `approval_required` | 需要人工干预 | 审批徽章 + 概览待干预区 |

---

## 7. 新增 API 端点

Ralph API 需要在 `dashboard/api/routes.py` 中新增：

### 7.1 只读端点（.ralph/ 数据）

| 端点 | 方法 | 功能 | 数据来源 |
|------|------|------|----------|
| `/api/ralph/workunits` | GET | 列表（含状态统计） | RalphRepository.list_work_units() |
| `/api/ralph/workunits/:id` | GET | 详情（含 harness + context_pack） | RalphRepository.get_work_unit() |
| `/api/ralph/transitions/:id` | GET | 状态转换历史 | transitions.jsonl |
| `/api/ralph/evidence/:id` | GET | 证据列表 | RalphRepository.list_evidence() |
| `/api/ralph/evidence/:id/file` | GET | 证据文件内容（**安全受限**） | 受限文件读取 |
| `/api/ralph/reviews/:id` | GET | Review 结果 | RalphRepository.list_reviews() |
| `/api/ralph/reports` | GET | 报告列表 | ReportGenerator.list_reports() |
| `/api/ralph/reports/:name` | GET | 报告内容 | 读取报告文件 |
| `/api/ralph/blockers` | GET | 阻塞项列表 | RalphRepository.list_blockers() |
| `/api/ralph/pending-actions` | GET | 待干预项汇总 | RalphRepository + Command 状态 |

### 7.2 Command 端点（唯一写入入口）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ralph/commands` | GET | 列出 Command |
| `/api/ralph/commands` | POST | 创建 Command（含 `idempotency_key`） |
| `/api/ralph/commands/:id` | GET | 查询 Command 状态 |

### 7.3 Evidence 文件读取安全约束

`/api/ralph/evidence/:id/file` 必须满足：

1. **用 `evidence_id` 读取，不接受任意 file path**
   - 后端通过 `RalphRepository.get_evidence(evidence_id)` 获取记录
   - 从记录中取 `file_path`，不使用前端传入的路径

2. **路径校验**
   - 文件路径必须在 `.ralph/evidence/` 或明确允许目录内
   - 拒绝 `..` 路径穿越、绝对路径、符号链接

3. **大文件截断/分页**
   - 超过 1MB 返回前 1MB + `truncated: true` 标记
   - 支持 `?offset=N&limit=M` 分页读取

4. **敏感信息 redaction**
   - `.env`、token、credential 文件直接拒绝
   - diff 内容中的 API key、密码做 `***REDACTED***` 替换

5. **分类型展示**（前端）
   - `diff` → 语法高亮 diff 视图
   - `test_output` → 终端样式文本
   - `screenshot` → 图片展示
   - `trace` → JSON/tree 视图

---

## 8. TypeScript 类型扩展

在 `dashboard-ui/lib/types.ts` 中新增：

```typescript
// Ralph WorkUnit 状态
export type WorkUnitStatus =
  | 'draft' | 'ready' | 'running' | 'needs_review'
  | 'accepted' | 'needs_rework' | 'blocked' | 'failed'

// WorkUnit（对齐 ralph/schema/work_unit.py 全部字段）
export interface WorkUnit {
  work_id: string
  work_type: string
  title: string
  background: string
  target: string
  scope_allow: string[]
  scope_deny: string[]
  dependencies: string[]
  input_files: string[]
  expected_output: string
  acceptance_criteria: string[]
  test_command: string
  rollback_strategy: string
  task_harness?: TaskHarness
  context_pack?: ContextPack
  assumptions: string[]
  impact_if_wrong: string
  risk_notes: string
  status: WorkUnitStatus
  producer_role: string
  reviewer_role: string
  created_at?: string
  updated_at?: string
}

// TaskHarness（对齐 ralph/schema/task_harness.py）
export interface TaskHarness {
  harness_id: string
  task_goal: string
  context_sources: string[]
  context_budget: string
  allowed_tools: string[]
  denied_tools: string[]
  scope_allow: string[]
  scope_deny: string[]
  preflight_checks: string[]
  checkpoints: string[]
  validation_gates: string[]
  evidence_required: string[]
  rollback_strategy: string
  stop_conditions: string[]
  reviewer_role: string
}

// 证据
export interface Evidence {
  evidence_id: string
  work_id: string
  evidence_type: string
  file_path: string
  description: string
}

// Review 结论
export interface ReviewResult {
  work_id: string
  reviewer_context_id: string
  review_type: string
  conclusion: string
  recommended_action: string
  criteria_results: CriterionResult[]
  issues_found: Issue[]
  evidence_checked: string[]
  harness_checked: boolean
}

export interface CriterionResult {
  criterion: string
  passed: boolean
  evidence: string
  notes: string
}

export interface Issue {
  description: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  suggested_action: string
  file_path: string
}

// 状态转换记录
export interface TransitionRecord {
  work_id: string
  from_status: WorkUnitStatus
  to_status: WorkUnitStatus
  actor_role: string
  reason: string
  timestamp: string
}

// 报告
export interface Report {
  name: string
  title: string
  generated_at: string
  content: string
}

// ContextPack 上下文包
// 注意：后端 Python schema 中字段名为 `prd片段`，序列化时需做字段别名映射
export interface ContextPack {
  work_id: string
  task_description: string
  prd_fragment: string            // 后端字段: prd片段（序列化时 alias）
  interface_contracts: string[]
  file_summaries: Record<string, string>
  upstream_results: string[]
  risks_and_constraints: string[]
  acceptance_criteria: string[]
  scope_deny: string[]
  trusted_data: string[]
  untrusted_data: string[]
}

// Command 命令
export type CommandType =
  | 'start_run' | 'stop_run'
  | 'prepare_work_unit' | 'execute_work_unit'
  | 'retry_work_unit' | 'resolve_blocker' | 'expand_scope'
  | 'accept_review' | 'request_rework' | 'override_accept'
  | 'generate_report'

export interface RalphCommand {
  command_id: string
  idempotency_key: string
  type: CommandType
  work_id?: string
  payload?: Record<string, any>
  status: 'pending' | 'applied' | 'rejected' | 'failed'
  created_at: string
  updated_at: string
  applied_by?: string
  error_message?: string
}

// Ralph WebSocket 事件
export type RalphEventType =
  | 'work_unit_transition' | 'evidence_saved' | 'review_completed'
  | 'agent_status_changed' | 'blocker_created' | 'blocker_resolved'
  | 'report_generated' | 'command_applied' | 'command_rejected'
  | 'command_failed' | 'approval_required' | 'heartbeat'

export interface RalphEvent {
  event_id: string          // UUID，日志追踪用
  type: RalphEventType
  work_id?: string
  actor_role?: string
  from_status?: WorkUnitStatus
  to_status?: WorkUnitStatus
  reason?: string
  timestamp: string
  payload: Record<string, any>
  sequence: number          // 单调递增游标，断线恢复用
}

// 待干预项（仅异常分支，不含 AI review 中）
export interface PendingAction {
  action_id: string
  type: 'dangerous_op' | 'scope_expansion' | 'review_dispute' | 'missing_dep' | 'execution_error' | 'manual_intervention'
  work_id: string
  reason: string
  created_at: string
  payload?: Record<string, any>
}

// Tab 状态
export interface Tab {
  id: string
  type: 'overview' | 'workunits' | 'workunit-detail' | 'approvals' | 'reports' | 'logs' | 'agents' | 'settings'
  label: string
  path: string
  statusColor?: string
  closable: boolean
}

// Zustand Store
export interface DashboardStore {
  workUnits: WorkUnit[]
  commands: RalphCommand[]
  pendingActions: PendingAction[]
  agents: AgentInstance[]
  events: EventStreamItem[]
  ralphEvents: RalphEvent[]
  tabs: Tab[]
  activeTabId: string
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
  lastSequence: number       // 断线恢复游标
  // Actions
  addTab: (tab: Omit<Tab, 'id'>) => void
  closeTab: (tabId: string) => void
  activateTab: (tabId: string) => void
  createCommand: (cmd: Omit<RalphCommand, 'command_id' | 'status' | 'created_at' | 'updated_at'>) => Promise<void>
  applyEvent: (event: RalphEvent) => void
  restoreFromSequence: (lastSeq: number) => Promise<void>  // 断线恢复
}
```

---

## 9. 实现优先级

### P0 — 核心功能（必须先有）
1. Sidebar 布局（可收起）+ 审批徽章
2. Tab 状态管理（Zustand + localStorage，URL 为 active tab 事实来源）
3. **后端 Ralph 只读 API**（列表 + 详情 + 证据 + Review + 转换历史 + Blocker + PendingActions）
4. **后端 Command API**（创建 + 查询，含幂等键）
5. `RunStatusHeader` 组件 — 概览页的最小替代，展示：
   - Ralph 当前阶段（运行中 / 空闲 / 等待人工干预）
   - 运行状态 ● 运行中 / ○ 已停止
   - 是否有待处理项（直接链接到审批中心）
   - 下一个动作建议（如"W-005 待审查" / "3 项工作需要干预"）
6. `/workunits` — WorkUnit 列表（6 状态看板）
7. `/workunits/:id` — WorkUnit 详情（含 Harness + ContextPack + Evidence + Review）
8. `/approvals` — 审批/干预中心
9. EvidenceViewer 组件（安全受限的文件查看器）
10. WebSocket：`work_unit_transition` 事件推送 + 断线恢复

### P1 — 增强功能
10. 概览页（统计卡片 + 最近活动 + 执行引擎）
11. TransitionTimeline 组件
12. `/reports` — 研发报告
13. Command 状态轮询 + 失败重试

### P2 — 完整功能
14. `/agents` — Agent 管理
15. `/logs` — 统一日志流
16. `/settings` — 系统设置

---

## 10. 技术约束

1. **纯 Ralph**：旧 Feature 系统废弃，不复用。`ProjectStateRepository` 保留管 commands/events/agents/chat
2. **Command 驱动**：前端所有写入操作 → 创建 Command → Coordinator 消费，不直接改 Ralph 状态
3. **WebSocket 优先**：所有状态变更通过 WebSocket 推送，支持断线恢复（`last_event_id` + `sequence`）
4. **TypeScript 严格模式**：完整类型定义
5. **Tailwind CSS 复用**：新组件复用现有 tech-* 类
6. **Zustand Store**：Tab 状态 + Ralph 数据 + Command 队列统一管理
7. **localStorage 持久化**：Tab 列表 + Sidebar 收起状态，不作为事实来源

---

## 11. Agent 工具链抽象（可扩展编程工具）

### 11.1 背景

当前 Ralph 的 `execute_work_unit` 命令直接调用 `claude code` CLI 执行代码变更。未来需要支持多种编程工具（Codex、Aider、Cline、Continue 等），且不同 Agent 角色可配置不同工具。

### 11.2 核心抽象：ToolAdapter

```python
# ralph/toolchain/adapter.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    success: bool
    stdout: str
    stderr: str
    changed_files: list[str]
    exit_code: int
    artifacts: dict[str, Any]  # 工具特定产物（如 diff、test_output）


@dataclass(frozen=True)
class ToolConfig:
    tool_id: str          # 'claude_code' | 'codex' | 'aider' | 'custom'
    executable: str       # 可执行文件路径或命令
    env_vars: dict[str, str]   # 环境变量覆盖
    args_template: str    # 参数模板，支持变量插值
    working_dir: str | None = None
    timeout_seconds: int = 300


class ToolAdapter(ABC):
    """编程工具抽象接口。每个适配器封装一个 CLI 工具的调用协议。"""

    @property
    @abstractmethod
    def tool_id(self) -> str:
        """全局唯一工具标识。"""

    @abstractmethod
    def execute(
        self,
        work_dir: Path,
        instruction: str,
        context_files: list[str],
        config: ToolConfig,
    ) -> ToolResult:
        """执行编程任务，返回标准化结果。"""

    @abstractmethod
    def preflight_check(self, work_dir: Path, config: ToolConfig) -> list[str]:
        """检查工具是否可用（可执行文件存在、版本兼容等），返回错误列表。"""

    @abstractmethod
    def supports_capability(self, capability: str) -> bool:
        """查询工具是否支持某项能力（'diff' | 'test' | 'lint' | 'commit' | 'multi_file'）。"""
```

### 11.3 预置适配器

| 适配器 | tool_id | 说明 |
|--------|---------|------|
| ClaudeCodeAdapter | `claude_code` | 调用 `claude code` CLI，支持自然语言指令 + 文件列表 |
| CodexAdapter | `codex` | OpenAI Codex CLI，支持 `--approval-mode` 配置 |
| AiderAdapter | `aider` | Aider + 各种模型后端，支持 `/add` `/commit` 等命令序列 |
| ClineAdapter | `cline` | Cline VS Code extension CLI 模式 |
| ShellAdapter | `shell` | 通用 shell 脚本适配器，用于用户自定义工具 |

### 11.4 按 Agent 角色分配工具

```typescript
// dashboard-ui/lib/types.ts
interface AgentToolMapping {
  role: string                    // 'producer' | 'reviewer' | 'fixer' | ...
  default_tool_id: string         // 默认使用的工具
  allowed_tools: string[]         // 该角色允许使用的工具白名单
  fallback_chain: string[]        // 工具失败时的回退链
}

// 示例配置
const DEFAULT_AGENT_TOOLS: AgentToolMapping[] = [
  { role: 'producer', default_tool_id: 'claude_code', allowed_tools: ['claude_code', 'codex', 'aider'], fallback_chain: ['codex', 'aider'] },
  { role: 'reviewer', default_tool_id: 'claude_code', allowed_tools: ['claude_code'], fallback_chain: [] },
  { role: 'fixer', default_tool_id: 'aider', allowed_tools: ['aider', 'claude_code'], fallback_chain: ['claude_code'] },
]
```

### 11.5 工具执行流程

```
WorkUnitEngine.execute(work_id)
  ├── 1. 读取 WorkUnit 的 producer_role
  ├── 2. 查询 AgentToolMapping 获取 tool_id
  ├── 3. 加载 ToolConfig（从 settings 或默认值）
  ├── 4. 调用 ToolAdapter.preflight_check()
  │      └── 失败 → 创建 blocker（tool_unavailable）
  ├── 5. 调用 ToolAdapter.execute(instruction, context_files)
  │      └── 超时/失败 → 按 fallback_chain 重试
  ├── 6. 解析 ToolResult.changed_files → 生成 evidence
  └── 7. 更新 WorkUnit 状态 → running → needs_review
```

### 11.6 前端配置界面

在 `/settings` 页面新增"工具链"区块：

```
┌─── 编程工具配置 ──────────────────────────────┐
│                                               │
│  已注册工具:                                   │
│  ├─ Claude Code  [版本: 0.25.0]  [测试连接]   │
│  ├─ Codex        [未配置]      [去配置]       │
│  └─ Aider        [版本: 0.75.0]  [测试连接]   │
│                                               │
│  Agent 角色分配:                               │
│  ├─ Producer    [Claude Code ▼]             │
│  ├─ Reviewer    [Claude Code ▼]             │
│  └─ Fixer       [Aider ▼]                   │
│                                               │
│  [+ 添加自定义工具]                            │
└───────────────────────────────────────────────┘
```

### 11.7 API 扩展

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ralph/tools` | GET | 列出所有已注册工具及其状态 |
| `/api/ralph/tools/:id/test` | POST | 测试工具连接性 |
| `/api/ralph/tools/:id/config` | PUT | 更新工具配置 |
| `/api/ralph/agent-tools` | GET | 获取 Agent 角色 → 工具映射 |
| `/api/ralph/agent-tools` | PUT | 更新 Agent 角色 → 工具映射 |

---

## 12. LLM Provider 配置（多模型支持）

### 12.1 背景

当前系统的大模型调用是硬编码的（如 Claude API）。需要支持用户在前端灵活配置模型 Provider，支持云端主流模型和本地路由。

### 12.2 支持的 Provider

| Provider | 标识 | API 格式 | 说明 |
|----------|------|----------|------|
| DeepSeek | `deepseek` | OpenAI-compatible | 国产大模型，代码能力强 |
| Qwen (通义千问) | `qwen` | OpenAI-compatible / DashScope | 阿里云 |
| MiniMax | `minimax` | MiniMax API | 海螺 AI |
| Kimi (Moonshot) | `kimi` | OpenAI-compatible | 月之暗面 |
| ChatGLM | `chatglm` | Zhipu API | 智谱 AI |
| ChatGPT | `openai` | OpenAI API | 原生 GPT 系列 |
| Gemini | `gemini` | Google AI Studio / Vertex | 谷歌 |
| Claude | `anthropic` | Anthropic Messages API | Anthropic |
| CC Switch (本地路由) | `cc_switch` | OpenAI-compatible | 本地部署的模型路由 |
| 自定义 | `custom` | OpenAI-compatible | 任意兼容 OpenAI API 格式的服务 |

### 12.3 Provider 配置模型

```typescript
// dashboard-ui/lib/types.ts
interface LLMProvider {
  id: string                 // 用户自定义唯一标识，如 'my-deepseek'
  name: string               // 显示名称
  provider_type: 'deepseek' | 'qwen' | 'minimax' | 'kimi' | 'chatglm' | 'openai' | 'gemini' | 'anthropic' | 'cc_switch' | 'custom'
  api_base: string           // 基础 URL，如 'https://api.deepseek.com/v1'
  api_key: string            // 密钥（前端存储加密，传输用 header）
  default_model: string      // 默认模型名，如 'deepseek-chat'
  models: string[]           // 该 Provider 下可用模型列表
  is_local: boolean         // 是否本地部署（影响超时和重试策略）
  enabled: boolean
  priority: number          // 优先级，数字小的优先
}

interface LLMModelPreset {
  id: string
  label: string
  provider_id: string       // 关联到 LLMProvider.id
  model_name: string
  max_tokens: number
  temperature: number
  use_for: ('chat' | 'code' | 'review' | 'plan' | 'summarize')[]
}
```

### 12.4 模型分配策略

支持按任务类型或 Agent 角色分配不同模型：

```typescript
interface ModelAssignment {
  scope: 'global' | 'role' | 'task_type' | 'agent_id'
  scope_value: string        // 如 'producer' 或 'code' 或 'agent-001'
  provider_id: string
  model_name: string
  override_params?: {
    temperature?: number
    max_tokens?: number
    top_p?: number
  }
}

// 示例
const DEFAULT_ASSIGNMENTS: ModelAssignment[] = [
  { scope: 'task_type', scope_value: 'code', provider_id: 'deepseek-main', model_name: 'deepseek-coder' },
  { scope: 'task_type', scope_value: 'review', provider_id: 'claude-main', model_name: 'claude-3-5-sonnet' },
  { scope: 'role', scope_value: 'product_manager', provider_id: 'kimi-main', model_name: 'moonshot-v1-128k' },
]
```

### 12.5 后端 Provider 路由层

```python
# ralph/llm_router.py
from typing import Protocol

class LLMBackend(Protocol):
    async def chat(self, messages: list[dict], model: str, **kwargs) -> str: ...
    async def stream_chat(self, messages: list[dict], model: str, **kwargs) -> AsyncIterator[str]: ...
    def list_models(self) -> list[str]: ...

class LLMRouter:
    """根据配置将请求路由到对应的 LLM 后端。"""

    def __init__(self, config: LLMConfig):
        self._backends: dict[str, LLMBackend] = {}
        self._assignments = config.assignments

    def resolve(self, task_type: str, role: str | None = None) -> tuple[LLMBackend, str]:
        """返回 (backend, model_name)，按优先级匹配。"""
        # 1. 按 agent_id 精确匹配
        # 2. 按 role 匹配
        # 3. 按 task_type 匹配
        # 4. 回退到 global default
```

### 12.6 前端配置界面

在 `/settings` 页面新增"大模型"区块：

```
┌─── 大模型配置 ───────────────────────────────────┐
│                                                  │
│  Provider 列表:                                   │
│  ├─ DeepSeek   [已启用] [默认]  [编辑] [删除]   │
│  ├─ Claude     [已启用]        [编辑] [删除]   │
│  └─ CC Switch  [本地]          [编辑] [删除]   │
│                                                  │
│  [+ 添加 Provider]                               │
│                                                  │
│  ── 模型分配 ──                                   │
│  代码生成:        [DeepSeek / deepseek-coder ▼] │
│  代码审查:        [Claude / claude-3-5-sonnet ▼]│
│  需求分析:        [Kimi / moonshot-v1-128k ▼]   │
│  报告生成:        [Claude / claude-3-5-sonnet ▼]│
│                                                  │
│  [保存配置]                                       │
└──────────────────────────────────────────────────┘
```

### 12.7 API 扩展

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ralph/llm/providers` | GET/POST | 列出/添加 Provider |
| `/api/ralph/llm/providers/:id` | PUT/DELETE | 更新/删除 Provider |
| `/api/ralph/llm/providers/:id/test` | POST | 测试 Provider 连通性 |
| `/api/ralph/llm/models` | GET | 列出所有可用模型（聚合所有 Provider） |
| `/api/ralph/llm/assignments` | GET/PUT | 获取/更新模型分配策略 |
| `/api/ralph/llm/chat` | POST | 统一聊天接口（后端自动路由到对应 Provider） |

---

## 13. 智能 Issue 治理

### 13.1 背景

系统应能主动读取本地和 GitHub 仓库的 Issues，自动判断是否需要修复，并按照人类预设的策略分流处理——自动修复、需审批、或忽略。

### 13.2 Issue 来源适配器

```python
# ralph/issue_sources/adapter.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IssueItem:
    issue_id: str                  # 来源唯一标识
    source: str                    # 'github' | 'local' | 'gitlab' | 'jira'
    title: str
    body: str
    labels: list[str]
    state: 'open' | 'closed'
    created_at: datetime
    updated_at: datetime
    author: str
    comments_count: int
    url: str                       # 原始链接
    metadata: dict                 # 来源特定字段


class IssueSource(ABC):
    """Issue 来源抽象。"""

    @property
    @abstractmethod
    def source_type(self) -> str: ...

    @abstractmethod
    async def list_issues(self, since: datetime | None = None) -> list[IssueItem]: ...

    @abstractmethod
    async def get_issue(self, issue_id: str) -> IssueItem | None: ...

    @abstractmethod
    async def add_comment(self, issue_id: str, body: str) -> bool: ...

    @abstractmethod
    async def close_issue(self, issue_id: str, reason: str) -> bool: ...


class GitHubIssueSource(IssueSource):
    """GitHub Issues API 适配器。"""
    def __init__(self, repo: str, token: str, base_url: str = "https://api.github.com"): ...

class LocalIssueSource(IssueSource):
    """本地文件系统 Issue Tracker（如 `.issues/` 目录下的 markdown 文件）。"""
    def __init__(self, issues_dir: Path): ...
```

### 13.3 Issue 分类器

```python
# ralph/issue_governance/classifier.py
from dataclasses import dataclass
from enum import Enum


class IssueAction(str, Enum):
    AUTO_FIX = "auto_fix"           # 大模型自行判断并修复
    REQUIRE_APPROVAL = "require_approval"  # 需要人类批准
    IGNORE = "ignore"               # 可以忽略
    NEEDS_INVESTIGATION = "needs_investigation"  # 需要进一步分析


@dataclass(frozen=True)
class ClassificationResult:
    issue_id: str
    action: IssueAction
    confidence: float             # 0.0 ~ 1.0
    reasoning: str                # 分类理由（用于前端展示）
    suggested_assignee: str | None  # 建议分配给哪个角色
    estimated_effort: str         # 'small' | 'medium' | 'large'
    related_work_units: list[str]  # 可能关联的历史 WorkUnit


class IssueClassifier:
    """基于规则 + LLM 的 Issue 分类器。"""

    def __init__(self, llm_router: LLMRouter, rules: list[ClassificationRule]):
        self._llm = llm_router
        self._rules = rules

    async def classify(self, issue: IssueItem) -> ClassificationResult:
        # 1. 规则引擎快速匹配（O(1) 判定）
        for rule in self._rules:
            if rule.matches(issue):
                return rule.to_result(issue)

        # 2. LLM 深度分析（规则未命中时）
        prompt = self._build_classification_prompt(issue)
        response = await self._llm.chat(prompt, task_type='plan')
        return self._parse_classification_response(issue, response)
```

### 13.4 人工配置策略

人类通过 `/settings` 页面配置 Issue 治理策略。策略按优先级匹配，第一条匹配的规则生效。

```typescript
// dashboard-ui/lib/types.ts
interface IssuePolicy {
  id: string
  name: string                    // 策略名称，如"忽略文档类"
  priority: number                // 数字小的优先
  enabled: boolean

  // 匹配条件（AND 关系）
  conditions: {
    labels?: string[]             // 包含任意一个标签
    title_keywords?: string[]     // 标题包含任意关键词
    body_keywords?: string[]      // 正文包含任意关键词
    author?: string[]             // 作者匹配
    source?: ('github' | 'local')[]  // 来源匹配
    min_comments?: number         // 评论数 >= N
    is_stale?: boolean            // 是否长期未更新（如 > 30 天）
  }

  // 判定动作
  action: 'auto_fix' | 'require_approval' | 'ignore' | 'needs_investigation'

  // 附加配置
  config: {
    approval_timeout_hours?: number   // 需审批时，超时自动转 auto_fix
    max_auto_fix_per_day?: number     // 每日自动修复上限（防滥用）
    require_tests?: boolean           // auto_fix 时是否要求生成测试
    notify_channels?: string[]        // 通知渠道（如 webhook、邮件）
  }
}

// 默认策略示例
const DEFAULT_ISSUE_POLICIES: IssuePolicy[] = [
  {
    id: 'ignore-docs',
    name: '忽略文档类 Issue',
    priority: 1,
    enabled: true,
    conditions: { labels: ['documentation', 'docs', 'typo'] },
    action: 'ignore',
    config: {},
  },
  {
    id: 'auto-fix-bug',
    name: '自动修复标记为 bug 的 Issue',
    priority: 2,
    enabled: true,
    conditions: { labels: ['bug'], title_keywords: ['fix', 'crash', 'error'] },
    action: 'auto_fix',
    config: { require_tests: true, max_auto_fix_per_day: 5 },
  },
  {
    id: 'approve-refactor',
    name: '重构类需审批',
    priority: 3,
    enabled: true,
    conditions: { labels: ['refactor', 'breaking-change'] },
    action: 'require_approval',
    config: { approval_timeout_hours: 48 },
  },
  {
    id: 'fallback',
    name: '兜底：需审批',
    priority: 999,
    enabled: true,
    conditions: {},
    action: 'require_approval',
    config: {},
  },
]
```

### 13.5 Issue 治理工作流

```
┌─────────────────────────────────────────────────────────────┐
│                     Issue 治理工作流                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  定时任务 / 手动触发                                          │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ GitHub API  │    │ Local .issues/│   │ 其他来源     │     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            ▼                                │
│                    ┌───────────────┐                        │
│                    │ IssueSource   │                        │
│                    │ 聚合所有 Issue │                        │
│                    └───────┬───────┘                        │
│                            ▼                                │
│                    ┌───────────────┐                        │
│                    │ IssueClassifier│                       │
│                    │ 规则 + LLM 分类 │                       │
│                    └───────┬───────┘                        │
│                            ▼                                │
│              ┌─────────────┼─────────────┐                  │
│              ▼             ▼             ▼                  │
│        ┌─────────┐  ┌──────────┐  ┌──────────┐             │
│        │ ignore  │  │ auto_fix │  │ require_ │             │
│        │  忽略   │  │ 自动修复  │  │ approval │             │
│        └─────────┘  └────┬─────┘  │ 需审批   │             │
│                          │        └────┬─────┘             │
│                          ▼             ▼                    │
│                   ┌──────────┐  ┌──────────────┐           │
│                   │ 生成     │  │ 创建 Pending │           │
│                   │ WorkUnit │  │ Action       │           │
│                   │ + Command│  │ (审批中心)   │           │
│                   └────┬─────┘  └──────┬───────┘           │
│                        │               │                    │
│                        ▼               ▼                    │
│                   ┌──────────────────────────┐             │
│                   │ 执行修复 → 生成证据 → Review │            │
│                   │ 完成后在 Issue 下评论并关闭   │            │
│                   └──────────────────────────┘             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 13.6 审批中心集成

被判定为 `require_approval` 的 Issue 进入审批中心，显示为特殊类型的 Pending Action：

```typescript
interface IssuePendingAction extends PendingAction {
  action_type: 'issue_approval'
  issue: IssueItem
  classification: ClassificationResult
  proposed_work_unit: Partial<WorkUnit>  // LLM 生成的修复方案预览
}
```

审批中心卡片展示：
- Issue 标题 + 来源 + 标签
- 分类器判定理由 + 置信度
- 建议修复方案摘要
- 操作按钮：[批准修复] [拒绝/忽略] [修改方案]

### 13.7 前端新增页面

在 Sidebar 新增"Issue 治理"入口：

```
/ issues              → Issue 列表（按状态分组：待分类 / 待审批 / 修复中 / 已忽略 / 已关闭）
/ issues / :id        → Issue 详情（原 Issue 内容 + 分类结果 + 关联 WorkUnit）
```

Issue 列表页：

```
┌─── Issue 治理 ────────────────────────────────────────────┐
│                                                            │
│  ┌─ 统计 ──────────────────────────────────────────────┐  │
│  │ 待分类: 3    待审批: 2    修复中: 1    已关闭: 12   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  来源: [全部 ▼]  状态: [待分类 ▼]  [批量操作 ▼]  [刷新]    │
│                                                            │
│  ┌─ GH-42  内存泄漏修复 ────────────────────────────┐    │
│  │ 来源: GitHub  标签: bug, performance              │    │
│  │ 分类: 自动修复 (置信度 92%)                        │    │
│  │ 原因: 标题含"修复"+标签含"bug"，匹配策略 auto-fix-bug │   │
│  │ [查看详情] [立即修复] [转为审批] [忽略]            │    │
│  └───────────────────────────────────────────────────┘    │
│                                                            │
│  ┌─ GH-38  重构 API 路由 ───────────────────────────┐    │
│  │ 来源: GitHub  标签: refactor, breaking-change     │    │
│  │ 分类: 需审批 (置信度 78%)                          │    │
│  │ 原因: 标签含"breaking-change"，匹配策略 approve-refactor │
│  │ [查看详情] [批准] [拒绝] [修改方案]                │    │
│  └───────────────────────────────────────────────────┘    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 13.8 API 扩展

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ralph/issues/sources` | GET/POST | 列出/配置 Issue 来源 |
| `/api/ralph/issues` | GET | 列出所有 Issue（支持过滤） |
| `/api/ralph/issues/sync` | POST | 手动触发同步 |
| `/api/ralph/issues/:id/classify` | POST | 对单个 Issue 重新分类 |
| `/api/ralph/issues/policies` | GET/PUT | 获取/更新治理策略 |
| `/api/ralph/issues/policies/:id/preview` | POST | 策略预览（测试规则匹配效果） |
| `/api/ralph/issues/:id/approve` | POST | 批准 Issue 修复（创建 WorkUnit + Command） |
| `/api/ralph/issues/:id/ignore` | POST | 忽略 Issue |

### 13.9 定时任务

```python
# ralph/issue_governance/scheduler.py

async def scheduled_issue_sync():
    """每小时同步一次 Issue。"""
    for source in configured_sources:
        issues = await source.list_issues(since=last_sync_time)
        for issue in issues:
            if issue.state == 'closed':
                continue
            result = await classifier.classify(issue)
            await apply_classification(issue, result)

async def apply_classification(issue: IssueItem, result: ClassificationResult):
    if result.action == IssueAction.AUTO_FIX:
        # 检查每日上限
        if daily_auto_fix_count >= policy.config.max_auto_fix_per_day:
            result = replace(result, action=IssueAction.REQUIRE_APPROVAL, reasoning="今日自动修复已达上限")
        else:
            # 创建 WorkUnit + Command
            work_unit = await create_work_unit_from_issue(issue, result)
            await create_command('execute_work_unit', work_unit.work_id)
            daily_auto_fix_count += 1

    if result.action == IssueAction.REQUIRE_APPROVAL:
        # 创建 Pending Action
        await create_pending_action(issue, result)

    if result.action == IssueAction.IGNORE:
        # 记录日志，可选在 Issue 下评论说明
        if policy.config.notify_channels:
            await notify_ignore(issue, result)
```
8. **URL 深链**：URL 表示当前 active tab，支持刷新、分享
9. **Evidence 安全**：用 `evidence_id` 读取，路径校验在 `.ralph/evidence/` 内，大文件截断，敏感信息 redaction
10. **幂等性**：所有 Command 带 `idempotency_key`，后端去重
