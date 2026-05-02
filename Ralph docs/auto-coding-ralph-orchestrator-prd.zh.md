# Auto Coding 重构为 Ralph Orchestrator 产品需求文档

版本：v1.1 拆分版  
日期：2026-04-30  
文档语言：中文  
当前阶段：PRD 阶段，不编写代码  

---

## 1. 文档拆分说明

当前文档只保留产品需求和决策边界。详细实现和协议拆到以下文档：

1. `docs/auto-coding-ralph-orchestrator-implementation-plan.zh.md`：实施方案。
2. `docs/auto-coding-ralph-orchestrator-ai-protocol.zh.md`：AI 协同协议和上下文隔离规则。
3. `docs/auto-coding-ralph-orchestrator-mvp-checklist.zh.md`：MVP 范围和验收清单。
4. `docs/auto-coding-ralph-orchestrator-reference-map.zh.md`：外部技能思想和本地可复用代码索引。

拆分目的：

1. 避免单个文档过长导致 AI 使用时上下文污染。
2. 让 PRD、实施方案、协议规范、验收清单各司其职。
3. 后续每个 agent 只读取自己需要的文档片段。

---

## 2. 背景

用户希望构建一个能够自动完成较大软件项目开发的系统。最初方向是优化 Ralph skill，让 Claude Code 在 skill 约束下自动完成项目开发。经过讨论后，当前判断是：

```text
纯 skill 不适合承担长期、复杂、可恢复、多 agent 协作的软件项目开发。
```

更合理的方向是：

```text
以 /Users/jieson/auto-coding 为基础，
重构为 Ralph Orchestrator。
```

Ralph Orchestrator 不是一个更长的提示词，也不是一个单独“更聪明”的 agent，而是一个自动开发调度系统。它负责长期记忆、任务拆解、调度、权限控制、上下文重建、测试验收、阻塞处理和最终报告；Claude Code 只负责执行边界清晰的小任务。

---

## 3. 核心结论

本项目不应从零开发一个新的 agent，也不应继续把能力主要压在 Ralph skill 上。

推荐路线：

```text
重构 auto-coding
  → 升级为 Ralph Orchestrator
  → Claude Code 作为短任务执行器
  → Ralph skill 作为执行规范和入口辅助
  → Superpowers、Playwright MCP、相关 skills 按需参与
```

系统核心职责：

```text
把大项目拆成足够小、足够清晰、可验证、可恢复的任务，
再调度 Claude Code 一次只执行一个很小的开发动作。
```

---

## 4. 用户目标

用户希望实现的是一个能够辅助甚至自动完成完整项目开发的系统，尤其适合用户睡觉、离开电脑、或者不想反复手动提示时，系统仍能安全推进。

真实目标包括：

1. AI 和用户先共同讨论需求，而不是用户一开始就必须定义完整需求。
2. 系统能用非技术语言把需求问透，再转成技术 PRD。
3. 系统能把需求拆得非常细，避免大模型只做出“看起来像那么回事”的粗糙模块。
4. 系统能提前分析代码耦合、模块边界和接口关系。
5. 系统能定义接口合同，避免多个 agent 并行开发时互相打架。
6. 系统能调度多个 Claude Code agent 并行工作。
7. 系统能让 agent 之间通过共享工作区协作。
8. 系统能解决 Claude Code 长任务中的上下文腐烂、遗忘约束、执行变粗等问题。
9. 系统能安全运行，不能依赖无保护的危险权限模式。
10. 系统能区分安全操作和危险操作。
11. 系统能在删除单个文件前自动备份，禁止大规模危险删除。
12. 系统能在卡死、中断、跑偏后恢复。
13. 系统能根据任务类型按需使用 Superpowers、Playwright MCP、frontend-design、UI/UX 等能力。
14. 系统能通过测试、review、Playwright 证据确认功能真的可用。
15. 系统能生成详细中文研发报告，让用户看懂发生了什么。

---

## 5. 不做什么

第一阶段不做以下事情：

1. 不做一个完全从零开始的新 agent 平台。
2. 不把 Ralph 做成一个单纯靠 `SKILL.md` 长时间执行的大 skill。
3. 不承诺完全无条件无人值守。
4. 不使用无保护的危险权限模式作为默认方案。
5. 不让 Claude Code 一次执行大而模糊的任务。
6. 不把“技能绑定”做成所有环节强制加载。
7. 不先追求漂亮 dashboard，而是先追求可靠闭环。

---

## 6. 产品定位

Ralph Orchestrator 是一个本地自动开发调度系统。

它不是：

```text
一个更厉害的提示词
一个更长的 skill
一个让 Claude Code 一口气完成整个项目的入口
```

它是：

```text
项目经理 + 架构协调者 + 任务调度器 + 安全执行器 + 验收系统
```

它把 Claude Code 视为短任务开发工人，而不是把 Claude Code 当作长期记忆的唯一来源。

---

## 7. 总体工作流

系统应按以下阶段工作：

```text
阶段 0：需求共创
阶段 1：PRD 冻结
阶段 2：代码库侦察
阶段 3：模块耦合分析
阶段 4：接口合同定义
阶段 5：任务细拆
阶段 6：执行计划生成
阶段 7：Claude Code 短任务执行
阶段 8：review 和测试
阶段 9：集成和回归
阶段 10：报告和交付
```

每个阶段都要产生可持久化文件，不能只存在于当前对话上下文中。

---

## 8. 核心原则

### 8.1 系统负责长期控制

```text
系统负责长期记忆、拆解、调度、验收。
Claude Code 负责完成一个很小、边界明确的开发动作。
```

最高边界是：

```text
Ralph Orchestrator 的所有关键流程都在 Claude Code 外部执行。
Claude Code 只执行由 Ralph 生成的、带 context_pack 和 task_harness 的短任务。
Claude Code 的 session resume 只能作为性能优化，不能作为长期记忆来源。
```

因此，需求共创、PRD、spec、任务拆解、上下文包、权限判断、验收标准、review、证据汇总和最终报告，都必须由 Ralph Orchestrator 外部状态系统连接起来。Claude Code 内部的对话上下文可以复用，但不能被当成事实来源。

Claude Code 单次任务必须尽量满足：

1. 只对应一个清晰开发动作。
2. 修改范围有限。
3. 有明确输入和输出。
4. 有明确不能修改的边界。
5. 有明确验收条件。
6. 有测试或检查方式。
7. 失败后可以回滚或重试。
8. 理想执行时间在 10 到 30 分钟内。

### 8.2 AI 工作单元必须 Harness 化

系统必须借鉴 harness 工程思想，为 AI 要做的每一项工作建立可重复、可观察、可验收、可返工的约束环境。

这里的 harness 不只是传统测试里的 test harness。传统 test harness 强调用测试数据、driver、stub、执行引擎和报告来验证软件；AI harness 要把这个思想扩展到每个 AI 任务外部，形成“任务运行外壳”：

```text
任务输入
  → 上下文包
  → 权限边界
  → 执行环境
  → 可用工具
  → 禁止动作
  → 检查点
  → 验收标准
  → 证据收集
  → 失败重试
  → 回滚和阻塞
```

换句话说，Ralph Orchestrator 不能只告诉 AI “请认真做”。它必须给每个任务配置一个 `task_harness`，让 AI 在这个外壳内执行，并由 runtime 检查结果是否合格。

AI 做的每一件关键事情都必须被验收，包括：

1. brainstorm。
2. PRD 生成。
3. 代码库侦察。
4. 耦合分析。
5. 接口合同。
6. 任务拆解。
7. 开发执行。
8. review。
9. 测试。
10. 报告。

如果一个工作单元没有验收标准或没有 `task_harness`，系统不得执行它。

每个 `task_harness` 至少要定义：

1. 任务目标。
2. 允许读取的上下文。
3. 允许修改的范围。
4. 禁止修改的范围。
5. 允许使用的工具和命令。
6. 禁止使用的工具和命令。
7. 执行前检查。
8. 执行中检查点。
9. 执行后验收标准。
10. 必须保存的证据。
11. 失败后的重试策略。
12. 回滚方式。
13. 阻塞条件。
14. 独立验收者。
15. 状态更新规则。

这些约束必须尽量由 runtime、schema、状态机、文件锁、diff 检查、测试命令和证据检查强制执行，而不是只靠提示词提醒 AI。

### 8.3 生成者不能自己验收自己

这是防止上下文污染的最高优先级原则：

```text
同一个 agent、同一个上下文、同一轮推理产生的结果，
不能由它自己判定合格。
```

原因是：如果验收者带着生成过程里的假设、偏见和遗漏去检查结果，很容易“顺着原来的错误继续认为没问题”。

因此：

1. brainstorm 结果不能由 brainstorm agent 自己判定合格。
2. PRD 草案不能由 PRD 生成 agent 自己判定合格。
3. 任务拆解不能由拆解 agent 自己判定颗粒度合格。
4. 验收标准不能只由任务分配者制定后直接使用。
5. 代码执行 agent 不能自己宣布任务完成。
6. review agent 不能只复述执行 agent 的自述。
7. 报告 agent 不能凭记忆总结，必须引用证据。

详细规则见：

```text
docs/auto-coding-ralph-orchestrator-ai-protocol.zh.md
```

---

## 9. 核心需求

### 9.1 需求共创

系统必须支持面向非技术用户的深度 brainstorm。目标不是尽快开始写代码，而是用用户听得懂的问题，把产品目标、用户流程、业务规则、边界状态、验收标准问到足够清楚，再由系统转换成技术 PRD、开发任务和验收规则。

brainstorm 必须边问边记录，并经过独立验收。

### 9.2 PRD 冻结

进入自动执行前，必须有冻结的 PRD。冻结不代表永远不能改，而是代表当前自动执行周期按这份 PRD 开发，新增想法进入变更队列。

PRD 冻结后，应建立 OpenSpec-style 规格库：

```text
.ralph/specs/current/
.ralph/specs/changes/
.ralph/specs/archive/
```

新需求先进入 change proposal，经 review 后再转为任务和 `task_harness`。

### 9.3 任务颗粒度门禁

用户故事不能直接交给 Claude Code 执行。必须拆成开发任务，再拆到 Claude Code 单次执行任务。

任务不满足以下条件时不得执行：

1. 目标清晰。
2. 范围明确。
3. 依赖明确。
4. 有验收标准。
5. 有测试或检查方式。
6. 失败后可回滚或重试。

### 9.4 代码库侦察和耦合分析

执行开发前，系统必须先理解现有项目。侦察和耦合分析至少覆盖技术栈、目录结构、启动命令、测试命令、构建命令、模块边界、共享文件、接口关系、数据模型和状态管理关系。

### 9.5 接口合同

多个 agent 并行开发前，必须尽量先冻结接口合同。任何 agent 不能擅自修改合同，如确实需要修改，必须创建合同变更申请。

### 9.6 多 agent 协作

系统需要支持调度 agent、执行 agent、审查 agent 等角色。角色之间通过结构化文件和状态机协作，而不是靠口头记忆。

### 9.7 上下文腐烂控制

系统必须假设 Claude Code 长时间执行一定会遗忘、变粗、跑偏或丢约束。因此每次任务都要从持久化文件重建上下文，只读取当前任务需要的最小上下文。

### 9.8 权限和安全

安全目标是：

```text
允许安全无人值守。
禁止危险无人值守。
```

安全任务可自动推进；危险操作、不可逆操作、权限不明操作进入阻塞队列。

### 9.9 阻塞队列

系统不能因为一个问题就卡死。当遇到无法安全自动处理的问题时，应进入阻塞队列。不相关任务可以继续推进。

### 9.10 真实可用性验收

完成不能基于 agent 自称。完成必须基于证据，包括 diff、测试输出、Playwright 截图或 trace、用户路径执行记录、控制台错误、网络错误和 review 结论。

### 9.11 Playwright MCP

涉及前端、页面、交互、表单、登录、工作流时，系统应使用 Playwright MCP 或等价能力进行真实浏览器验证。

### 9.12 Superpowers 和 skills

Superpowers、frontend-design、UI/UX、安全审查等能力应按需使用，不能所有环节强制加载。

外部 skill 思想必须先被 Ralph 转换成模块规则、schema、门禁或检查表，再进入执行流程。不能把多个 skill 原文同时塞给 Claude Code，让 Claude Code 自己决定听谁。

借鉴关系按模块归属：

1. 需求共创主要借鉴 Superpowers brainstorming，但由 Ralph 增加边问边记录和独立需求完整度验收。
2. PRD、spec 和变更管理主要借鉴 OpenSpec 和 spec-driven-development。
3. 任务拆解主要借鉴 planning-and-task-breakdown、incremental-implementation 和 Superpowers writing-plans。
4. 上下文包主要借鉴 context-engineering，并由 Ralph 控制 context budget 和 trust level。
5. 执行调度主要借鉴 multica 的 provider、execenv、task queue 和 task message stream。
6. 验收主要借鉴 verification-before-completion、code-review-and-quality、browser-testing-with-devtools 和 Playwright MCP。

当两个参考来源冲突时，优先级为：

```text
Ralph PRD / AI 协议
  > task_harness
  > runtime schema / 状态机 / 权限控制
  > 安全规则
  > 证据
  > 外部 skill 建议
  > Claude Code 当前 session 记忆
```

### 9.13 最终报告

任务执行结束后，系统必须生成中文研发报告，说明开发过程、完成内容、证据、阻塞项、风险、未完成事项和建议下一步。

### 9.14 编程工具可扩展性

系统不能锁定在单一 CLI 工具上。当前默认对接 Claude Code，但必须通过 `ToolAdapter` 抽象接口支持扩展更多编程工具：

1. **ToolAdapter 抽象接口**：统一封装工具调用、结果解析、状态上报和错误处理，屏蔽底层差异。
2. **内置适配器**：Claude Code（默认）、Codex、Aider、Cline、OpenClaw 等。
3. **配置驱动**：`.ralph/config/toolchain.yaml` 声明启用的工具、优先级和回退策略。
4. **能力声明**：每个适配器必须声明自身支持的能力（如 MCP、session resume、stream output、tool use），调度系统根据任务 harness 匹配最优工具。
5. **统一结果格式**：无论底层工具是什么，返回给 Ralph 的执行结果必须符合同一 schema（exit code、文件变更、证据、stdout/stderr、token usage）。
6. **安全策略不变**：所有工具都必须经过 Permission Guard，不能因为有了新适配器就绕过备份和阻塞机制。

### 9.15 可配置 LLM Provider 前端

系统前端（dashboard）必须支持用户配置和管理 LLM Provider，而不是写死单一模型：

1. **Provider 管理层**：支持 DeepSeek、Qwen、Kimi、ChatGPT、Gemini、Claude、Claude Code Switch、自定义 OpenAI-compatible 等。
2. **三层配置模型**：
   - `LLMProvider`：API 基础配置（base_url、api_key、默认模型）。
   - `LLMModelPreset`：模型级参数（temperature、max_tokens、top_p 等）。
   - `ModelAssignment`：任务级路由规则（brainstorm 用轻量模型、代码生成用强模型、review 用独立模型）。
3. **前端可配**：dashboard 提供 Provider 增删改查、密钥安全存储（前端加密或后端代理）、模型预设模板、实时连通性测试。
4. **后端代理**：前端不直接携带密钥访问第三方 API，而是走后端代理路由，避免密钥泄露和 CORS 问题。
5. **降级策略**：当主 Provider 不可用时，按预设优先级自动切换备用 Provider，并记录切换事件。

### 9.16 智能 Issue 治理

系统必须能主动感知代码仓库中的问题，而不是等用户手动输入：

1. **Issue 源适配**：抽象 `IssueSource` 接口，支持 GitHub Issues（通过 API）和本地 issue 文件（如 `.ralph/issues/` 或项目目录中的 markdown）。
2. **自动拉取**：定时或手动触发拉取，去重后写入 Ralph 状态系统。
3. **智能分类**：结合规则引擎 + LLM 对 issue 进行分类：
   - `bug` / `feature` / `refactor` / `security` / `docs`
   - 严重级别：`critical` / `high` / `medium` / `low`
4. **策略驱动的自动处理**：用户可配置 `IssuePolicy`，对不同类型 issue 指定四种动作：
   - `auto_fix`：自动生成 work unit 并进入任务队列。
   - `require_approval`：生成处理建议，等待用户确认后再创建任务。
   - `ignore`：标记为忽略，不进入任务队列（可配置忽略原因和过期时间）。
   - `needs_investigation`：创建侦察任务，先分析根因再决定后续动作。
5. **人机协作**：自动处理的结果必须经过 Ralph 的标准验收流程，不能跳过 review 和证据收集。用户可随时覆盖系统自动决策。
6. **报告与可追溯**：Issue 治理的完整生命周期（发现 → 分类 → 决策 → 执行 → 验收）必须记录到执行日志和最终报告中。

---

## 10. MVP 范围

第一版先跑通可靠闭环：

```text
需求冻结
  → 任务细拆
  → 代码库侦察
  → 接口合同
  → 单任务 Claude Code 执行
  → 测试
  → review
  → 报告
  → 可恢复
```

MVP 必须包含：

1. 中文 PRD 管理。
2. story 和 dev task 管理。
3. 任务颗粒度门禁。
4. 状态持久化。
5. `task_harness` 契约。
6. Claude Code 短任务调用。
7. 执行日志。
8. 阻塞队列。
9. 安全权限策略。
10. 单文件删除备份。
11. 测试结果记录。
12. review 流程。
13. 用户路径验收。
14. Playwright 真实点击验收。
15. 多尺寸截图验收。
16. 边界状态检查清单。
17. review 问题转任务机制。
18. 中文研发报告。
19. `ToolAdapter` 抽象接口和 Claude Code 适配器。
20. LLM Provider 基础配置模型（至少支持 Claude 和一种自定义 OpenAI-compatible）。
21. Issue 源抽象和本地 issue 文件读取能力。

MVP 暂不必须包含：

1. 完整 Web dashboard。
2. 大规模并行。
3. 复杂权限 UI。
4. 团队多人协作。
5. Codex、Aider、Cline 等额外工具适配器。
6. GitHub Issues 实时同步和自动拉取。
7. LLM 驱动的 Issue 自动分类和自动修复。
8. 多 Provider 自动降级和负载均衡。

---

## 11. 成功标准

系统成功的标准不是“agent 说完成了”，而是：

1. 用户能用中文说清一个项目想法。
2. 系统能帮助用户形成 PRD。
3. 系统能把需求拆成细任务。
4. 每个任务足够小，Claude Code 不需要长时间记住全局。
5. 每个关键 AI 工作单元都有验收标准。
6. 生成者不能自己验收自己。
7. 系统能自动推进安全任务。
8. 危险任务会被拦截并说明原因。
9. 中断后能恢复。
10. 用户能看到当前进度。
11. 最终有测试、截图、日志、review 证据。
12. 用户常见路径已经被真实浏览器执行过。
13. 常见边界状态已经被检查过。
14. 前端页面在主要屏幕尺寸下没有明显错位。
15. review agent 发现的问题已经转成返工、补测试或阻塞项。
16. 人工验收从“到处找 bug”降低为“产品判断和少量抽查”。

---

## 12. 关键风险

1. 任务拆解仍然太粗。
2. brainstorm 问得不够深。
3. 上下文污染导致验收放水。
4. 验收标准本身有盲区。
5. 权限控制不牢。
6. 过度依赖提示词。
7. 过度相信 AI review。
8. 系统本身过早复杂化。

对应控制措施详见：

```text
docs/auto-coding-ralph-orchestrator-ai-protocol.zh.md
docs/auto-coding-ralph-orchestrator-mvp-checklist.zh.md
```

---

## 13. 已确认设计前提

当前方案按以下前提推进：

1. 重构 auto-coding 为主，Ralph skill 为辅。
2. MVP 先做命令行和文件状态，不先做完整 dashboard。
3. 第一阶段先做可靠顺序执行，再扩展多 agent 并行。
4. 任务颗粒度门禁是最高优先级能力之一。
5. 系统追求安全无人值守，而不是无条件无人值守。
6. 真实可用性验收系统和任务颗粒度门禁同等重要。
7. 生成者不能自己验收自己。
8. 所有关键流程都在 Claude Code 外部执行。
9. 外部 skill 思想必须先被 Ralph 吸收成模块规则、schema、状态机、检查表或证据门禁。

进入开发前，剩余需要确认的是 MVP 第一批具体任务顺序和技术实现细节，不再是产品方向问题。

---

## 14. 当前结论

```text
不要再把 Ralph 设计成纯 skill。
不要从零开发新 agent。
应该重构 auto-coding，
把它升级成 Ralph Orchestrator。
```

第一阶段目标不是“全自动完成任何项目”，而是先建立可靠闭环：

```text
需求清楚
任务够细
上下文隔离
上下文可恢复
权限可控
执行可审计
验收有证据
报告能看懂
```

只有这个闭环稳定后，才继续扩展并行 agent、dashboard 和更复杂的自动化能力。
