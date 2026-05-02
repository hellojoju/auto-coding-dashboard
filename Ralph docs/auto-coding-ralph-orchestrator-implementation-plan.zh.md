# Ralph Orchestrator 实施方案

版本：v1.0 草案  
日期：2026-04-30  
文档语言：中文  
依赖文档：

```text
docs/auto-coding-ralph-orchestrator-prd.zh.md
docs/auto-coding-ralph-orchestrator-ai-protocol.zh.md
docs/auto-coding-ralph-orchestrator-mvp-checklist.zh.md
docs/auto-coding-ralph-orchestrator-reference-map.zh.md
```

---

## 1. 实施目标

本方案的目标是把 `/Users/jieson/auto-coding` 重构为 Ralph Orchestrator。

系统形态：

```text
auto-coding / Ralph Orchestrator 作为主系统
  → 调用 Claude Code 执行短任务
  → 使用 Ralph skill 作为 Claude Code 内部执行规范
  → 使用结构化状态文件保存长期记忆
  → 使用测试、review、Playwright 和证据文件验收
```

关键边界：

```text
所有关键流程都在 Claude Code 外部执行。
Claude Code 只接收 Ralph 生成的短任务、context_pack 和 task_harness。
Claude Code 的 session resume 只用于减少重复读取和提升执行效率，不能作为长期记忆、验收依据或状态事实来源。
```

第一阶段不追求完整平台，而是先跑通可靠闭环。

---

## 2. 重构原则

1. 保留 auto-coding 中已有的状态管理、agent 进程管理、阻塞问题、执行日志、workspace 概念。
2. 不继续堆提示词能力，而是建设状态机、schema 校验、证据记录和权限控制。
3. Claude Code 只做短任务执行，不承担长期项目记忆。
4. 每个 AI 工作单元必须有输入、输出、验收标准、证据和返工规则。
5. 生成者不能自己验收自己。
6. 协议和数据结构先稳定，dashboard 后做。

---

## 3. 建议目录结构

Ralph Orchestrator 在目标项目中创建 `.ralph/` 目录：

```text
.ralph/
  config/
  prd/
  specs/
    current/
    changes/
    archive/
  brainstorm/
  plans/
  analysis/
  contracts/
  tasks/
  harnesses/
  work_units/
  context_packs/
  reviews/
  evidence/
  blockers/
  backups/
  runtime/
  reports/
```

说明：

1. `brainstorm/` 保存用户问答、需求事实、未确认假设、brainstorm 验收报告。
2. `prd/` 保存 PRD 草案、冻结版 PRD、变更队列。
3. `specs/` 保存 OpenSpec-style 当前规格、变更提案和归档。
4. `analysis/` 保存代码库侦察和耦合分析。
5. `contracts/` 保存接口合同和合同变更申请。
6. `tasks/` 保存 story、dev task、依赖图。
7. `harnesses/` 保存每个任务的 `task_harness` 契约。
8. `work_units/` 保存每个 AI 工作单元的结构化定义和状态。
9. `context_packs/` 保存每次调用 Claude Code 的最小上下文包。
10. `reviews/` 保存独立 review 结果。
11. `evidence/` 保存测试输出、截图、trace、日志。
12. `blockers/` 保存阻塞项。
13. `reports/` 保存面向用户的中文报告。

---

## 4. 核心模块

### 4.1 State Repository

职责：

1. 作为系统唯一事实来源。
2. 保存任务、工作单元、阻塞项、证据、状态流转记录。
3. 提供原子写入，避免多 agent 并发写坏状态。
4. 拒绝非法状态流转。

### 4.2 Work Unit Engine

职责：

1. 创建 AI 工作单元。
2. 校验工作单元是否有验收标准。
3. 调度工作单元进入运行。
4. 根据独立验收结果决定 accepted、needs_rework、blocked。
5. 记录每次返工原因。

### 4.3 Task Harness Manager

职责：

1. 为每个 AI 工作单元生成 `task_harness`。
2. 校验任务是否具备执行前门禁。
3. 限制上下文来源、工具、命令和文件修改范围。
4. 记录执行中检查点、工具调用、文件变更和异常。
5. 检查执行后验收门禁。
6. 收集证据文件。
7. 根据失败类型触发重试、回滚或阻塞。
8. 拒绝没有 harness 或违反 harness 的任务进入 `accepted`。

### 4.4 Brainstorm Manager

职责：

1. 用非技术语言和用户讨论需求。
2. 边问边记录用户原话、系统理解、已确认事实、未确认假设。
3. 生成 brainstorm 输出物。
4. 调用独立需求完整度 review。
5. 未通过验收时继续追问。

### 4.5 PRD Manager

职责：

1. 根据 brainstorm 输出生成 PRD 草案。
2. 维护冻结版 PRD。
3. 维护需求变更队列。
4. 生成从用户原始回答到 PRD 条目的追溯关系。

### 4.6 Spec Change Manager

职责：

1. 维护 OpenSpec-style 规格库。
2. 保存 `.ralph/specs/current/` 中的能力级当前事实源。
3. 为新需求创建 `.ralph/specs/changes/<change_id>/proposal.md`、`design.md`、`tasks.md` 和 spec delta。
4. change 未通过 review 前，不允许进入开发。
5. 开发完成并验收通过后，将 change apply 到 current specs 并归档。

### 4.7 Context Pack Manager

职责：

1. 按 context-engineering 思想组装最小上下文包。
2. 区分规则、PRD/spec、相关源文件、错误输出、历史摘要。
3. 标记 untrusted data，如浏览器 DOM、console、network 响应、外部文档内容。
4. 禁止把全量长文档塞给每个 agent。

### 4.8 Source Docs Check

职责：

1. 识别项目依赖版本。
2. 对框架关键实现、升级、安全、部署任务拉取官方文档。
3. 将外部文档作为参考数据，而不是指令。
4. 记录引用来源，供 review 和最终报告使用。

### 4.9 Decision Log / ADR Manager

职责：

1. 记录重要架构、接口、权限、安全、数据模型决策。
2. 保存 alternatives considered 和 consequences。
3. 支持 superseded/deprecated，不删除历史。

### 4.10 Repository Recon Analyzer

职责：

1. 识别技术栈、目录结构、启动命令、测试命令、构建命令。
2. 识别前端、后端、数据库、状态管理、路由、配置。
3. 生成代码库侦察报告。
4. 将结果写入结构化状态，而不是只写自然语言总结。

### 4.11 Coupling Analyzer

职责：

1. 分析文件级、模块级、接口级、数据模型级耦合。
2. 识别共享文件、高风险修改点、必须串行的任务。
3. 输出可并行任务和必须串行任务建议。

### 4.12 Contract Manager

职责：

1. 生成和维护接口合同。
2. 管理合同变更申请。
3. 约束 agent 不得擅自修改合同。
4. 在合同冻结后触发早期烟雾测试。

### 4.13 Task Decomposer

职责：

1. 把 PRD 拆成 story。
2. 把 story 拆成 dev task。
3. 把 dev task 拆成 Claude Code 单次执行任务。
4. 执行任务颗粒度门禁。
5. 生成任务依赖图。

### 4.14 Claude Code Runner

职责：

1. 根据 work unit 生成最小上下文包。
2. 调用 Claude Code 执行短任务。
3. 捕获输出、退出码、测试结果、修改文件列表。
4. 不依赖长对话记忆推进任务。
5. 每次调用都注入当前 `context_pack` 和 `task_harness`。
6. 如果使用 session resume，只把它作为性能优化，不把 session 内记忆当成事实来源。
7. 执行完成后只提交 `execution_result` 和证据，不直接把任务标记为 `accepted`。

### 4.15 Permission Guard

职责：

1. 区分自动允许、需要备份、需要阻塞、永远禁止的操作。
2. 删除单个普通文件前先备份。
3. 大规模删除、密钥修改、数据库删除、发布命令等进入阻塞。

### 4.16 Review Manager

职责：

1. 调用独立 review。
2. 按 review 类型检查功能完整性、边界状态、假实现、接口一致性、UI 风险、测试有效性。
3. 将 review 问题转换为返工任务、补测试任务、补 Playwright 验收任务或阻塞项。

### 4.17 Verification Manager

职责：

1. 运行单元测试、集成测试、lint、typecheck、build。
2. 运行 Playwright 用户路径测试。
3. 生成多尺寸截图。
4. 保存控制台错误、网络错误、trace 和失败复现步骤。

### 4.18 Report Generator

职责：

1. 汇总已完成任务、证据、阻塞项、风险、返工记录。
2. 生成中文研发报告。
3. 报告必须引用证据文件，不得凭记忆总结。

### 4.19 ToolChain Manager

职责：

1. 管理 `ToolAdapter` 注册表，支持 Claude Code、Codex、Aider、Cline、OpenClaw 等适配器。
2. 根据 `task_harness` 中声明的 `tool_adapter` 和 `adapter_capabilities_required` 匹配最优工具。
3. 统一封装执行请求（context_pack、scope、timeout、mcp_servers、env_vars）。
4. 统一解析执行结果（exit_code、文件变更、stdout/stderr、evidence、token_usage）。
5. 管理适配器生命周期：加载、健康检查、降级、卸载。
6. 维护 `.ralph/config/toolchain.yaml` 配置。
7. 确保所有适配器都经过 Permission Guard，不因为工具切换绕过安全策略。

### 4.20 LLM Provider Manager

职责：

1. 管理 `LLMProvider`、`LLMModelPreset`、`ModelAssignment` 三层配置。
2. 支持多种 Provider：DeepSeek、Qwen、Kimi、ChatGPT、Gemini、Claude、Claude Code Switch、自定义 OpenAI-compatible。
3. 提供 Provider 连通性测试和健康检查。
4. 实现后端代理路由：前端不直接访问第三方 API，统一走后端代理。
5. 实现密钥安全存储：支持环境变量、加密存储或外部密钥管理器。
6. 实现模型降级策略：主 Provider 不可用时按优先级自动切换备用 Provider。
7. 根据任务类型路由模型：brainstorm 用轻量模型、代码生成用强模型、review 用独立模型。
8. 记录 token 使用量和调用日志，供成本分析使用。

### 4.21 Issue Governance Manager

职责：

1. 管理 `IssueSource` 适配器：GitHub Issues（API 拉取）和本地 issue 文件（目录监听）。
2. 定时或手动触发 issue 拉取，去重后写入状态系统。
3. 实现 `IssueClassifier`：规则引擎 + LLM 两阶段分类。
4. 管理 `IssuePolicy`：分类到处理动作的映射规则。
5. 根据策略自动创建 work unit（`auto_fix`）、生成审批建议（`require_approval`）、标记忽略（`ignore`）或创建侦察任务（`needs_investigation`）。
6. 将 issue 处理状态回写到源系统（如 GitHub label、comment）。
7. 记录完整 issue 生命周期日志，纳入最终报告。
8. 支持用户覆盖系统自动决策，并记录覆盖理由。
9. 对安全相关 issue 强制进入额外安全 review 队列。

---

## 5. 分阶段实施

### 5.1 阶段一：可靠顺序执行

目标：先让系统稳定完成一个个小任务。

必须实现：

1. `.ralph/` 目录结构。
2. 工作单元 schema。
3. `task_harness` schema。
4. 任务执行前、执行中、执行后 harness 门禁。
5. 状态机。
6. brainstorm 记录和验收。
7. PRD 冻结。
8. 任务细拆和颗粒度门禁。
9. Claude Code 短任务执行。
10. 独立 review。
11. 测试结果记录。
12. 中文报告。
13. `ToolAdapter` 抽象接口和 Claude Code 适配器。
14. LLM Provider 基础配置模型（至少支持 Claude 和一种自定义 OpenAI-compatible）。
15. Issue 源抽象和本地 issue 文件读取。

暂不实现：

1. 多 agent 并行。
2. 完整 dashboard。
3. Codex、Aider、Cline 等额外工具适配器。
4. GitHub Issues 实时同步。
5. LLM 驱动的 issue 自动分类和自动修复。
6. 多 Provider 自动降级。

### 5.2 阶段二：真实可用性验收

目标：减少“AI 都说没问题，用户一点全是 bug”的情况。

必须实现：

1. 用户路径验收。
2. Playwright 真实点击。
3. 多尺寸截图。
4. 控制台错误捕获。
5. 网络错误捕获。
6. 边界状态检查。
7. 探索式点击测试。

### 5.3 阶段三：隔离并行执行

目标：支持多个 agent 并行开发互不干扰。

必须实现：

1. 文件级锁。
2. git worktree 或隔离 workspace。
3. 并行任务调度。
4. 集成队列。
5. 合并冲突处理。
6. 集成后回归测试。

### 5.4 阶段四：可视化和长期运行

目标：让用户能像看项目管理系统一样观察和干预。

可以实现：

1. dashboard。
2. 实时日志。
3. 阻塞项处理界面。
4. 成本和耗时统计。
5. 历史项目复盘。
6. 多工具适配器（Codex、Aider、Cline 等）及其能力可视化。
7. LLM Provider 前端配置界面、模型预设管理、实时连通性测试。
8. GitHub Issues 同步、自动分类可视化、Issue 治理策略配置界面。
9. 多 Provider 自动降级和负载均衡监控。

---

## 6. 从 auto-coding 继承的能力

保留和加强：

1. 状态仓库：升级为系统唯一事实来源。
2. agent 进程管理：继续负责 Claude Code 子进程。
3. 阻塞问题模型：升级为正式阻塞队列。
4. 执行日志：升级为研发过程审计日志。
5. workspace 概念：升级为隔离工作区和协作工作区。
6. dashboard 雏形：后续作为观察和干预入口。

需要改造：

1. 弱任务拆解改为强颗粒度门禁。
2. prompt 约束改为 schema 和状态机约束。
3. 自述完成改为证据验收。
4. 危险权限改为 permission guard。
5. 简单 review 改为独立上下文 review。

---

## 7. 借鉴 multica 的能力

可借鉴：

1. daemon 模式。
2. task queue。
3. workspace 隔离。
4. session 和 workdir 复用。
5. task message 流。
6. runtime 健康检查。
7. 最大并发控制。
8. 任务取消机制。
9. 多 provider 抽象。
10. structured skills 注入。

不直接照搬：

1. 默认绕过权限的思路。
2. 偏 issue 分配平台，不是完整产品开发流程。
3. 对需求拆解和验收深度不足。
4. 对假完成和上下文腐烂控制不足。

---

## 8. 实施注意事项

1. 第一阶段先做 CLI 和文件状态，不做完整 dashboard。
2. 先保证一个任务可靠完成，再扩展并行。
3. 所有 AI 输出都必须结构化校验。
4. 所有 AI 工作单元都必须有 `task_harness`。
5. 所有最终验收都必须基于证据文件。
6. 验收 agent 必须使用独立上下文。
7. 任何“AI 必须遵守”的规则，都应尽量变成 runtime 强制校验。

---

## 9. 参考资料与可复用代码索引

开发时必须先阅读：

```text
docs/auto-coding-ralph-orchestrator-reference-map.zh.md
```

其中明确标注了：

1. `agent-skills` 哪些 skill 思想需要吸收。
2. `superpowers-zh` 哪些 skill 文件可参考。
3. OpenSpec 的 specs/changes/apply/archive 思想如何落到 `.ralph/specs/`。
4. `multica` 哪些本地代码文件可以作为实现参考或迁移对象。
5. 多个外部参考同时适用时，如何按模块归属和优先级处理冲突。

开发实施时不得让 Claude Code 直接同时加载多个外部 skill 原文。所有外部参考必须先由 Ralph Orchestrator 转换成模块职责、schema、`task_harness`、状态机、检查表或证据门禁。
5. 哪些内容不能照搬，尤其是绕过权限、粗任务分发和 prompt-only 约束。
