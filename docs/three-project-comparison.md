# 三项目全量对比分析（修订版）

> **对比对象**
> - **auto-coding**（当前项目）: Python/FastAPI 的多 Agent 编程编排系统
> - **auto-coding-agent-demo**（参考项目 A）: Next.js 视频生成应用 + Claude Code 自动化循环
> - **multica**（参考项目 B）: Go + Next.js 的多 Agent 管理平台（含 daemon / CLI / Web）

---

## 一、先给结论

这三个项目表面上都和 AI Agent 有关，但本质不是同一类东西：

- **auto-coding-agent-demo** 更像“AI 自动化开发操作规程”的样板工程。它的核心价值不在业务本身，而在 `task.json + CLAUDE.md + run-automation.sh` 这一套外部工作流控制。
- **multica** 是典型的产品级 Agent 平台，重点不是单个 Agent 能做什么，而是运行时管理、状态持久化、workspace 隔离、CLI/daemon/desktop 的整体工程能力。
- **auto-coding（我们）** 目前更接近“自建编排层 + Claude CLI 执行引擎 + Dashboard”的平台雏形。优势是迭代快、测试全、角色细；短板是架构边界、运维入口、统一状态源还不够成熟。

一句话概括：

- 要借 **agent-demo**，重点借的是“工作流外置”和“阻塞协议”。
- 要借 **multica**，重点借的是“架构治理”和“产品级运行时”。
- 我们当前不该急着借的是“Go 重写”“Electron 化”“全量多租户化”。

---

## 二、项目定位对比

| 维度 | auto-coding（我们） | auto-coding-agent-demo | multica |
|------|---------------------|------------------------|---------|
| **定位** | 多 Agent 编程编排系统 | 用 AI 自动推进单个应用开发的样板工程 | 多 Agent 协作与管理平台 |
| **核心用户** | 开发者 / 内部平台使用者 | 单项目开发者 / 内容应用作者 | 团队 / 工作空间级用户 |
| **项目性质** | 平台雏形 | 成品应用 + 自动化开发 workflow demo | 产品级平台 / 基础设施 |
| **真正的参考价值** | — | 任务规约、自动化循环、人工介入协议 | 架构边界、daemon/CLI、状态治理、workspace |

**修正判断**：

- 原文把我们写成 “OpenAI 原生多 Agent 编程平台” 不准确。当前代码里的 Agent 实际通过 [agents/base_agent.py](/Users/jieson/auto-coding/agents/base_agent.py) 调用 `claude -p`，并不是直接走 OpenAI API。
- 原文把 agent-demo 理解成“应用项目”没错，但还不够。它更重要的价值是把 Agent workflow 写到了代码和文件里，而不是藏在 prompt 里。

---

## 三、技术栈与实现基线

### 3.1 后端 / 编排层

| 维度 | auto-coding（我们） | auto-coding-agent-demo | multica |
|------|---------------------|------------------------|---------|
| 主要语言 | Python 3.11+ | 无独立后端（全栈 Next.js） | Go 1.24+ |
| API / 服务框架 | FastAPI + Uvicorn | Next.js Route Handlers | Chi router |
| 核心执行引擎 | Python 编排 + Claude CLI | Claude Code CLI | Go server + daemon + 多种 Agent CLI |
| 任务持久化 | SQLite `TaskQueue` + `features.json` + `state.json` | `task.json` 文件 | PostgreSQL + sqlc + task/run 表 |
| 状态存储风格 | 文件 + SQLite 混合 | 文件驱动 | 数据库优先 |
| 实时通信 | FastAPI WebSocket + EventBus | 无 | WebSocket + 事件总线 |
| 调度方式 | PM / Coordinator 进程内调度 | Shell 外循环轮询 | daemon 长驻调度 |

**代码层面的真实情况**：

- 我们的任务队列不是“纯内存”，而是 SQLite，见 [core/task_queue.py](/Users/jieson/auto-coding/core/task_queue.py)。
- 我们的 feature 状态和 dashboard 状态不是同一个源：
  - feature 在 [core/feature_tracker.py](/Users/jieson/auto-coding/core/feature_tracker.py) 的 `features.json`
  - dashboard 在 [dashboard/state_repository.py](/Users/jieson/auto-coding/dashboard/state_repository.py) 的 `state.json`
- 也就是说，我们现在已经不是“没有持久化”，而是“持久化分散、状态源不统一”。

### 3.2 前端

| 维度 | auto-coding（我们） | auto-coding-agent-demo | multica |
|------|---------------------|------------------------|---------|
| 框架 | Next.js 15 | Next.js 14 | Next.js 16 |
| 语言 | TypeScript | TypeScript | TypeScript |
| 包管理 | npm | npm | pnpm workspaces |
| Monorepo | 否 | 否 | 是（Turborepo） |
| 状态管理 | Zustand + WebSocket | React state / 页面内状态 | TanStack Query + Zustand |
| 桌面应用 | 否 | 否 | 是（Electron） |
| UI 抽象层 | 业务组件为主 | 页面直写为主 | `packages/ui` / `packages/views` 分层 |

### 3.3 Agent 系统

| 维度 | auto-coding（我们） | auto-coding-agent-demo | multica |
|------|---------------------|------------------------|---------|
| Agent 运行时 | 自建编排层 + Claude CLI | Claude Code CLI | 多 Agent CLI 自动检测与注册 |
| Agent 角色 | 9 个固定专业角色 | 单一通用 Claude | 多运行时、多 agent provider |
| Agent 提示词 | `prompts/*.md` + Python 拼装 | `CLAUDE.md` + `task.json` | 系统提示词 + 工作流 + server/daemon 协议 |
| 并发方式 | `AgentPool` 多实例 | 单 session 一次一任务 | daemon + runtime registry |
| 隔离方式 | 每个 agent 实例独立 workspace，但无 workspace 多租户 | 无 | workspace 级隔离 |

**修正判断**：

- 原文写“工作空间隔离：否”不完全准确。我们在 [agents/pool.py](/Users/jieson/auto-coding/agents/pool.py) 已经有“每个实例独立 workspace”的局部隔离。
- 但这不是 multica 那种“用户/团队级 workspace 隔离”，所以更准确的写法应该是：**有实例级隔离，无平台级多租户隔离**。

---

## 四、最关键的几个代码维度

这部分是原文里最值得补充的，因为这些差异只有看实现才能真正看出来。

### 4.1 运行时控制哲学

**auto-coding-agent-demo**

- 真正的“调度器”不是应用代码，而是 [run-automation.sh](/Users/jieson/auto-coding/auto-coding-agent-demo/run-automation.sh)。
- 它负责：
  - 统计剩余任务
  - 每轮只做一个任务
  - 记录日志
  - 失败后继续下一轮
  - 强制让 Claude 按 `CLAUDE.md` 规定的流程执行
- 这是一种典型的“外层确定性控制 + 内层非确定性模型执行”模式。

**auto-coding（我们）**

- 调度逻辑主要在 [core/project_manager.py](/Users/jieson/auto-coding/core/project_manager.py) 和 [dashboard/coordinator.py](/Users/jieson/auto-coding/dashboard/coordinator.py)。
- 优点是灵活、可插入审批闸门、可接 dashboard。
- 缺点是控制面分散，PM、Coordinator、Repository、CommandProcessor、EventBus 共同组成了运行时，理解和维护成本明显高于 agent-demo。

**multica**

- [multica/server/internal/daemon/daemon.go](/Users/jieson/auto-coding/multica/server/internal/daemon/daemon.go) 清楚地展示了它的产品级运行时形态：
  - runtime 注册
  - workspace 同步
  - heartbeat
  - gc
  - health server
  - poll loop
- 这不是“脚本自动化”，而是“长期在线的 Agent 运行基础设施”。

**结论**

- agent-demo 借鉴点：外层流程控制应该尽量显式化、文件化。
- multica 借鉴点：运行时职责拆分清楚，长生命周期服务的边界明确。
- 我们当前要做的不是重写架构，而是把现有编排层的职责继续收口。

### 4.2 架构约束显式性

**multica 最强**

- [multica/AGENTS.md](/Users/jieson/auto-coding/multica/AGENTS.md) 不是普通说明文档，而是架构约束：
  - `packages/core` 负责什么
  - `packages/ui` 不能依赖什么
  - `packages/views` 不能沾染什么
  - 服务端状态和客户端状态如何分工
- 这种“写出来的边界”会直接降低后期架构腐化速度。

**agent-demo 的约束重点不同**

- [auto-coding-agent-demo/CLAUDE.md](/Users/jieson/auto-coding/auto-coding-agent-demo/CLAUDE.md) 约束的是工作流，不是代码包边界。
- 它定义的是：
  - 先 init
  - 再选任务
  - 完成后必须测
  - 只有通过测试才能改 `passes`
  - 阻塞时必须停止

**我们当前的情况**

- 代码本身已有一定结构，但边界更多是“约定俗成”，不是“被文档明确约束”。
- 当前最缺的不是新功能，而是一份类似 multica `AGENTS.md` 的项目级架构契约。

### 4.3 状态源与可审计性

**auto-coding-agent-demo**

- `task.json` 是最简单也最强的一点。
- 任务状态、步骤、完成标记都是肉眼可读、可 diff、可回滚的。
- 这使得 workflow 非常透明。

**auto-coding（我们）**

- 当前状态分散在多个层次：
  - `features.json`
  - SQLite `tasks`
  - dashboard `state.json`
  - 进度日志 `claude-progress.txt`
- 好处是已经有初步分层。
- 问题是还没有一个真正统一的“项目事实源”。

**multica**

- 明显是数据库优先设计。
- 从 migration、sqlc、service 层设计可以看出，它把状态历史、事务边界、事件传播当成一等公民。

**结论**

- 我们下一步不应该简单理解成“给 TaskQueue 换数据库”。
- 更准确的目标是：**统一项目状态源，减少同一事实在 SQLite / JSON / 内存中的重复表达。**

### 4.4 事件模型与副作用收口

**multica**

- [multica/server/internal/events/bus.go](/Users/jieson/auto-coding/multica/server/internal/events/bus.go) 的事件总线非常克制，就是同步发布订阅。
- 服务层如 [multica/server/internal/service/autopilot.go](/Users/jieson/auto-coding/multica/server/internal/service/autopilot.go) 负责：
  - 先做事务
  - 再更新 run / issue / task
  - 再发事件
- 事件不是“状态本身”，而是“状态变化后的通知”。

**我们**

- 现在这条链已经比之前顺很多：
  - Repository
  - CommandProcessor
  - Coordinator
  - EventBus
  - WebSocket
- 但 [core/project_manager.py](/Users/jieson/auto-coding/core/project_manager.py) 仍然承担过多职责：
  - 任务编排
  - 验收
  - 重试
  - git 提交
  - 状态推进

**结论**

- multica 更值得借鉴的是“副作用收口”，不是单纯换技术栈。
- 我们后续应继续把 PM 里的流程职责往独立组件拆，而不是继续往一个类里堆逻辑。

### 4.5 前端状态所有权

**我们**

- 当前 dashboard 前端主要是 Zustand + WebSocket 直接推状态。
- 这对快速迭代友好，但随着页面复杂度上升，服务端状态、派生状态、临时 UI 状态会开始混在一起。

**multica**

- `QueryProvider` 和 query client 很简单，见 [multica/packages/core/provider.tsx](/Users/jieson/auto-coding/multica/packages/core/provider.tsx) 与 [multica/packages/core/query-client.ts](/Users/jieson/auto-coding/multica/packages/core/query-client.ts)。
- 但真正重要的是状态所有权被划清了：
  - TanStack Query 管服务端状态
  - Zustand 管客户端交互状态

**结论**

- 这不是“为了流行而引入 TanStack Query”，而是为了把状态边界写清楚。
- 这个方向对我们是对的，但优先级略低于统一状态源和架构契约。

### 4.6 工程化入口与运维体验

**multica**

- [multica/Makefile](/Users/jieson/auto-coding/multica/Makefile) 是非常值得学的地方。
- 它不是“方便命令集合”，而是真正的 operator interface：
  - setup
  - start / stop
  - env
  - db
  - self-host
  - worktree 环境
- 这会极大降低团队操作成本。

**agent-demo**

- 工程化入口极轻，适合单项目自动推进，不适合平台产品。

**我们**

- 现在已经有 `cli.py`，但更多还是功能入口，不是完整的运维入口。
- 最现实的借鉴方向不是先做 daemon，而是先把“开发、测试、dashboard、状态查看、清理、回放”这些操作标准化。

### 4.7 失败处理与人工介入

**agent-demo**

- 这一点其实很强。
- [auto-coding-agent-demo/CLAUDE.md](/Users/jieson/auto-coding/auto-coding-agent-demo/CLAUDE.md) 明确规定：
  - 什么情况下不能提交
  - 什么情况下不能标记完成
  - 什么情况下必须请求人工帮助
- 这是非常实用的“阻塞协议”。

**我们**

- 我们的优势是已经有 PM 审批闸门，这比单纯的“停下来”更进一步。
- 但缺少一份对 Agent 和人都可见的统一阻塞协议文档。

**结论**

- 这块最值得借鉴的不是 shell，而是“什么时候必须停、停下后输出什么”。

---

## 五、三边方案的核心优劣

### 5.1 auto-coding-agent-demo 的真实优势

1. **工作流外置**  
   不是把流程写在 prompt 里，而是写在 `run-automation.sh + CLAUDE.md + task.json` 里，透明且稳定。

2. **一轮只做一个任务**  
   这个约束很简单，但极大降低了 session 漂移和状态污染。

3. **阻塞协议清晰**  
   不能测、缺账号、缺环境时，明确要求停止，不允许“假装完成”。

4. **极低基础设施成本**  
   不需要 server、不需要 daemon，也能把自动化工作流跑起来。

### 5.2 multica 的真实优势

1. **平台边界清晰**  
   代码组织、包职责、运行时职责都写得很清楚。

2. **运行时成熟度高**  
   server、daemon、workspace、runtime、autopilot 这些概念都是一等公民。

3. **数据库与迁移体系成熟**  
   它的状态治理和演进能力远强于文件混合式持久化。

4. **工程操作入口完整**  
   Makefile、CLI、环境切换、worktree/self-host 都是产品级的。

5. **前端状态模型更规范**  
   Query 与本地状态分工明确，后期可维护性更好。

### 5.3 auto-coding（我们）的真实优势

1. **角色化编排已经成型**  
   9 个专业角色 + AgentPool 多实例，这在平台雏形阶段已经很有辨识度。

2. **审批与可视化链路已经建立**  
   PM 协调、命令处理、事件推送、dashboard 基本闭环已经打通。

3. **测试成熟度最好**  
   当前代码库已经有比较扎实的 Python 测试、前端构建与 E2E 验证。

4. **实现速度快**  
   Python/FastAPI + Next.js 的开发效率，对当前阶段非常合适。

5. **实例级工作区隔离已具备基础**  
   虽然不是多租户，但已具备每个 agent 实例独立 workspace 的机制。

---

## 六、最值得借鉴的点（重新排序）

### P0：应该优先做

| 借鉴内容 | 来源 | 为什么值得优先做 |
|----------|------|------------------|
| **补一份项目级架构契约文档** | multica | 现在最缺的是边界治理，不是再加功能。把状态归属、模块职责、前后端边界、事件流规则写清楚，收益最大。 |
| **把工作流协议外置** | auto-coding-agent-demo | 不是简单照搬 `task.json`，而是把“如何选任务、如何验证、何时停下来”写成显式协议，减少隐藏 prompt 状态。 |
| **统一项目状态源** | multica + 我们当前现状 | 当前 SQLite / JSON / Repository 并存，应该先统一事实源，再谈更复杂的产品能力。 |
| **补阻塞处理协议** | auto-coding-agent-demo | PM 审批解决了“是否通过”，但还没完整解决“何时必须停止并请求人工”的规范问题。 |

### P1：值得做，但次一级

| 借鉴内容 | 来源 | 为什么值得做 |
|----------|------|--------------|
| **前端改为 TanStack Query + Zustand 分工** | multica | 解决服务端状态与客户端状态混杂问题，提升 dashboard 可维护性。 |
| **补统一操作入口（Makefile / scripts）** | multica | 把 setup、dashboard、tests、cleanup、dev 环境入口统一，降低多人协作成本。 |
| **引入可审计任务账本视图** | auto-coding-agent-demo | 未必必须是 `task.json`，但需要一个能让人一眼看懂“当前系统在做什么”的任务账本。 |
| **继续拆 PMCoordinator / ProjectManager 职责** | multica 的服务层分工思路 | 现在 PM 仍偏重，继续收口副作用能降低后续回归成本。 |

### P2：阶段性观察，不要着急上

| 借鉴内容 | 来源 | 为什么暂缓 |
|----------|------|------------|
| **多 Agent CLI 自动检测** | multica | 当前单一 Claude CLI 跑通主链路更重要，过早做 provider 抽象只会增加复杂度。 |
| **Workspace 多租户体系** | multica | 当前还没到团队级平台阶段，先把单项目/单实例状态治理做好。 |
| **Electron 桌面端** | multica | 这是交付形态问题，不是当前最痛的工程问题。 |
| **Monorepo 重构** | multica | 现在体量还不至于非上 monorepo 不可，过早重构收益有限。 |

---

## 七、不建议直接照搬的部分

| 内容 | 来源 | 原因 |
|------|------|------|
| `task.json` 原样替代我们全部任务系统 | auto-coding-agent-demo | 我们已有 FeatureTracker、TaskQueue、Repository，直接替换会把平台能力降回单文件工作流。应该借“规约”，不是机械替换。 |
| Shell + grep 作为长期核心编排 | auto-coding-agent-demo | 对单项目有效，但不适合作为平台主控制面。 |
| Go 后端重写 | multica | 当前瓶颈不在语言性能，而在状态治理和模块边界。 |
| 一上来就做 Electron + 多租户 + daemon 全套 | multica | 这是产品成熟期能力，不是当前最短路径。 |

---

## 八、最终判断

### 8.1 三个项目的本质区别

- **auto-coding-agent-demo** 是“把 AI 当执行者的开发作业流程样板”。
- **multica** 是“把 Agent 当长期在线资源来管理的产品平台”。
- **auto-coding（我们）** 是“正在从编排脚本化思维，走向平台化思维”的中间阶段。

### 8.2 我们现在最应该学什么

**不是学新技术栈，而是学两件事：**

1. **向 agent-demo 学 workflow discipline**  
   把任务协议、测试协议、阻塞协议写清楚，让模型少靠隐式记忆。

2. **向 multica 学 architecture discipline**  
   把状态、边界、运行时职责、操作入口整理清楚，让系统从“能跑”走向“可维护”。

### 8.3 一个更准确的路线图

1. **短期**
   - 补项目级架构契约文档
   - 补阻塞协议和执行协议
   - 统一状态源定义

2. **中期**
   - Dashboard 前端状态拆分
   - 操作入口标准化
   - PM / Coordinator / Repository 继续解耦

3. **长期**
   - 如果产品真的走向团队协作平台，再考虑 daemon、多 runtime、workspace 多租户、桌面端

---

## 九、最简结论

- **agent-demo 最值得借的是 workflow，不是它的业务。**
- **multica 最值得借的是治理能力，不是它的语言和桌面端。**
- **我们当前最该做的，是把已有能力收口、写清、统一，而不是继续横向扩功能。**
