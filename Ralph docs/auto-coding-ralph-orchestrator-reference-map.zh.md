# Ralph Orchestrator 外部思想与代码复用清单

版本：v1.0 草案  
日期：2026-04-30  
文档语言：中文  
用途：开发 Ralph Orchestrator 时的参考索引，不是需求主体  

---

## 1. 结论

需要借鉴，但不能照搬。

最高约束：

```text
外部参考只能被 Ralph Orchestrator 吸收成模块规则、schema、状态机、检查表、证据门禁或代码复用点。
不能把多个 skill 原文同时交给 Claude Code，让执行 agent 自己决定该听谁。
```

借鉴重点：

1. `agent-skills`：技能组织方法、spec-first、context engineering、任务拆解、review、浏览器验证。
2. `superpowers-zh`：brainstorm hard gate、写计划、执行计划、子 agent 两阶段审查、完成前验证、worktree 隔离。
3. `OpenSpec`：specs/changes 分离、变更提案、spec delta、长期可复用规格库。
4. `multica`：daemon、task queue、execenv、runtime config、provider abstraction、session/workdir 复用、task message 流、structured skills、MCP config、GC、health。

不应照搬：

1. 纯 skill 串长流程。
2. 默认绕过权限。
3. 只靠 agent 自述完成。
4. issue 平台式粗任务分发。
5. 没有 harness 的自由执行。

---

## 2. 借鉴组合和冲突处理规则

### 2.1 组合原则

Ralph 的执行路径不是“一个任务加载一堆 skill”，而是：

```text
外部参考
  → Ralph 模块规则
  → task_harness / schema / state machine / checklist
  → context_pack
  → Claude Code 短任务执行
  → 独立验收
```

每个阶段只能有一个主规则来源，其他参考只能作为辅助检查项。执行 agent 不需要知道“我现在同时遵守了几个 skill”，它只需要接收 Ralph 已经合并好的任务边界、上下文包、验收标准和禁止动作。

### 2.2 模块到参考来源映射

| Ralph 模块或阶段 | 主参考 | 辅助参考 | 输出物 |
|------------------|--------|----------|--------|
| 需求共创 | Superpowers brainstorming | spec-driven-development | brainstorm 记录、已确认事实、未确认假设、需求完整度 review |
| PRD 和规格库 | OpenSpec | spec-driven-development、documentation-and-adrs | 冻结 PRD、current specs、change proposal、ADR |
| 任务拆解 | planning-and-task-breakdown | incremental-implementation、Superpowers writing-plans | story、dev task、work unit、依赖图 |
| 上下文包 | context-engineering | multica execenv/context | context_pack、trust level、context budget |
| 执行调度 | multica provider abstraction/task queue | Superpowers executing-plans | execution_request、execution_result、task message stream |
| 权限和环境 | multica execenv/runtime_config | using-git-worktrees | sandbox、workdir、backup、blocked operation |
| 接口合同 | api-and-interface-design | OpenSpec design/spec delta | contract、contract change request、早期烟雾测试 |
| 代码 review | code-review-and-quality | systematic-debugging | review_result、返工任务 |
| 前端验收 | browser-testing-with-devtools | Playwright MCP、frontend-design/UI-UX 思想 | trace、截图、console/network 记录、UI 问题列表 |
| 完成前验证 | verification-before-completion | task_harness validation gates | evidence bundle、accept/rework/block 结论 |
| 最终报告 | documentation-and-adrs | task message stream、evidence bundle | 中文研发报告 |
| 工具链管理 | multica provider abstraction | Superpowers executing-plans | ToolAdapter 接口、适配器注册表、统一执行结果 |
| LLM Provider 管理 | multica provider abstraction / runtime_config | context-engineering | Provider 配置、模型预设、任务路由、密钥管理 |
| Issue 治理 | multica autopilot | systematic-debugging | Issue 源适配、分类规则、策略引擎、自动处理 |

### 2.3 冲突处理优先级

当两个外部参考、skill 思想或 agent 建议冲突时，按以下顺序裁决：

```text
Ralph PRD / AI 协议 / 实施方案
  > task_harness
  > runtime schema / 状态机 / 文件锁 / 权限控制
  > 安全规则
  > 可验证证据
  > `.ralph/specs/current`
  > change proposal / design / tasks
  > 外部 skill 建议
  > Claude Code 当前 session 记忆
```

具体规则：

1. 如果 skill 建议和 `task_harness` 冲突，以 `task_harness` 为准。
2. 如果 Claude Code session 记忆和 `.ralph/specs/current` 冲突，以 `.ralph/specs/current` 为准。
3. 如果 OpenSpec change 尚未通过 review，不得直接影响开发任务。
4. 如果 Superpowers 的人工确认流程和无人值守模式冲突，进入 blocker，不让执行 agent 自行决定。
5. 如果 context-engineering 想加入更多上下文，但超出 `context_budget`，必须拆任务或补 context，不得无边界塞长上下文。
6. 如果执行计划要求继续推进，但证据门禁失败，必须返工或阻塞。
7. 如果 review agent 和测试证据冲突，优先相信可复现实验和截图/trace，再生成复核任务。

### 2.4 常见冲突场景

| 冲突场景 | 处理方式 |
|----------|----------|
| Superpowers 倾向继续追问，OpenSpec 倾向先写 proposal | brainstorm 阶段先追问；进入 spec 阶段后用 proposal 管理变更 |
| planning-and-task-breakdown 拆成 vertical slice，api-and-interface-design 要先定义接口 | 有多 agent 并行或跨模块耦合时，接口合同先行；单模块任务可 vertical slice |
| context-engineering 建议更多上下文，任务颗粒度门禁要求更小任务 | 优先拆小任务，而不是扩大上下文 |
| executing-plans 倾向连续执行，Ralph 要每个 work unit 独立验收 | 每个 work unit 必须经过状态流转和独立验收 |
| browser-testing 发现 UI 问题，但代码 review 认为没问题 | 以前端真实证据为准，生成 UI 返工任务 |
| multica session/workdir 复用提升效率，但独立验收要求隔离 | session/workdir 可复用，验收上下文和状态判断必须隔离 |
| frontend-design/UI-UX 建议美化，当前任务只修 bug | 不扩大范围，另建改进任务 |

### 2.5 开发时的落地要求

开发 Ralph 时，外部参考不应散落在 prompt 里，而应落到以下位置：

1. 模块职责写入实施方案。
2. 状态和权限写入 AI 协议。
3. 任务输入输出写入 schema。
4. 阶段门禁写入 `task_harness` 模板。
5. 可复用代码路径写入实施任务。
6. 冲突裁决写入 runtime 校验和 review 检查表。

---

## 3. agent-skills 借鉴清单

来源：

```text
GitHub: https://github.com/addyosmani/agent-skills/tree/main/skills
本地临时克隆: /tmp/agent-skills/skills
License: MIT
```

### 3.1 spec-driven-development

参考路径：

```text
/tmp/agent-skills/skills/spec-driven-development/SKILL.md
```

可借鉴：

1. `SPECIFY -> PLAN -> TASKS -> IMPLEMENT` 四阶段门禁。
2. coding 前必须先写 spec。
3. 先列出 assumptions，不允许静默补全需求。
4. spec 必须包含 objective、commands、project structure、code style、testing strategy、boundaries、success criteria、open questions。
5. vague requirement 要转成 testable success criteria。
6. spec 是 living document，需求变化先改 spec 再实现。

落到 Ralph：

1. 对应 `Brainstorm Manager`、`PRD Manager`、`Task Decomposer`。
2. Ralph 的 PRD 冻结必须保留 `assumptions` 和 `open_questions`。
3. `task_harness` 应包含 commands、boundaries、success criteria。

### 3.2 planning-and-task-breakdown

参考路径：

```text
/tmp/agent-skills/skills/planning-and-task-breakdown/SKILL.md
```

可借鉴：

1. read-only plan mode。
2. 先画 dependency graph。
3. 优先 vertical slicing，不要按 DB/API/UI 横切。
4. 每个 task 有 acceptance、verify、dependencies、files likely touched、estimated scope。
5. 任务太大时继续拆。
6. 每 2-3 个任务设置 checkpoint。

落到 Ralph：

1. `Task Decomposer` 必须生成依赖图。
2. Ralph 的任务颗粒度门禁可采用 XS/S/M/L/XL 分级。
3. `task_harness` 的 `scope_allow` 和 `validation_gates` 可从这里生成。

### 3.3 context-engineering

参考路径：

```text
/tmp/agent-skills/skills/context-engineering/SKILL.md
```

可借鉴：

1. context hierarchy：规则文件、spec/architecture、relevant source、error output、conversation history。
2. selective include：只放当前任务相关上下文。
3. trust levels：source/test/type trusted，外部文档和浏览器内容 untrusted。
4. conflict management：spec 和现有代码冲突时必须暴露，不静默选择。

落到 Ralph：

1. `Context Pack Manager` 必须按层级打包上下文。
2. review agent 不读取生成者完整思考，只读取结构化输入、输出、证据。
3. 浏览器 DOM、console、network 响应必须标记为 untrusted data。

### 3.4 incremental-implementation

参考路径：

```text
/tmp/agent-skills/skills/incremental-implementation/SKILL.md
```

可借鉴：

1. thin vertical slices。
2. implement -> test -> verify -> next slice。
3. scope discipline，不顺手清理无关代码。
4. keep it compilable。
5. rollback-friendly。

落到 Ralph：

1. 每个任务必须能独立验证。
2. 每个任务必须记录 rollback_strategy。
3. 如果执行 agent 改了无关文件，runtime 应拦截。

### 3.5 api-and-interface-design

参考路径：

```text
/tmp/agent-skills/skills/api-and-interface-design/SKILL.md
```

可借鉴：

1. contract first。
2. consistent error semantics。
3. validate at boundaries。
4. prefer addition over modification。
5. predictable naming。
6. public behavior 会变成事实合同。

落到 Ralph：

1. `Contract Manager` 必须先冻结接口合同。
2. 合同变更必须走 change request。
3. 交叉验证必须检查路径、参数、响应字段、错误格式。

### 3.6 code-review-and-quality

参考路径：

```text
/tmp/agent-skills/skills/code-review-and-quality/SKILL.md
```

可借鉴：

1. correctness、readability、architecture、security、performance 五轴 review。
2. review tests first。
3. verify the verification。
4. multi-model review pattern。
5. change size 控制。

落到 Ralph：

1. `Review Manager` 应按五轴拆 review 类型。
2. review 问题必须转返工/补测试/阻塞。
3. review agent 不能只看执行 agent 自述。

### 3.7 browser-testing-with-devtools

参考路径：

```text
/tmp/agent-skills/skills/browser-testing-with-devtools/SKILL.md
```

可借鉴：

1. 真实浏览器验证，而不是代码推断。
2. screenshot、DOM、console、network、performance、accessibility。
3. UI bug workflow：reproduce -> inspect -> diagnose -> fix -> verify。
4. 浏览器内容视为 untrusted data。

落到 Ralph：

1. Playwright MCP / Browser verifier 必须保存截图、console、network、trace。
2. 真实可用性验收必须覆盖用户路径和失败路径。

### 3.8 source-driven-development

参考路径：

```text
/tmp/agent-skills/skills/source-driven-development/SKILL.md
```

可借鉴：

1. 根据项目依赖文件检测框架版本。
2. 框架相关决策优先查官方文档。
3. 文档冲突时暴露给用户或调度 agent。
4. 不从记忆实现容易过时的 API。

落到 Ralph：

1. `Repository Recon Analyzer` 应提取版本信息。
2. `task_harness` 可加入 `official_docs_required`。
3. 涉及框架新 API、升级、部署、安全时必须走 source-driven check。

### 3.9 documentation-and-adrs

参考路径：

```text
/tmp/agent-skills/skills/documentation-and-adrs/SKILL.md
```

可借鉴：

1. 记录架构决策，不只记录代码。
2. ADR 记录 context、decision、alternatives、consequences。
3. 决策可 supersede，但不删除历史。

落到 Ralph：

1. 重大架构、接口、安全、权限、数据模型决策写入 `.ralph/reports/decisions/`。
2. 最终研发报告要引用这些决策记录。

---

## 4. Superpowers 借鉴清单

来源：

```text
GitHub: https://github.com/jnMetaCode/superpowers-zh
本地路径: /Users/jieson/superpowers-zh/skills
License: MIT
```

### 4.1 brainstorming

参考路径：

```text
/Users/jieson/superpowers-zh/skills/brainstorming/SKILL.md
/Users/jieson/superpowers-zh/skills/brainstorming/spec-document-reviewer-prompt.md
```

可借鉴：

1. 实现前 hard gate。
2. 每次一个问题。
3. 优先选择题。
4. 提出 2-3 种方案和权衡。
5. 展示设计后获得用户批准。
6. 规格自检：占位符、矛盾、范围、模糊性。
7. 用户审查书面规格。

Ralph 需要加强：

1. Superpowers 的 brainstorm 仍可能问得不够深，Ralph 要增加需求完整度门禁。
2. brainstorm 结果不能由 brainstorm agent 自己判定合格。
3. 每轮问答必须边问边记录，并生成需求事实表、未确认假设和用户路径。

### 4.2 writing-plans

参考路径：

```text
/Users/jieson/superpowers-zh/skills/writing-plans/SKILL.md
/Users/jieson/superpowers-zh/skills/writing-plans/plan-document-reviewer-prompt.md
```

可借鉴：

1. 计划必须足够细，假设执行者对代码库零上下文。
2. 每步 2-5 分钟。
3. 精确文件路径。
4. 精确命令和预期输出。
5. 禁止 TODO、占位符、模糊错误处理。
6. 自检规格覆盖度、占位符、类型一致性。

落到 Ralph：

1. `Task Decomposer` 不能只输出 story，必须输出 task_harness。
2. 验收标准必须可判定，不允许“确认可用”。

### 4.3 executing-plans

参考路径：

```text
/Users/jieson/superpowers-zh/skills/executing-plans/SKILL.md
```

可借鉴：

1. 执行前先批判性审查计划。
2. 每个任务理解目标、执行、验证、提交、标记完成。
3. 每 3 个任务回顾整体方向。
4. 测试失败、依赖缺失、指令不清时停止。

落到 Ralph：

1. `Work Unit Engine` 执行前必须跑 preflight review。
2. 批量任务需要 checkpoint，不允许一路跑到底。

### 4.4 subagent-driven-development

参考路径：

```text
/Users/jieson/superpowers-zh/skills/subagent-driven-development/SKILL.md
/Users/jieson/superpowers-zh/skills/subagent-driven-development/implementer-prompt.md
/Users/jieson/superpowers-zh/skills/subagent-driven-development/spec-reviewer-prompt.md
/Users/jieson/superpowers-zh/skills/subagent-driven-development/code-quality-reviewer-prompt.md
```

可借鉴：

1. 每个任务一个全新子 agent。
2. 不继承主会话上下文，精确构造任务上下文。
3. 两阶段审查：规格合规性，再代码质量。
4. 实现者状态：DONE、DONE_WITH_CONCERNS、NEEDS_CONTEXT、BLOCKED。

落到 Ralph：

1. 这正好对应“生成者不能自己验收自己”。
2. Ralph 的执行结果状态可借鉴这些状态，但要进入结构化状态机。
3. 不能用子 agent 口头报告替代证据。

### 4.5 verification-before-completion

参考路径：

```text
/Users/jieson/superpowers-zh/skills/verification-before-completion/SKILL.md
```

可借鉴：

1. 没有新鲜验证证据，不许宣称完成。
2. run -> read -> verify -> conclude。
3. 信任代理成功报告是失败模式。
4. 需求满足要逐项核对，不只是测试通过。

落到 Ralph：

1. `accepted` 前必须有 evidence。
2. final report 不能写“完成”，除非引用证据。

### 4.6 using-git-worktrees

参考路径：

```text
/Users/jieson/superpowers-zh/skills/using-git-worktrees/SKILL.md
```

可借鉴：

1. 隔离工作区。
2. 创建前验证 worktree 目录被 gitignore。
3. 基线测试失败时不继续。
4. 工作树位置、分支命名、依赖安装、基线验证流程。

落到 Ralph：

1. 并行 agent 阶段必须使用 worktree 或等价隔离。
2. MVP 可先顺序执行，但协议必须预留 worktree。

### 4.7 systematic-debugging

参考路径：

```text
/Users/jieson/superpowers-zh/skills/systematic-debugging/SKILL.md
```

可借鉴：

1. 不做根因调查，不许提修复方案。
2. 稳定复现。
3. 检查近期变更。
4. 多组件系统按边界加诊断。
5. 单一假设、最小测试。

落到 Ralph：

1. 测试失败后的返工任务不能直接“再试一次”。
2. `Review Manager` 和 `Verification Manager` 应生成 root cause task。

### 4.8 workflow-runner

参考路径：

```text
/Users/jieson/superpowers-zh/skills/workflow-runner/SKILL.md
```

可借鉴：

1. YAML 工作流。
2. DAG 依赖拓扑排序。
3. 每步角色文件。
4. 每步输出保存。
5. metadata.json。

落到 Ralph：

1. 可作为未来多角色 workflow DSL 的参考。
2. MVP 不直接做 YAML runner，但 `work_units` 可以采用同类 DAG 思想。

---

## 5. OpenSpec 借鉴清单

来源：

```text
官网: https://openspec.dev/
GitHub: https://github.com/Fission-AI/OpenSpec/
```

可借鉴：

1. specs live in code：规格和代码一起保存。
2. 按 capability 组织 specs。
3. 每个 change 都有 proposal、design、tasks、spec deltas。
4. review intent, not just code。
5. 规格是跨会话、跨 agent 的长期上下文，不随聊天消失。
6. 先 review/refine plan，再写代码。
7. 适合 brownfield codebase，不要求一开始生成全量 specs。

建议落地为 Ralph 的目录：

```text
.ralph/specs/
  current/
    auth-login/spec.md
    project-board/spec.md
  changes/
    add-remember-me/
      proposal.md
      design.md
      tasks.md
      specs/
        auth-session/spec.md
  archive/
```

和现有文档关系：

1. PRD 是项目级需求。
2. `.ralph/specs/current/` 是能力级长期事实源。
3. `.ralph/specs/changes/` 是变更提案和 spec delta。
4. `task_harness` 从具体 change 的 tasks 和 spec delta 派生。

Ralph 应吸收的规则：

1. 新功能不能直接改 current spec，先创建 change。
2. change 未通过 review 不能进入开发。
3. 开发完成后，change 才能 apply 到 current spec。
4. final report 要说明本次 apply 了哪些 spec delta。

---

## 6. multica 可借鉴代码清单

来源：

```text
本地路径: /Users/jieson/auto-coding/multica
License: modified Apache 2.0
注意: 内部本地使用可参考；如果未来做商业托管或嵌入产品，需要重新检查 LICENSE 条款。
```

### 6.1 daemon 主循环和 runtime 管理

参考路径：

```text
/Users/jieson/auto-coding/multica/server/internal/daemon/daemon.go
/Users/jieson/auto-coding/multica/server/internal/daemon/types.go
/Users/jieson/auto-coding/multica/server/internal/daemon/config.go
/Users/jieson/auto-coding/multica/server/internal/daemon/health.go
/Users/jieson/auto-coding/multica/server/internal/daemon/gc.go
```

可借鉴：

1. daemon 启动、注册 runtime、heartbeat、poll loop、task claim。
2. `activeTasks` 计数。
3. runtime health endpoint。
4. workspace sync loop。
5. GC meta 和任务目录清理。

Ralph 改造建议：

1. 可移植 daemon 框架思想。
2. 不直接照搬 server API，Ralph MVP 可先用本地文件状态。
3. health endpoint 可以直接参考接口形态。

### 6.2 task queue、状态和并发控制

参考路径：

```text
/Users/jieson/auto-coding/multica/server/internal/service/task.go
/Users/jieson/auto-coding/multica/server/migrations/022_task_lifecycle_guards.up.sql
/Users/jieson/auto-coding/multica/server/pkg/db/generated/agent.sql.go
```

可借鉴：

1. enqueue、claim、start、complete、fail、cancel。
2. `max_concurrent_tasks` 并发控制。
3. queued/dispatched 去重保护。
4. stale task failure。

Ralph 改造建议：

1. Ralph 的 work unit 状态机可参考 task lifecycle。
2. 去重索引思想可用于防止同一 work unit 被重复执行。
3. task claim 应结合 `task_harness` 和文件锁。

### 6.3 isolated exec environment

参考路径：

```text
/Users/jieson/auto-coding/multica/server/internal/daemon/execenv/execenv.go
/Users/jieson/auto-coding/multica/server/internal/daemon/execenv/context.go
/Users/jieson/auto-coding/multica/server/internal/daemon/execenv/runtime_config.go
/Users/jieson/auto-coding/multica/server/internal/daemon/execenv/codex_home.go
/Users/jieson/auto-coding/multica/server/internal/daemon/execenv/codex_sandbox.go
```

可借鉴：

1. 每个任务独立 envRoot/workdir/output/logs。
2. 任务目录可复用。
3. `.agent_context/issue_context.md`。
4. provider-native skill injection。
5. 写 `CLAUDE.md`、`AGENTS.md`、`GEMINI.md`。
6. cleanup 保留 output/logs。

Ralph 改造建议：

1. Ralph 的 `.ralph/runtime/tasks/<work_id>/` 可直接借鉴 execenv 结构。
2. context 文件应换成 Ralph 的 `context_pack.md/json`。
3. skill injection 可借鉴 provider 路径解析。

### 6.4 provider abstraction

参考路径：

```text
/Users/jieson/auto-coding/multica/server/pkg/agent/agent.go
/Users/jieson/auto-coding/multica/server/pkg/agent/claude.go
/Users/jieson/auto-coding/multica/server/pkg/agent/codex.go
/Users/jieson/auto-coding/multica/server/pkg/agent/opencode.go
/Users/jieson/auto-coding/multica/server/pkg/agent/openclaw.go
```

可借鉴：

1. `Backend` interface。
2. `ExecOptions`：cwd、model、system prompt、timeout、resume session、custom args、MCP config。
3. `Session` message stream 和 final result。
4. Claude stream-json 解析。
5. Codex app-server JSON-RPC。
6. token usage 统计。

Ralph 改造建议：

1. MVP 先实现 Claude provider，但接口按 provider abstraction 设计。
2. Claude runner 可参考 stream-json、session_id、MCP config 临时文件。
3. 不能照搬绕过权限模式；Ralph 必须走 Permission Guard。
4. `ToolAdapter` 的 Backend interface、ExecOptions、Session message stream 可直接借鉴 provider abstraction 的接口形态。
5. `LLM Provider Manager` 的 provider 注册、配置模型、能力声明、token 统计可直接借鉴 provider abstraction 的设计。
6. 统一执行结果 schema（exit_code、files_created、files_modified、stdout、stderr、token_usage）应借鉴 multica 的 result 结构。

### 6.5 session/workdir 复用

参考路径：

```text
/Users/jieson/auto-coding/multica/server/migrations/020_task_session.up.sql
/Users/jieson/auto-coding/multica/server/internal/daemon/types.go
/Users/jieson/auto-coding/multica/server/internal/daemon/daemon.go
```

可借鉴：

1. `prior_session_id`。
2. `prior_work_dir`。
3. 任务完成后回传 `session_id` 和 `work_dir`。
4. 下次同 issue 任务可 resume/reuse。

Ralph 改造建议：

1. Ralph 可以对同一个 story 复用 workdir，但验收任务必须用独立上下文。
2. session 复用不能跨越“生成者验收自己”的边界。

### 6.6 task message stream

参考路径：

```text
/Users/jieson/auto-coding/multica/server/migrations/026_task_messages.up.sql
/Users/jieson/auto-coding/multica/server/internal/daemon/client.go
/Users/jieson/auto-coding/multica/server/internal/daemon/daemon.go
/Users/jieson/auto-coding/multica/server/pkg/db/generated/task_message.sql.go
```

可借鉴：

1. task message seq。
2. text/thinking/tool-use/tool-result/status/error/log。
3. 增量读取 run messages。
4. 用于 dashboard 和调试。

Ralph 改造建议：

1. `.ralph/runtime/messages/<work_id>.jsonl` 可先用文件实现。
2. 后续 dashboard 可迁移为数据库表。

### 6.7 structured skills

参考路径：

```text
/Users/jieson/auto-coding/multica/server/migrations/008_structured_skills.up.sql
/Users/jieson/auto-coding/multica/server/internal/handler/skill.go
/Users/jieson/auto-coding/multica/server/cmd/multica/cmd_skill.go
/Users/jieson/auto-coding/multica/server/internal/daemon/execenv/context.go
```

可借鉴：

1. skill、skill_file、agent_skill 三表结构。
2. skill 有 content 和 supporting files。
3. 按 agent 注入 skills。

Ralph 改造建议：

1. Ralph 可以维护 `skills_registry.json`。
2. 根据任务类型注入 relevant skills，不全量加载。

### 6.8 MCP config

参考路径：

```text
/Users/jieson/auto-coding/multica/server/migrations/046_agent_mcp_config.up.sql
/Users/jieson/auto-coding/multica/server/pkg/agent/agent.go
/Users/jieson/auto-coding/multica/server/pkg/agent/claude.go
```

可借鉴：

1. agent 级 `mcp_config`。
2. 执行时写临时 MCP config 文件。
3. 传给 Claude `--mcp-config`。

Ralph 改造建议：

1. `task_harness` 可声明 `allowed_mcp_servers`。
2. UI 任务注入 Playwright MCP。
3. 非 UI 任务不注入 Playwright，减少上下文和权限面。

### 6.9 repo cache 和 worktree checkout

参考路径：

```text
/Users/jieson/auto-coding/multica/server/internal/daemon/repocache/cache.go
/Users/jieson/auto-coding/multica/server/internal/daemon/health.go
```

可借鉴：

1. bare repo cache。
2. per-task worktree。
3. checkout HTTP endpoint。
4. stale worktree prune。

Ralph 改造建议：

1. 并行阶段可借鉴。
2. MVP 可先在单一 repo 顺序执行，不必立即上 repo cache。

### 6.10 event bus、realtime、redaction

参考路径：

```text
/Users/jieson/auto-coding/multica/server/internal/events/bus.go
/Users/jieson/auto-coding/multica/server/internal/realtime/hub.go
/Users/jieson/auto-coding/multica/server/pkg/redact/redact.go
```

可借鉴：

1. in-process event bus。
2. WebSocket hub。
3. secret redaction。

Ralph 改造建议：

1. MVP 可先文件日志，不做 WebSocket。
2. redaction 可以较早引入，防止报告和日志泄露 token。

### 6.11 autopilot

参考路径：

```text
/Users/jieson/auto-coding/multica/server/internal/service/autopilot.go
/Users/jieson/auto-coding/multica/server/cmd/server/autopilot_scheduler.go
/Users/jieson/auto-coding/multica/server/migrations/042_autopilot.up.sql
```

可借鉴：

1. 定时或触发式 agent automation。
2. run history。
3. failure reason。

Ralph 改造建议：

1. 第一阶段不做完整 autopilot。
2. 后续可用于夜间巡检、定时回归、自动继续未完成任务。
3. `Issue Governance Manager` 的定时拉取、自动化决策、run history、failure reason 可直接借鉴 autopilot 的设计思想。
4. Issue 分类后的自动任务创建和状态流转，可参考 autopilot 的触发-执行-记录模式。

---

## 7. 复用优先级

第一阶段优先参考：

1. `multica/server/pkg/agent/agent.go`
2. `multica/server/pkg/agent/claude.go`
3. `multica/server/internal/daemon/execenv/execenv.go`
4. `multica/server/internal/daemon/execenv/context.go`
5. `multica/server/internal/daemon/execenv/runtime_config.go`
6. `multica/server/internal/service/task.go`
7. `multica/server/migrations/026_task_messages.up.sql`
8. `multica/server/pkg/redact/redact.go`
9. `multica/server/pkg/agent/codex.go`（ToolAdapter 扩展参考）
10. `multica/server/pkg/agent/opencode.go`（ToolAdapter 扩展参考）
11. `multica/server/internal/daemon/execenv/runtime_config.go`（LLM Provider 配置参考）
12. `multica/server/internal/service/autopilot.go`（Issue 治理触发模式参考）

第二阶段参考：

1. `multica/server/internal/daemon/repocache/cache.go`
2. `multica/server/internal/realtime/hub.go`
3. `multica/server/internal/events/bus.go`
4. `multica/server/internal/service/autopilot.go`

---

## 8. 开发时必须避免的误用

1. 不要照搬 multica 的 issue 平台抽象来替代 Ralph 的 PRD/story/task/work_unit。
2. 不要照搬任何 bypass permissions 思路。
3. 不要让 skill injection 变成全量 skill 上下文加载。
4. 不要让 session resume 破坏独立验收。
5. 不要把 OpenSpec 的轻量 proposal 当成完整工程验收。
6. 不要把 Superpowers 的人工交互流程原样搬进无人值守模式。
7. 不要让 agent-skills 的建议停留在 prompt 层，必须转成 runtime schema、状态机和证据门禁。

---

## 9. 对现有 Ralph 文档的影响

需要同步到 Ralph 设计中的明确要求：

1. 增加 OpenSpec-style `.ralph/specs/current` 和 `.ralph/specs/changes`。
2. 增加 `Task Harness Manager`，已经写入实施方案。
3. 增加 `Context Pack Manager` 对标 context-engineering。
4. 增加 `Spec Change Manager` 对标 OpenSpec。
5. 增加 `Source Docs Check` 对标 source-driven-development。
6. 增加 `Decision Log / ADR` 对标 documentation-and-adrs。
7. 将 multica 代码路径作为开发参考索引写入实施方案。
8. 增加 `ToolChain Manager`，借鉴 multica provider abstraction 设计 `ToolAdapter` 接口和适配器注册表。
9. 增加 `LLM Provider Manager`，借鉴 multica provider abstraction 和 runtime_config 实现 Provider 配置、模型预设和任务路由。
10. 增加 `Issue Governance Manager`，借鉴 multica autopilot 的触发-执行-记录模式，实现 Issue 拉取、分类和自动处理。
