# Ralph Orchestrator AI 协同协议

版本：v1.0 草案  
日期：2026-04-30  
文档语言：中文  

---

## 1. 协议目标

本协议定义 Ralph Orchestrator 中 AI agent 之间如何协作。

更准确地说，Ralph Orchestrator 是 Claude Code 外部的长期控制系统。Claude Code、Codex、OpenClaw 等 agent 是短任务执行器，不是项目长期记忆、需求事实、验收结论或调度状态的事实来源。

核心不是“AI 之间怎么传消息”，而是：

```text
谁有权在什么时候改变什么状态，
输入什么数据，
输出什么数据，
如何验收，
出了问题怎么传播，
如何避免上下文污染。
```

---

## 2. 最高原则：生成者不能自己验收自己

同一个 agent、同一个上下文、同一轮推理产生的结果，不能由它自己判定合格。

这是为了避免上下文污染：

```text
生成者在生成结果时形成了某些假设和偏见。
如果它继续用同一上下文验收自己的结果，
它很容易忽略自己原本就没想到的问题。
```

因此，所有关键工作单元必须遵守：

1. 生成者负责产出。
2. 验收者使用独立上下文验收。
3. 验收者主要读取结构化输入、输出、验收标准和证据。
4. 验收者不得只依赖生成者自述。
5. 调度 agent 根据验收结果做最终状态决策。

---

## 3. 外部流程吸收规则

所有关键流程必须先被 Ralph Orchestrator 外部吸收、结构化和落盘，再作为短任务交给执行 agent。

必须在 Claude Code 外部完成的事项：

1. brainstorm 记录和需求完整度验收。
2. PRD 草案、冻结版 PRD 和变更队列。
3. OpenSpec-style current specs、change proposal、design 和 tasks。
4. 代码库侦察、耦合分析和接口合同。
5. work unit、context_pack 和 task_harness。
6. 权限判断、危险操作阻塞和备份策略。
7. 独立 review、Playwright 验收、证据汇总和最终报告。

执行 agent 可以使用 session resume，但必须遵守：

1. resume 不能替代 `context_pack`。
2. resume 不能替代 `.ralph/specs/current`、冻结 PRD 或任务状态。
3. resume 中的信息如果和结构化状态冲突，以结构化状态为准。
4. 调度 agent 不得因为执行 agent “记得之前的事”而省略输入、边界、验收标准或证据要求。

外部 skill、Superpowers、OpenSpec 和 multica 的思想都必须先转成 Ralph 的模块规则、schema、状态机、检查表或证据门禁。不能把多个 skill 原文同时注入给同一个执行 agent，让它自行解决冲突。

---

## 4. 上下文复用风险评估

| 模块 | 上下文污染风险 | 隔离要求 |
|------|----------------|----------|
| brainstorm | brainstorm agent 容易认为自己已经问够 | 需求完整度 review 必须由独立上下文执行 |
| PRD 生成 | PRD agent 容易把自己的假设写成需求 | PRD review 必须追溯用户原话和未确认假设 |
| 任务拆解 | 拆解 agent 容易把任务拆得仍然过粗 | 颗粒度 review 必须独立执行 |
| 验收标准制定 | 标准制定者容易遗漏自己没想到的场景 | 验收标准必须独立审查 |
| 代码库侦察 | 侦察 agent 可能漏掉关键目录或命令 | 用确定性命令和独立抽样复核 |
| 耦合分析 | 分析 agent 可能低估共享文件风险 | 依赖图和高风险文件需要独立复核 |
| 接口合同 | 合同作者可能设计出不可用接口 | 合同冻结后必须做早期烟雾测试 |
| 开发执行 | 执行 agent 容易宣布完成 | 执行 agent 只能提交执行结果，不能 accepted |
| 代码 review | review agent 可能被执行自述带偏 | review 只读 diff、任务、标准、证据，少读自述 |
| 测试生成 | 测试 agent 可能只测容易通过的路径 | 测试有效性 review 独立检查覆盖关系 |
| Playwright 验收 | 验收脚本可能只跑主路径 | 必须覆盖用户路径、失败路径和截图证据 |
| 报告生成 | 报告 agent 可能凭印象总结 | 报告必须引用状态、证据、阻塞项和日志 |

---

## 5. AI 工作单元结构

每个 AI 工作单元必须包含：

```text
work_id：工作编号
work_type：工作类型
producer_role：生成者角色
reviewer_role：验收者角色
input：输入材料
expected_output：预期输出
acceptance_criteria：验收标准
task_harness：任务运行外壳
context_pack：上下文包
execution_log：执行记录
evidence：证据
review_result：验收结果
retry_policy：返工规则
status：状态
```

如果缺少 `acceptance_criteria`、`producer_role`、`reviewer_role` 或 `task_harness`，工作单元不得进入 `ready`。

---

## 6. 任务 Harness 契约

每个任务都必须携带 `task_harness`。它是任务运行外壳，负责把 AI 的自由发挥限制在可观察、可验证、可恢复的工程流程里。

`task_harness` 必须包含：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| harness_id | 字符串 | 是 | harness 唯一标识 |
| task_goal | 字符串 | 是 | 当前任务要达成的目标 |
| context_sources | 列表 | 是 | 允许读取的上下文来源 |
| context_budget | 描述 | 是 | 上下文大小和读取边界 |
| allowed_tools | 列表 | 是 | 允许使用的工具或命令 |
| denied_tools | 列表 | 是 | 禁止使用的工具或命令 |
| tool_adapter | 字符串 | 否 | 指定 ToolAdapter（如 claude_code、coder、aider）；未指定时由调度系统根据任务类型和能力匹配 |
| adapter_capabilities_required | 列表 | 否 | 任务所需的适配器能力（如 mcp、session_resume、stream_output、tool_use） |
| scope_allow | 文件列表 | 是 | 允许修改范围 |
| scope_deny | 文件列表 | 是 | 禁止修改范围 |
| preflight_checks | 列表 | 是 | 执行前检查 |
| checkpoints | 列表 | 是 | 执行中检查点 |
| validation_gates | 列表 | 是 | 执行后验收门禁 |
| evidence_required | 列表 | 是 | 必须保存的证据 |
| retry_policy | 对象 | 是 | 失败重试规则 |
| rollback_strategy | 描述 | 是 | 回滚方式 |
| timeout_policy | 对象 | 是 | 超时规则 |
| stop_conditions | 列表 | 是 | 必须停止或阻塞的条件 |
| reviewer_role | 字符串 | 是 | 独立验收者角色 |
| status_transitions | 对象 | 是 | 允许的状态变化 |

### 6.1 执行前门禁

任务进入 `running` 前，runtime 必须检查：

1. `task_harness` 存在。
2. 上下文来源存在且可读取。
3. 允许修改范围明确。
4. 禁止修改范围明确。
5. 验收标准可判定。
6. 独立验收者已指定。
7. 需要的工具可用。
8. 阻塞条件未触发。

任一项不满足，任务不得执行。

### 6.2 执行中约束

任务执行中，runtime 必须记录：

1. 实际读取的上下文。
2. 实际调用的工具。
3. 实际修改的文件。
4. 检查点状态。
5. 超时情况。
6. 异常输出。

如果发现越界修改、危险命令、超时、上下文缺失或检查点失败，任务必须转为 `blocked` 或 `failed`。

### 6.3 执行后门禁

任务进入 `accepted` 前，runtime 必须检查：

1. 修改范围没有越界。
2. 必要证据已保存。
3. 测试或检查命令已执行。
4. 验收标准逐条有结果。
5. 独立 review 已完成。
6. 阻塞项为空或已被处理。
7. 下游影响已记录。

任一项不满足，任务不得进入 `accepted`。

### 6.4 harness 不是提示词

`task_harness` 不能只写在 prompt 里。它必须以结构化数据保存，并由 runtime 执行校验。

原则：

```text
能用 schema 校验的，不靠 AI 自觉。
能用状态机限制的，不靠 AI 记忆。
能用工具检查的，不靠 AI 自述。
能用证据证明的，不靠 AI 判断。
```

---

## 7. 状态流转协议

### 7.1 状态定义

| 状态 | 含义 | 允许进入的下一阶段 |
|------|------|-------------------|
| draft | 任务已创建，但尚未确认可执行 | ready |
| ready | 任务已确认，等待分配执行 | running |
| running | 执行 agent 正在执行 | needs_review / failed / blocked |
| needs_review | 执行完成，等待审查 | accepted / needs_rework / blocked |
| failed | 执行出错，无法完成 | ready / blocked |
| needs_rework | 审查不合格，需要返工 | ready |
| blocked | 遇到无法自动处理的问题 | ready |
| accepted | 验收通过，进入下一阶段 | 集成或下一个依赖任务 |

### 7.2 状态修改权限

调度 agent 可以：

1. 创建任务为 `draft`。
2. 确认任务可执行为 `ready`。
3. 分配任务为 `running`。
4. 根据审查结论把任务转为 `accepted`、`needs_rework` 或 `blocked`。
5. 决定失败任务是否重试。

执行 agent 可以：

1. 报告开始执行。
2. 报告执行完成。
3. 报告执行失败。
4. 报告阻塞。

审查 agent 可以：

1. 给出结构化审查结论。
2. 标记每条验收标准是否通过。
3. 提出返工、补测试、补 Playwright 验收或阻塞建议。

审查 agent 不直接修改最终状态。最终状态由调度 agent 根据协议修改。

---

## 8. 数据格式规范

### 8.1 任务定义格式

每个任务必须包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| work_id | 字符串 | 是 | 任务唯一标识 |
| work_type | 字符串 | 是 | 开发/测试/review/返工/侦察等 |
| title | 字符串 | 是 | 任务标题 |
| background | 字符串 | 是 | 背景说明 |
| target | 字符串 | 是 | 具体目标 |
| scope_allow | 文件列表 | 是 | 允许修改范围 |
| scope_deny | 文件列表 | 是 | 禁止修改范围 |
| dependencies | 任务 ID 列表 | 是 | 依赖任务 |
| input_files | 文件列表 | 是 | 输入文件或接口 |
| expected_output | 描述 | 是 | 预期输出 |
| acceptance_criteria | 列表 | 是 | 验收标准 |
| test_command | 字符串 | 是 | 测试或检查方式 |
| rollback_strategy | 描述 | 是 | 回滚方式 |
| task_harness | 对象 | 是 | 当前任务的 harness 契约 |
| assumptions | 列表 | 是 | 当前任务成立的前提假设 |
| impact_if_wrong | 描述 | 是 | 假设错误会造成什么影响 |
| risk_notes | 字符串 | 是 | 风险说明 |
| context | 对象 | 是 | 最小上下文包 |
| status | 字符串 | 是 | 当前状态 |

### 8.2 执行结果格式

执行 agent 完成后必须返回：

| 字段 | 类型 | 说明 |
|------|------|------|
| work_id | 字符串 | 对应任务 ID |
| status | 字符串 | needs_review / failed / blocked |
| files_created | 文件列表 | 新增文件 |
| files_modified | 文件列表 | 修改文件 |
| files_deleted | 文件列表 | 删除文件 |
| scope_violations | 列表 | 越界修改说明 |
| test_results | 对象 | 测试结果 |
| evidence_files | 文件列表 | 证据文件 |
| harness_events | 列表 | harness 执行过程中的关键事件 |
| harness_violations | 列表 | 违反 harness 约束的情况 |
| risks_observed | 字符串 | 执行中观察到的风险 |
| downstream_impact | 字符串 | 对下游任务的影响 |
| blocking_reason | 字符串 | 阻塞原因 |

### 8.3 审查结论格式

审查结论必须包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| work_id | 字符串 | 被审查任务 ID |
| reviewer_context_id | 字符串 | 独立审查上下文 ID |
| review_type | 字符串 | 功能完整性/边界状态/假实现/接口一致性/UI 风险/测试有效性等 |
| criteria_results | 列表 | 每条验收标准的通过/不通过结果 |
| issues_found | 列表 | 问题、严重程度、建议处理方式 |
| evidence_checked | 文件列表 | 审查时检查的证据 |
| harness_checked | 布尔值 | 是否检查了 task_harness 约束 |
| conclusion | 字符串 | 通过/不通过 |
| recommended_action | 字符串 | 接受/返工/补测试/补 Playwright 验收/阻塞 |

---

## 9. 上下文包规则

上下文包由调度 agent 组装，执行 agent 只读不写。

上下文包包括：

1. 当前任务。
2. 相关 PRD 片段。
3. 相关接口合同。
4. 相关文件列表及摘要。
5. 上游任务结果摘要。
6. 已知风险和约束。
7. 验收标准。
8. 禁止修改范围。

上下文包不得包含：

1. 无关历史聊天。
2. 全量 PRD。
3. 全量研发报告。
4. 执行 agent 的自我辩护作为唯一验收依据。
5. 和当前任务无关的其他 agent 思考过程。

---

## 10. 独立验收规则

### 10.1 brainstorm

生成者：brainstorm agent。  
验收者：需求完整度 review agent。

验收者必须检查：

1. 是否明确目标用户。
2. 是否明确核心流程。
3. 是否明确角色和权限。
4. 是否明确必须功能和暂不做功能。
5. 是否明确数据对象。
6. 是否明确业务规则。
7. 是否明确异常状态。
8. 是否明确验收标准。
9. 是否列出未确认假设。
10. 是否能追溯用户原话。

### 10.2 PRD

生成者：PRD agent。  
验收者：PRD review agent。

验收者必须检查：

1. PRD 条目是否来自 brainstorm 事实或明确假设。
2. 是否把 AI 猜测误写成用户需求。
3. 是否有未确认需求进入开发范围。
4. 是否有第一版范围。
5. 是否有成功标准。

### 10.3 任务拆解

生成者：task decomposer。  
验收者：granularity review agent。

验收者必须检查：

1. 任务是否足够小。
2. 是否有明确修改范围。
3. 是否有禁止修改范围。
4. 是否有依赖关系。
5. 是否有验收标准。
6. 是否能在短任务中完成。

### 10.4 验收标准

生成者：调度 agent 或任务拆解 agent。  
验收者：acceptance criteria review agent。

验收标准不合格示例：

```text
功能正常可用。
页面显示正确。
接口能工作。
```

合格示例：

```text
点击保存按钮后，发送 POST /api/projects 请求；
成功后列表新增该项目；
失败时页面显示错误提示；
刷新页面后新增项目仍存在。
```

### 10.5 开发执行

生成者：执行 agent。  
验收者：review agent、test runner、Playwright verifier。

执行 agent 只能报告：

1. 修改了什么。
2. 创建了什么证据。
3. 测试结果是什么。
4. 有什么风险。

执行 agent 不能把任务状态改为 `accepted`。

### 10.6 最终报告

生成者：report agent。  
验收者：report review agent。

报告必须能追溯：

1. 已完成任务。
2. 证据文件。
3. 测试结果。
4. review 结论。
5. 阻塞项。
6. 风险和未完成事项。

---

## 11. 阻塞机制

以下情况必须进入阻塞流程：

1. 合同不一致。
2. 依赖缺失。
3. 需要用户判断。
4. 权限不足。
5. 环境缺失。
6. 多次重试失败。
7. 上下文污染风险无法排除。
8. `task_harness` 缺失或被违反。

阻塞项必须包含：

1. blocker_id。
2. blocked_task_id。
3. blocker_type。
4. description。
5. impact_scope。
6. is_global_blocker。
7. can_skip。
8. recommended_action。
9. options。
10. status。

---

## 12. 并发控制协议

MVP 可以顺序执行，但协议必须支持并发。

并发控制原则：

1. 文件级排他锁。
2. 同一文件同一时间只能被一个任务修改。
3. scope_allow 外的修改必须拦截。
4. 异常退出后必须清理锁并检查文件状态。
5. 集成前必须检查 diff 是否符合任务范围。

---

## 13. 防连锁错误机制

连锁错误是指上游任务方向错了，但验收通过了，下游任务基于错误前提继续执行。

必须设置四道防线：

1. 每个任务有 `assumptions` 和 `impact_if_wrong`。
2. 验收标准独立审查。
3. 上下游任务交叉验证。
4. 接口合同冻结后做早期烟雾测试。

这四道机制是 MVP 必须实现的防线。

---

## 14. 协议与文档的关系

结构化状态文件是给 AI 读的。PRD、决策记录、最终报告是给人类读的。

不要把结构化状态文件包装成花哨文档，也不要把正式文档当作 AI 协同的数据源。它们各司其职。

---

## 15. 工具适配协议

### 15.1 设计目标

`ToolAdapter` 协议的目标是让 Ralph Orchestrator 不依赖单一 CLI 工具，同时保持任务 harness、验收标准和权限控制的统一性。

核心原则：

```text
调度系统决定哪个工具执行哪个任务。
ToolAdapter 只负责把 Ralph 的通用执行请求翻译成工具原生调用。
所有工具返回的结果必须符合同一 schema，调度系统无感知底层差异。
```

### 15.2 Adapter 能力声明

每个 ToolAdapter 必须在注册时声明自身能力：

| 能力项 | 说明 |
|--------|------|
| `mcp_support` | 是否支持 MCP server 注入 |
| `session_resume` | 是否支持跨任务 session 复用 |
| `stream_output` | 是否支持实时流式输出 |
| `tool_use` | 是否支持原生 tool use / function calling |
| `sandbox_mode` | 是否支持受限沙箱执行 |
| `timeout_configurable` | 超时是否可按任务配置 |
| `credential_injection` | 是否支持密钥/环境变量注入 |

调度系统根据 `task_harness.tool_adapter` 或 `adapter_capabilities_required` 匹配最优适配器。

### 15.3 统一执行请求格式

Ralph 发给 ToolAdapter 的请求必须包含：

| 字段 | 说明 |
|------|------|
| `work_id` | 任务标识 |
| `context_pack` | 最小上下文包路径 |
| `task_goal` | 任务目标 |
| `scope_allow` | 允许修改范围 |
| `scope_deny` | 禁止修改范围 |
| `allowed_tools` | 允许调用的工具 |
| `denied_tools` | 禁止调用的工具 |
| `timeout_seconds` | 超时时间 |
| `mcp_servers` | 需要注入的 MCP server 列表 |
| `prior_session_id` | 前序 session ID（如支持 resume） |
| `env_vars` | 需要注入的环境变量 |

### 15.4 统一执行结果格式

ToolAdapter 返回的结果必须符合以下 schema：

| 字段 | 说明 |
|------|------|
| `work_id` | 对应任务 ID |
| `exit_code` | 进程退出码 |
| `status` | `completed` / `timeout` / `error` / `cancelled` |
| `files_created` | 新增文件列表 |
| `files_modified` | 修改文件列表 |
| `files_deleted` | 删除文件列表 |
| `stdout` | 标准输出（截断或摘要） |
| `stderr` | 标准错误（截断或摘要） |
| `evidence_files` | 证据文件路径列表 |
| `token_usage` | token 消耗统计（如工具提供） |
| `session_id` | 本次执行 session ID（供后续 resume） |
| `adapter_specific` | 适配器专有字段（作为扩展包，不破坏统一 schema） |

### 15.5 权限和安全不变性

无论底层工具是什么，以下规则不变：

1. 删除文件前必须备份到 `.ralph/backups/`。
2. 危险操作必须进入阻塞队列，不能由工具自行决定。
3. 越界修改必须拦截并转为 `blocked`。
4. 密钥和凭据不得写入工具原生配置文件，必须通过 `env_vars` 注入。
5. 工具的 session resume 只能作为性能优化，不能替代 `context_pack` 和结构化状态。

---

## 16. Issue 治理协议

### 16.1 Issue 生命周期

Issue 在 Ralph 中的生命周期：

```text
发现（拉取） → 去重 → 分类 → 策略匹配 → 决策 → 执行/阻塞/忽略 → 验收 → 归档
```

每个阶段都必须是可观察、可审计、可回滚的。

### 16.2 Issue 源适配协议

`IssueSource` 接口必须实现：

| 方法 | 说明 |
|------|------|
| `list_issues()` | 拉取 issue 列表 |
| `get_issue(issue_id)` | 获取单个 issue 详情 |
| `sync_status(issue_id, ralph_status)` | 将 Ralph 的处理状态回写（如 GitHub label、comment） |
| `validate_connection()` | 验证源连接是否可用 |

GitHub Issues 源必须支持：

1. OAuth / Personal Access Token 认证。
2. 按仓库、label、milestone、assignee 过滤。
3. webhook 或轮询触发增量拉取。
4. 处理状态回写（如添加 `ralph-processed` label）。

本地 Issue 源必须支持：

1. 从 `.ralph/issues/` 或项目目录中的 markdown/yaml 读取。
2. 文件变更时自动检测。
3. 不依赖外部网络。

### 16.3 分类协议

Issue 分类由 `IssueClassifier` 执行，采用规则引擎 + LLM 两阶段：

**阶段一：规则引擎**

1. 按标题/正文关键词匹配预定义规则。
2. 按 label / 文件路径 / 作者匹配。
3. 规则可覆盖，用户自定义规则优先于默认规则。

**阶段二：LLM 分类（规则未命中或置信度不足时）**

1. 输入 issue 标题、正文、评论、相关文件片段。
2. 输出分类标签、严重级别、置信度分数。
3. 置信度低于阈值时标记为 `needs_investigation`。

分类结果必须保存到结构化状态，包括：

- `classification_type`：规则分类 / LLM 分类 / 人工覆盖
- `confidence_score`：置信度（0-1）
- `classified_at`：分类时间
- `classifier_id`：分类器标识

### 16.4 策略匹配协议

`IssuePolicy` 定义分类到动作的映射：

| 字段 | 说明 |
|------|------|
| `policy_id` | 策略标识 |
| `match_rules` | 匹配条件（类型、严重级别、关键词、文件路径等） |
| `action` | `auto_fix` / `require_approval` / `ignore` / `needs_investigation` |
| `priority` | 优先级（数字越小越优先） |
| `expiry` | 策略过期时间（可选） |
| `created_by` | 创建者（system / user / agent） |

策略匹配规则：

1. 按优先级从高到低匹配，第一个命中的策略生效。
2. 没有匹配到任何策略时，默认进入 `require_approval`。
3. 用户可随时覆盖系统决策，覆盖记录保存到决策日志。

### 16.5 自动处理动作协议

#### `auto_fix`

1. 系统自动创建 work unit。
2. work unit 的 `task_harness` 必须包含 issue 上下文和复现步骤。
3. 必须经过标准的状态流转和独立验收，不能跳过 review。
4. 验收通过后，可选择自动关闭原 issue 或添加评论。

#### `require_approval`

1. 系统生成处理建议（包括拟创建的 work unit 列表和预估影响）。
2. 进入阻塞队列或待处理动作列表，等待用户确认。
3. 用户确认后转为正式 work unit；用户拒绝时记录原因并归档。

#### `ignore`

1. 标记为忽略，不创建 work unit。
2. 必须记录忽略原因（策略匹配结果或用户指定）。
3. 可配置忽略过期时间，过期后重新评估。
4. 被忽略的 issue 仍可在报告中查询。

#### `needs_investigation`

1. 创建侦察型 work unit，目标为“分析 issue 根因和影响范围”。
2. 侦察结果必须经独立 review。
3. review 后根据结论重新分类并匹配策略。

### 16.6 人机协作规则

1. 系统自动决策必须有证据（分类置信度、匹配的策略、影响评估）。
2. 用户覆盖系统决策时，系统必须记录用户理由并用于后续策略优化。
3. `auto_fix` 动作创建的任务和普通用户创建的任务在验收标准上完全一致。
4. Issue 治理的完整日志必须纳入最终报告。
5. 涉及安全或危险操作的 issue（如密钥泄露、SQL 注入）即使策略为 `auto_fix`，也必须额外进入安全 review 队列。
