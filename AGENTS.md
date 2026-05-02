# Auto-Coding 架构契约

> 本文档定义系统的架构约束和组件职责。所有代码变更必须符合此契约。
> 变更此文档需要团队评审。

## 系统概述

Auto-Coding 是一个多 Agent 自动化代码生成平台，通过协调多个 Claude Code 实例完成项目功能开发。

## 组件职责

### ProjectManager
- 初始化项目结构
- 生成 PRD 和功能列表（调用 Claude CLI）
- 协调执行循环
- 聊天响应
- **不直接管理**：状态存储（委托 StateRepository）、特性执行（委托 FeatureExecutionService）、验收（委托 FeatureVerificationService）、Git 操作（委托 GitService）

### FeatureExecutionService
- 接收 Feature 和 Agent 实例
- 构建执行上下文（PRD 摘要、依赖上下文）
- 调用 Agent.execute()
- 返回执行结果（success/error）

### FeatureVerificationService
- 检查 Feature 涉及的文件是否存在
- 运行语法检查
- 运行 E2E 测试
- 返回验证结果（pass/fail + 错误详情）

### GitService
- 初始化 git 仓库
- 提交变更
- 创建分支
- 合并分支

### ProjectStateRepository
- 唯一的状态写入点
- 线程安全
- 原子写入（tmpfile + rename）
- 支持 agents/features/commands/events/chat/module_assignments/blocking_issues

### PMCoordinator
- 在每步执行之间插入审批闸门
- 处理用户审批/驳回命令
- 同步状态到 Repository
- 静默检测和 Agent 进程管理

## 状态归属表

| 数据类型 | 唯一来源 | 写入者 | 读取者 |
|---------|---------|--------|--------|
| Feature 列表 | StateRepository | ProjectManager / Coordinator | Dashboard, Coordinator, CLI |
| Agent 实例 | StateRepository | Coordinator | Dashboard |
| 任务队列 | SQLite `tasks.db` | TaskQueue | AgentPool |
| 命令 | StateRepository | REST API | Coordinator |
| 事件 | StateRepository | ProjectManager / Coordinator / API | Dashboard (WebSocket) |
| 阻塞问题 | StateRepository | Coordinator/Services | Dashboard, CLI |
| 执行台账 | `execution-plan.json` | ExecutionLedger | Dashboard, CLI |

## 数据流

```
用户发起项目 → CLI → ProjectManager.initialize_project()
                        ↓
                   生成 features.json（审计副本）
                        ↓
              PMCoordinator.run_coordinated_loop()
                        ↓
              FeatureExecutionService.execute()
                        ↓
              Agent.execute(context)
                        ↓
              结果写入 StateRepository
                        ↓
              等待审批 → 用户审批 → FeatureVerificationService.verify()
                        ↓
              GitService.commit() → 下一个 Feature
```

## 约束

1. 所有运行时业务状态写入必须通过 StateRepository；`features.json` 仅保留为审计副本
2. 服务之间通过接口通信，不直接依赖实现
3. 阻塞问题必须作为一等公民记录，不能仅用 error_log 字符串
4. 每个 Feature 状态变更必须伴随一个 Event 记录


<claude-mem-context>
# Memory Context

# [auto-coding] recent context, 2026-05-01 4:39pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (14,270t read) | 4,236,328t work | 100% savings

### Apr 30, 2026
S105 Ralph Orchestrator Phase 3 收尾 — WorkUnitEngine 测试修复与全量回归验证 (Apr 30 at 9:37 PM)
S104 创建 Ralph Orchestrator 重构执行计划 — 将 jiaojie.txt 方案融入 auto-coding 产品开发流程 (Apr 30 at 9:37 PM)
S106 Comprehensive architectural review of DASHBOARD_ARCHITECTURE.md with 7 specific fixes for Ralph Runtime Console scope, AI/human approval separation, Command semantics, WebSocket cursor, P0 minimal status, and TypeScript type alignment (Apr 30 at 10:36 PM)
### May 1, 2026
182 12:17p ✅ P0 Scope Simplified with RunStatusHeader Minimal Overview Component
183 12:18p 🟣 Ralph Runtime Console frontend development plan created
S108 完成 Ralph Runtime Console 前端开发计划，包含13个任务（A-M），等待用户选择子代理驱动或内联执行方式 (May 1 at 12:18 PM)
S109 Ralph Runtime Console 前端完整实现与测试 (May 1 at 12:58 PM)
S107 Ralph Runtime Console 前端开发计划已制定完成，用户选择子代理驱动开发模式，要求建立标准体系后开始编码 (May 1 at 12:58 PM)
184 1:07p ⚖️ Frontend Design Standards Established
186 1:16p ✅ Added debug output to path traversal test
191 1:17p ✅ Ruff applied auto-fixes to dashboard Python files
192 " 🔴 Recurring UnboundLocalError in dashboard routes fixed again
185 1:18p 🔄 Removed redundant inline Path import in dashboard routes
187 1:21p 🔵 Starlette normalizes raw path traversal but not %2E-encoded dots
188 " 🔴 Fixed UnboundLocalError from inline Path import in dashboard routes
189 " ✅ Updated path traversal test to use %2E encoding
190 " ✅ Installed ruff linter/formatter
193 1:24p ⚖️ Frontend Design Standards Decision: Sharp Angular Aesthetic
194 2:40p 🟣 Ralph Utils Test Suite Created with 24 Passing Tests
195 " 🔴 Test Edge Cases Fixed for Unicode Truncation and Relative Date Formatting
196 " ⚖️ Frontend Development Standards Established
197 2:50p ⚖️ Frontend Development Standards Established
198 2:55p ⚖️ Frontend development standards established
199 3:04p 🔴 Ralph Store test suite fixed and passing
200 " 🔄 WebSocket test inlined to avoid vitest mocking issues
201 " 🔵 TypeScript compilation errors in multiple dashboard UI test files
202 3:07p 🔴 WebSocket tests fixed with class-based mock pattern
203 " 🔵 Task E Zustand Store completed with confirmed API signatures
204 " 🟣 WebSocket test suite expanded with reconnection and deduplication coverage
205 3:08p 🟣 Full ralph test suite passes with 123 tests across 5 files
207 " 🔵 RALPH_FRONTEND_STANDARDS.md exists in project root
208 " 🟣 Ralph frontend standards document fully defined (426 lines)
209 " 🟣 Core Ralph library stack fully implemented
210 " ✅ Ralph UI component and route directories created
206 3:09p 🟣 Task D WebSocket client completed by typescript-pro subagent
211 3:12p ⚖️ RALPH frontend standards established with strict border-radius constraint
212 " 🟣 Ralph dashboard UI components shipped: WorkUnit detail, ApprovalCenter, EvidenceViewer
213 " 🔄 Test suite hardened for React Testing Library robustness
S111 Ralph Runtime Console 前端完整实现 - 13 个任务详细验收 (May 1 at 3:26 PM)
214 3:43p 🟣 Ralph Runtime Console 前端完整实现与测试覆盖
218 3:44p 🔵 Ralph Runtime Console 集成验证发现前后端契约严重错位
S110 Ralph Runtime Console 前端完整实现与测试验收 (May 1 at 4:05 PM)
216 4:10p 🟣 Ralph Runtime Console frontend fully implemented
217 4:13p 🔵 Frontend-backend API contract mismatches found in Ralph Console
219 4:22p 🔵 Frontend-backend Ralph API contracts severely misaligned
220 " 🔵 CommandConsumer does not recognize Ralph-specific command types
221 " 🔵 Tab system is UI-only with no routing or content mapping
222 " 🔵 WebSocket client disconnected from backend and unused in pages
223 " 🔵 EvidenceViewer built but not integrated into WorkUnitDetail
224 " 🔵 TypeScript and Python schema definitions diverged for Evidence and Blocker
225 " 🔵 Quality gates failing: lint, TypeScript, and backend python3 compatibility
226 4:25p ✅ Ralph API contract aligned between frontend and backend
227 " ✅ Frontend Ralph tabs and navigation now drive real routing
228 " 🟣 EvidenceViewer integrated into WorkUnit detail page
229 " 🔴 CommandConsumer Ralph handler auto-initialization fixed
230 " 🔴 Frontend quality gate failures resolved
231 " 🔴 Blocker schema field mismatch discovered in RalphCommandHandler
232 4:32p 🔴 RalphCommandHandler fixed for frozen Blocker dataclass

Access 4236k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>