# 基于三项目对比的全量改进 Roadmap

> 关联文档: [three-project-comparison.md](/Users/jieson/auto-coding/docs/three-project-comparison.md)
> 目标对象: 不熟悉业务的工程师、项目负责人、实现负责人
> 文档目标: 把对比结论直接拆成可以执行的改进方案和实施计划

---

## 一、先说清楚：这份 Roadmap 要解决什么问题

当前项目已经具备这些能力：

- 可以用 `ai-dev` 初始化项目
- 有 9 个角色的 Agent 编排
- 有 Dashboard、WebSocket、审批闸门
- 后端 / 前端 / E2E 测试都能跑通

但它还存在 4 个根问题：

1. **系统边界不够清楚**  
   很多职责还混在 `ProjectManager`、`Coordinator`、`Repository`、前端 store 里，维护成本会越来越高。

2. **运行规则不够显式**  
   现在“Agent 应该如何选任务、什么时候必须停止、怎么报阻塞、怎么验收”更多靠实现和上下文，不够像 `auto-coding-agent-demo` 那样外显。

3. **状态源不统一**  
   同一类事实分散在 `features.json`、SQLite `tasks`、dashboard `state.json`、进度日志里，后面做复杂能力时容易产生同步问题。

4. **平台工程化入口不够完整**  
   虽然已经有 `cli.py`，但还没有形成像 `multica` 那样统一的 operator interface。

这份 Roadmap 的目标不是“继续堆功能”，而是把系统从“能跑”推进到“可维护、可扩展、可交付”。

---

## 二、目标状态

当这个 Roadmap 做完后，项目应达到以下状态：

### 2.1 架构目标

- 每个模块职责都有明确说明
- 后端状态流转路径固定且可追踪
- 前端区分“服务端状态”和“本地 UI 状态”
- `ProjectManager` 不再承担过多副作用

### 2.2 工作流目标

- Agent 的执行协议、阻塞协议、验收协议全部文档化
- 人和 Agent 对“什么时候停、什么时候继续、什么算完成”有统一理解
- 能从 UI 或 CLI 一眼看出当前系统在做什么

### 2.3 运行时目标

- 任务、Feature、命令、事件、阻塞状态有统一事实源
- 状态变更能通过 API / WebSocket / UI 稳定观察
- CLI 与脚本具备标准化入口

### 2.4 工程目标

- 新人不需要理解全部业务，也能按模块改功能
- 日常运维动作有固定命令
- 每一项改造都有测试和验收标准

---

## 三、实施原则

整个实施过程必须遵守 5 条原则：

1. **先收口，再扩展**  
   先统一规则和状态源，再加新能力。

2. **先文档契约，再代码重构**  
   边界没定义清楚前，不要急着大拆代码。

3. **每一阶段都要独立可验收**  
   每个阶段结束后，测试必须全绿，文档必须更新。

4. **优先复用现有结构**  
   不要为了“更先进”马上引入 Go、Electron、Monorepo。

5. **所有改造都必须给出观测面**  
   改了流程，就要补日志、状态、测试、UI 或 CLI 入口。

---

## 四、实施总览

### 4.1 阶段划分

| 阶段 | 优先级 | 主题 | 结果 |
|------|--------|------|------|
| Phase 0 | 准备阶段 | 基线冻结与设计准备 | 给后续改造建立统一起点 |
| Phase 1 | P0 | 架构契约文档 | 先把边界写清楚 |
| Phase 2 | P0 | 工作流协议外置 | 把“怎么执行”写成显式规则 |
| Phase 3 | P0 | 统一状态源 | 把系统事实收口 |
| Phase 4 | P0 | 阻塞处理协议 | 把“什么时候停”标准化 |
| Phase 5 | P1 | 前端状态治理 | 区分 Query 状态和 UI 状态 |
| Phase 6 | P1 | 统一操作入口 | 把运行、测试、清理、诊断标准化 |
| Phase 7 | P1 | 任务账本与观测面 | 让人能看懂系统当前在做什么 |
| Phase 8 | P1 | PM/Coordinator 拆职责 | 进一步降低耦合 |

### 4.2 推荐排期

| 阶段 | 建议时长 | 依赖 |
|------|----------|------|
| Phase 0 | 2-3 天 | 无 |
| Phase 1 | 2-3 天 | Phase 0 |
| Phase 2 | 3-5 天 | Phase 1 |
| Phase 3 | 5-8 天 | Phase 1 |
| Phase 4 | 2-4 天 | Phase 2、Phase 3 |
| Phase 5 | 4-6 天 | Phase 3 |
| Phase 6 | 2-4 天 | Phase 1 |
| Phase 7 | 3-5 天 | Phase 3、Phase 5 |
| Phase 8 | 4-7 天 | Phase 3、Phase 4 |

总工期建议：**4-6 周**

---

## 五、Phase 0：基线冻结与设计准备

这个阶段不做大改造，只做“后面能安全改”的准备。

### 5.1 功能点：冻结当前系统基线

**目的**

- 给后续改造建立对照基线
- 避免边改边漂移，最后不知道哪里变了

**具体要做什么**

1. 记录当前测试基线
2. 记录当前 CLI / API / WebSocket 可用能力
3. 记录当前状态文件与数据库结构
4. 记录当前 Dashboard 主要页面与数据流

**建议产出**

- `docs/baselines/current-system-baseline.md`
- `docs/baselines/current-api-baseline.md`
- `docs/baselines/current-state-model.md`

**建议覆盖内容**

- 命令列表：`ai-dev init / run / status / tail / dashboard`
- 后端接口列表：dashboard API、WebSocket
- 状态文件列表：
  - `data/features.json`
  - SQLite `tasks`
  - `data/dashboard/state.json`
  - `claude-progress.txt`

**验收标准**

- 新人只看 baseline 文档，知道系统现状和入口
- 后续每个阶段都能明确写出“变更前 vs 变更后”

---

## 六、Phase 1：补项目级架构契约文档

这是整个计划里最重要的第一步。

### 6.1 功能点：新增架构契约文档

**目的**

- 定义各模块职责
- 约束未来代码该放哪里、不该放哪里
- 降低后面重构风险

**建议新增文件**

- `ARCHITECTURE.md`

**文档必须包含的章节**

1. 系统总览
2. 模块职责边界
3. 状态源归属
4. 事件流规则
5. 命令流规则
6. Agent 执行流规则
7. 前端状态管理规则
8. 禁止事项

### 6.2 功能点：定义模块边界

**必须写清楚的边界**

#### `core/`

负责：

- 项目初始化
- Feature 规划与排序
- 与 Agent 编排相关的业务流程

不负责：

- WebSocket 推送
- REST API
- 前端状态结构

#### `dashboard/`

负责：

- 对外 API
- WebSocket 广播
- 命令处理
- 仓储持久化
- 协调与观测

不负责：

- 直接生成 PRD
- 直接写业务 prompt

#### `agents/`

负责：

- 角色 prompt 组合
- 调用 Claude CLI 执行
- 上报执行状态

不负责：

- 最终状态裁决
- 任务编排
- 直接操作 dashboard store

#### `dashboard-ui/`

负责：

- 数据展示
- 用户交互
- 调用 API
- WebSocket 消费

不负责：

- 定义业务事实源
- 复写后端状态机逻辑

### 6.3 功能点：定义“状态归属表”

必须给每种数据定义唯一归属：

| 数据类型 | 唯一事实源 | 允许缓存位置 | 不允许出现的情况 |
|----------|------------|--------------|------------------|
| Feature 状态 | Repository | 前端 Query Cache | `FeatureTracker` 和 dashboard 各自维护两套最终状态 |
| Command 状态 | Repository | 前端 Query Cache | 前端本地直接推断最终命令结果 |
| Event 历史 | Repository | WebSocket 增量缓存 | EventBus 队列被当成长期存储 |
| Agent 实例状态 | Repository | WebSocket 增量缓存 | 仅前端 store 知道状态 |
| UI 开关/抽屉/选中项 | Zustand | 无 | 后端持久化这种纯 UI 状态 |

### 6.4 功能点：定义禁止事项

文档里必须明确写出：

- 禁止在前端重复实现后端状态机
- 禁止一个业务事实同时写入两个长期事实源
- 禁止把 WebSocket 事件当成唯一事实源
- 禁止 `ProjectManager` 继续新增与 API / WebSocket 直接耦合的逻辑

### 6.5 测试与验收

**不用写新功能测试，但必须做这些检查**

- 架构文档完成后，团队内任意工程师能回答“某类状态该放哪里”
- 后续 PR 的代码评审可以引用这份文档

**阶段完成标准**

- `ARCHITECTURE.md` 成稿
- 文档里有清晰模块边界表
- 文档里有状态归属表
- 文档里有禁止事项

---

## 七、Phase 2：把工作流协议外置

这一阶段借的是 `auto-coding-agent-demo` 的思想，但不是简单复制 `task.json`。

### 7.1 功能点：新增执行协议文档

**目的**

- 让 Agent 的工作方式可见
- 让“如何开始、如何执行、如何结束”不再隐式存在于代码和上下文里

**建议新增文件**

- `WORKFLOW.md`

**必须写清楚的内容**

1. Agent 如何选择下一个任务
2. 一次执行允许做几件事
3. 什么时候必须跑测试
4. 什么情况下可以标记完成
5. 什么情况下必须进入阻塞
6. 什么情况下必须请求 PM 审批

### 7.2 功能点：补“任务执行单元”定义

当前系统有 Feature、Task、Command，但对“执行单元”的解释还不够统一。

**要做什么**

- 在文档里定义三类对象：
  - `Feature`: 用户需求拆出的业务项
  - `Task`: 可执行工作单元
  - `Command`: 人对系统的控制指令

**具体要求**

- 给每个对象写输入、输出、生命周期
- 写清楚三者关系

**建议样例**

```text
Feature = “实现任务看板”
Task = “前端实现看板列组件”
Command = “approve / reject / pause / resume”
```

### 7.3 功能点：引入“执行清单”产物

为了让流程更透明，建议新增一个“执行账本文件”，但不是直接照搬 `task.json`。

**建议新增文件**

- `data/execution-plan.json`

**字段建议**

```json
{
  "project_id": "demo-project",
  "run_id": "abcd1234",
  "features": [
    {
      "feature_id": "F-001",
      "title": "实现 Agent 监控页",
      "status": "pending",
      "tasks": [
        {
          "task_id": "T-001",
          "title": "补后端 agents 列表接口",
          "owner_role": "backend",
          "status": "pending",
          "blocking_reason": ""
        }
      ]
    }
  ]
}
```

**注意**

- 这个文件不是为了替换后端状态源
- 它的主要作用是“可读、可审计、可让人快速理解当前执行计划”

### 7.4 功能点：把工作流规则接入 CLI

**要做什么**

在 `cli.py` 新增只读命令，帮助查看当前计划和规则。

**建议新增命令**

- `ai-dev plan`
  - 输出当前执行计划
- `ai-dev explain-state`
  - 输出当前项目中 Feature / Task / Command 的状态说明
- `ai-dev blocked`
  - 输出当前所有阻塞项

### 7.5 功能点：让 Agent 执行遵守“单次执行边界”

**要做什么**

- 在 `WORKFLOW.md` 里定义“一次执行最多完成一个 Task 或一个明确子目标”
- 在相关执行代码中补日志字段，记录本轮执行目标

**建议改动位置**

- [core/project_manager.py](/Users/jieson/auto-coding/core/project_manager.py)
- [agents/base_agent.py](/Users/jieson/auto-coding/agents/base_agent.py)
- 相关日志写入位置

**为什么要做**

- 防止一次执行改动过大
- 让任务追踪和回滚更容易

### 7.6 测试与验收

**测试项**

- CLI 新命令有输出
- `execution-plan.json` 会生成并可读
- 文档能解释清楚 Feature / Task / Command 三者关系

**阶段完成标准**

- `WORKFLOW.md` 完成
- `execution-plan.json` 方案落地
- CLI 有只读查看入口

---

## 八、Phase 3：统一项目状态源

这是代码改造量最大的阶段，也是最关键的工程阶段。

### 8.1 目标定义

**目标不是“把所有东西放数据库”**，而是让系统里每种业务事实有且只有一个长期事实源。

### 8.2 现状问题

当前事实分散：

- `FeatureTracker` 持有 Feature 状态
- `TaskQueue` 持有 Task 状态
- `ProjectStateRepository` 持有 commands/events/agents/features/chat/module_assignments
- `progress_logger` 再记录一份文本轨迹

这会导致：

- 状态同步复杂
- API 难以回答“当前准确状态是什么”
- 前端容易消费到不同来源的数据

### 8.3 功能点：定义统一状态模型

**建议新增文件**

- `docs/state-model.md`

**文档必须定义**

- Feature
- Task
- AgentInstance
- Command
- Event
- BlockingIssue
- ExecutionRun

**每个模型必须写清楚**

- 主键
- 生命周期状态
- 谁能改
- 从哪里读
- 何时对外广播

### 8.4 功能点：扩展 `ProjectStateRepository`

**改造目标**

把它升级为真正的“项目事实源”。

**建议具体任务**

1. 给 Repository 明确新增 Task 读写接口
2. 给 Repository 明确新增 BlockingIssue 读写接口
3. 给 Repository 明确新增 ExecutionRun 读写接口
4. 保留事件追加模型，但规范 event payload
5. 给所有写入动作加统一时间戳和版本号

**建议改动文件**

- [dashboard/state_repository.py](/Users/jieson/auto-coding/dashboard/state_repository.py)
- [dashboard/models.py](/Users/jieson/auto-coding/dashboard/models.py)
- [dashboard/api/schemas.py](/Users/jieson/auto-coding/dashboard/api/schemas.py)

### 8.5 功能点：重新定位 `FeatureTracker`

**目标**

- 不再让 `FeatureTracker` 作为最终事实源

**改造方向**

方案 A，推荐：

- `FeatureTracker` 退化为“依赖排序与业务规则辅助器”
- 最终状态全部写入 Repository

方案 B，不推荐：

- 继续保留 `FeatureTracker` 为主事实源，再同步给 Repository

**为什么推荐 A**

- 避免双写
- 避免一个状态先改 `features.json` 再改 `state.json`

### 8.6 功能点：重新定位 `TaskQueue`

**目标**

- 不再让 SQLite `TaskQueue` 成为“孤立任务系统”

**改造方向**

方案 A，推荐：

- 保留队列调度能力
- 把任务事实源迁到 Repository
- `TaskQueue` 只负责任务领取次序和并发控制

具体意思是：

- Task 的定义、状态、错误、结果，最终存 Repository
- Queue 只负责“谁先执行”

### 8.7 功能点：统一状态流转入口

所有状态变更必须统一从这些入口走：

1. `Repository`
2. `CommandProcessor`
3. `Coordinator` / 专门的业务服务

**禁止**

- 前端手工拼最终状态
- 直接在多个对象上各自改状态

### 8.8 功能点：补状态查询 API

为了让统一状态源真正可用，后端需要新增或重构 API。

**建议新增接口**

- `GET /api/state/snapshot`
  - 返回完整当前快照
- `GET /api/features`
  - 返回 feature 列表
- `GET /api/tasks`
  - 返回 task 列表
- `GET /api/blocking-issues`
  - 返回阻塞项
- `GET /api/runs/current`
  - 返回当前执行轮次

**建议响应要求**

- 所有接口都返回稳定结构
- 列表字段命名统一
- 不要一个接口返回裸数组、另一个返回包裹对象

### 8.9 功能点：补状态迁移脚本

因为现有项目已经有旧数据，所以要写迁移脚本。

**建议新增**

- `scripts/migrate_state.py`

**脚本要做什么**

1. 读取旧 `features.json`
2. 读取 SQLite tasks
3. 读取 dashboard `state.json`
4. 合并生成新的统一快照
5. 输出迁移报告

### 8.10 功能点：补状态一致性测试

**必须新增测试**

- Repository 单元测试
- 状态迁移测试
- API 快照测试
- “单次状态变更只写一个事实源”的测试

**建议新增测试文件**

- `tests/test_state_model.py`
- `tests/test_state_migration.py`
- `tests/test_snapshot_api.py`

### 8.11 阶段完成标准

- Feature / Task / Agent / Command / Event / BlockingIssue 有统一模型
- Repository 成为唯一长期事实源
- 前端和 API 都从统一状态源读数据
- 旧状态可迁移
- 全量测试通过

---

## 九、Phase 4：补阻塞处理协议

### 9.1 为什么必须做

审批协议解决的是“这个结果过不过”，阻塞协议解决的是“这个任务还能不能继续做”。

如果没有阻塞协议，系统会出现这些问题：

- Agent 明明缺环境，却继续瞎跑
- 前端看不到哪些任务是因为外部依赖卡住
- PM 不知道该人工介入什么

### 9.2 功能点：定义阻塞类型

**建议新增枚举**

- `missing_env`
- `missing_credentials`
- `external_service_down`
- `manual_decision_required`
- `test_unavailable`
- `unexpected_runtime_error`

**建议落地位置**

- `dashboard/models.py`
- `docs/WORKFLOW.md`
- `docs/state-model.md`

### 9.3 功能点：新增 `BlockingIssue` 模型

**字段建议**

- `blocking_id`
- `related_feature_id`
- `related_task_id`
- `type`
- `title`
- `details`
- `required_human_action`
- `status` (`open` / `resolved`)
- `created_at`
- `resolved_at`

### 9.4 功能点：让 Agent 可上报阻塞

**要做什么**

- 给 Agent 执行结果增加标准阻塞返回结构
- 不再只返回 success / failed

**建议结构**

```json
{
  "success": false,
  "blocked": true,
  "blocking_type": "missing_env",
  "blocking_message": "缺少 OPENAI_API_KEY",
  "required_human_action": "请在 .env 中配置 OPENAI_API_KEY"
}
```

**建议改动文件**

- [agents/base_agent.py](/Users/jieson/auto-coding/agents/base_agent.py)
- 各角色 agent
- [core/project_manager.py](/Users/jieson/auto-coding/core/project_manager.py)

### 9.5 功能点：把阻塞写入 Repository 和 UI

**后端要做什么**

- 保存阻塞项
- 对外提供查询接口
- WebSocket 广播阻塞事件

**前端要做什么**

- 新增阻塞列表区域
- 每个阻塞项显示：
  - 类型
  - 阻塞原因
  - 需要人工做什么
  - 当前状态

**建议改动文件**

- `dashboard-ui/lib/api.ts`
- `dashboard-ui/lib/types.ts`
- `dashboard-ui/components/` 下新增阻塞面板组件

### 9.6 功能点：给 CLI 增加阻塞查看能力

**建议新增命令**

- `ai-dev blocked`
- `ai-dev unblock <blocking_id>`

### 9.7 测试与验收

**测试项**

- Agent 返回阻塞时，系统不继续错误推进状态
- 阻塞项能在 API 和 UI 中看到
- 人工解除阻塞后，任务可以重新进入排队

**阶段完成标准**

- 阻塞是系统内的一等对象，不再只是日志文本

---

## 十、Phase 5：前端状态治理

这一阶段的目标是把 dashboard-ui 从“能显示”变成“状态职责明确”。

### 10.1 功能点：引入 Query 层

**目标**

- 服务端状态用 Query 管
- 本地 UI 状态继续用 Zustand 管

**建议新增**

- `dashboard-ui/lib/query-client.ts`
- `dashboard-ui/lib/query-keys.ts`
- `dashboard-ui/lib/hooks/`

**建议迁移的服务端数据**

- features 列表
- agents 列表
- commands 列表
- events 初始快照
- blocking issues
- execution run

### 10.2 功能点：收缩 Zustand 的职责

**Zustand 只保留这些**

- 当前选中的 agent
- 抽屉开关
- 过滤条件
- 当前输入框内容
- 临时乐观状态

**Zustand 不再负责**

- 后端 feature 全量数据
- command 最终状态
- event 历史的长期保存

### 10.3 功能点：重构 API 层

**要做什么**

- 把 `lib/api.ts` 改造成 Query 友好的 fetcher 层
- 统一所有 API 返回结构

**建议规则**

- 列表接口统一返回 `{ items, total? }`
- 详情接口统一返回 `{ item }`
- 命令执行接口统一返回 `{ command }`

### 10.4 功能点：WebSocket 只做增量更新，不做唯一数据源

**要做什么**

- 页面首次加载先走 HTTP 快照
- WebSocket 只推增量事件
- 收到增量事件后 invalidate 对应 Query

### 10.5 功能点：补 Query 层测试

**建议新增测试**

- query hooks 测试
- API 返回结构测试
- WebSocket 到 Query 失效联动测试

### 10.6 阶段完成标准

- dashboard-ui 的服务端状态不再主要堆在 Zustand
- 首屏快照 + 增量更新模型成立

---

## 十一、Phase 6：统一操作入口

### 11.1 目标

把当前零散的启动、测试、状态查看、诊断操作，整理成固定入口。

### 11.2 功能点：新增顶层 Makefile

**建议新增文件**

- `Makefile`

**建议命令**

- `make setup`
- `make test`
- `make test-backend`
- `make test-frontend`
- `make lint`
- `make build-ui`
- `make run-dashboard`
- `make run-cli`
- `make status`
- `make clean-state`

### 11.3 功能点：新增诊断脚本

**建议新增**

- `scripts/doctor.py`

**脚本检查项**

- Python 依赖是否安装
- Node 依赖是否安装
- Claude CLI 是否可用
- Playwright 是否可用
- 数据目录是否存在
- 状态文件是否损坏

### 11.4 功能点：补状态清理与回放工具

**建议新增命令**

- `ai-dev doctor`
- `ai-dev replay-events`
- `ai-dev reset-project-state`

### 11.5 阶段完成标准

- 常用操作不再依赖口头说明
- 新人看 Makefile 和 CLI help 就能跑起来

---

## 十二、Phase 7：任务账本与观测面

### 12.1 目标

让任何人都能回答这 5 个问题：

1. 当前在做哪个 Feature
2. 当前卡在哪个 Task
3. 哪个 Agent 在做
4. 为什么被阻塞
5. 下一步等谁处理

### 12.2 功能点：补任务账本 API

**建议新增接口**

- `GET /api/execution-ledger`

**返回内容**

- 当前 run
- feature 列表
- 每个 feature 下的 task
- 每个 task 当前 owner / 状态 / 阻塞情况

### 12.3 功能点：补任务账本面板

**前端建议新增组件**

- `execution-ledger-panel.tsx`

**每行至少显示**

- Feature 名称
- 当前状态
- 当前 Task
- Agent 角色
- 是否阻塞
- 最后更新时间

### 12.4 功能点：支持“按 Agent / 按 Feature / 按状态”过滤

**过滤条件**

- agent role
- feature id
- task status
- blocked / unblocked

### 12.5 阶段完成标准

- UI 和 CLI 都能直接观察执行账本
- 不需要翻日志猜系统状态

---

## 十三、Phase 8：拆解 PM / Coordinator / Repository 职责

这是代码质量提升阶段。

### 13.1 目标

让 `ProjectManager` 从“大而全”变成“负责编排，不直接处理所有副作用”。

### 13.2 当前问题

[core/project_manager.py](/Users/jieson/auto-coding/core/project_manager.py) 现在同时负责：

- 项目初始化
- feature 调度
- agent 调用
- 验收
- 重试
- git commit
- 状态推进

这类类后面很容易继续膨胀。

### 13.3 功能点：拆出 Feature 执行服务

**建议新增文件**

- `core/feature_execution_service.py`

**职责**

- 执行单个 feature
- 协调 Agent 调用
- 返回标准执行结果

### 13.4 功能点：拆出 Feature 验收服务

**建议新增文件**

- `core/feature_verification_service.py`

**职责**

- 文件存在性检查
- 语法检查
- E2E 检查
- 生成标准验收报告

### 13.5 功能点：拆出提交服务

**建议新增文件**

- `core/git_service.py`

**职责**

- git add / commit
- 返回标准化结果
- 统一错误处理

### 13.6 功能点：让 `ProjectManager` 只负责编排

最终 `ProjectManager` 应只做这些：

- 读取项目状态
- 选择下一个 feature
- 调用执行服务
- 调用协调器或仓储
- 决定是否进入下一轮

### 13.7 功能点：补服务层测试

**建议新增测试**

- `tests/test_feature_execution_service.py`
- `tests/test_feature_verification_service.py`
- `tests/test_git_service.py`

### 13.8 阶段完成标准

- `ProjectManager` 代码明显变薄
- 每项副作用都有独立服务和测试

---

## 十四、每个阶段的交付清单

| 阶段 | 必交付文档 | 必交付代码 | 必交付测试 |
|------|------------|------------|------------|
| Phase 0 | baseline 文档 | 无或极少 | 基线记录 |
| Phase 1 | `ARCHITECTURE.md` | 无或极少 | 文档评审 |
| Phase 2 | `WORKFLOW.md` | CLI 只读命令、执行计划文件 | CLI 测试 |
| Phase 3 | `state-model.md` | Repository 重构、API、新模型、迁移脚本 | 状态模型与 API 测试 |
| Phase 4 | 阻塞协议章节 | BlockingIssue 模型、API、UI、CLI | 阻塞流测试 |
| Phase 5 | 前端状态约定文档 | Query 层、store 收缩 | hooks 与前端集成测试 |
| Phase 6 | 运维命令说明 | Makefile、doctor 脚本、CLI 命令 | 脚本测试 |
| Phase 7 | 账本说明 | ledger API、UI 面板 | ledger 测试 |
| Phase 8 | 架构更新文档 | 服务拆分 | 服务层测试 |

---

## 十五、实施顺序建议

如果资源有限，建议严格按下面顺序做：

1. Phase 0
2. Phase 1
3. Phase 3
4. Phase 2
5. Phase 4
6. Phase 5
7. Phase 6
8. Phase 7
9. Phase 8

原因：

- Phase 1 先定义边界，否则后面会反复返工
- Phase 3 先统一状态源，否则前后端改造没有稳定基础
- Phase 2 和 Phase 4 让工作流和阻塞规则变得显式
- Phase 5/7 再做 UI 和观测面，才不会反复改接口
- Phase 8 最后拆服务，风险最小

---

## 十六、每个阶段的统一验收口径

每个阶段结束时，都必须回答这 6 个问题：

1. 新增了什么事实模型
2. 哪些文件的职责发生变化
3. 哪些 API 结构被统一了
4. 哪些 UI 页面可以观察到变化
5. 新增了哪些测试
6. 全量测试是否通过

如果这 6 个问题答不完整，说明阶段没有真正完成。

---

## 十七、最小可执行版本

如果现在不想一次做完整套，可以先做“最小闭环版”：

### 第 1 周

- Phase 0
- Phase 1

### 第 2 周

- Phase 2 的文档与 CLI 只读入口
- Phase 4 的阻塞协议文档

### 第 3-4 周

- Phase 3 的统一状态源改造

### 第 5 周

- Phase 5 的前端状态治理
- Phase 7 的任务账本面板

### 第 6 周

- Phase 6 的操作入口
- Phase 8 的服务拆分收尾

---

## 十八、最终结论

这份 Roadmap 的核心不是“让项目看起来更高级”，而是完成三件真正有价值的事：

1. **把系统的规则写清楚**  
   让新人和 Agent 都知道该怎么做。

2. **把系统的状态收清楚**  
   让系统里每一种事实都只有一个可信来源。

3. **把系统的职责拆清楚**  
   让代码未来还能继续长，而不是越长越脆。

如果只做一件事，优先做 **Phase 1 + Phase 3**。  
如果要做一条完整路线，就按这份 Roadmap 顺序推进，不要跳着做。
