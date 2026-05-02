# TODO — 待办工作清单

> 最后更新：2026-04-24
> 状态标记：✅ 已完成 / 🔄 进行中 / ⏳ 待开始 / ❌ 阻塞

---

## 已完成 ✅

### 1. 修复 `--allowedTools` 无效参数
- **状态**：✅ 已完成
- **说明**：修复 Claude CLI 调用时 `--allowedTools` 参数传递问题

### 2. 修复 workspace 验证不匹配
- **状态**：✅ 已完成（2026-04-24）
- **说明**：AgentPool 创建隔离 workspace 后，FeatureVerificationService 在错误目录验证文件存在性
- **核心修复**：
  - `FeatureExecutionService.execute()` 不再用 `getattr(agent, "workspace_path", "")` 推导 workspace（MagicMock 会返回 Mock 而非空字符串）
  - 改为接收显式 `workspace_dir` 参数，由 `_execute_feature` 从 `instance.workspace_path` 传入
  - `agents/pool.py` AgentPool.acquire() 返回 `(instance, agent)` 对，instance 持有 workspace_path
  - 验证在 workspace 中检查文件，通过后 merge 到 project_dir，再 git commit
- **测试结果**：265 tests, all green

### 3. 拆分 FeatureExecutionService
- **状态**：✅ 已完成
- **说明**：从 ProjectManager 拆分执行逻辑到独立服务类
- **提交**：138eb8e, d7cb317, 6ada5a8

### 4. Dashboard 修复系列
- **状态**：✅ 已完成
- **修复项**：
  - CommandProcessor on_event 回调签名不匹配
  - Consumer 命令别名支持
  - CMD_TYPE_MAP 映射 pause/resume/retry/skip
  - PM 消息路由到日志而非聊天窗口
  - Agent 管理 REST 端点

---

## 待办事项 ⏳

### 高优先级

#### T-001: 添加进程流式输出
- **状态**：⏳ 待开始
- **说明**：Agent 执行时实时显示子进程输出到终端/dashboard
- **当前问题**：Agent 通过 Claude CLI 子进程执行，输出被捕获但无实时流式反馈
- **涉及**：`agents/pool.py`, `dashboard/coordinator.py`, CLI 输出
- **价值**：用户不再面对"黑屏等待"，能看到实时进度

#### T-002: 补 AgentPool 测试
- **状态**：⏳ 待开始
- **说明**：`agents/pool.py` 有测试文件 `tests/test_agent_pool.py`，但覆盖度不足
- **缺失场景**：
  - workspace 创建/清理生命周期
  - acquire/release 并发安全
  - 实例健康检查
  - 异常恢复
- **涉及**：`tests/test_agent_pool.py`

#### T-003: 清理旧 AgentPool
- **状态**：⏳ 待开始
- **说明**：可能存在新旧两套 AgentPool 实现，需要统一到 runtime pool 或新架构
- **涉及**：`agents/pool.py`, `agents/base_agent.py`
- **依赖**：T-002 完成后安全清理

### 中优先级

#### T-004: 提交未跟踪文件
- **状态**：⏳ 待开始
- **说明**：大量 `??` 未跟踪文件需要决定归属
- **待分类文件**：
  - **应提交**：`cli.py`, `core/*.py`, `agents/*.py`, `dashboard/*.py`, `tests/*.py`, `docs/`, `prompts/`, `uv.lock`
  - **应忽略**：`.DS_Store`, `.coverage`, `MagicMock/`, `data/`, `.claude/`
  - **待定**：`auto-coding-agent-demo/`, `multica/`, `project/`, `design/`, `testing/`
- **行动**：完善 `.gitignore`，提交应有文件

#### T-005: 落档核心文档
- **状态**：⏳ 待开始（部分完成）
- **已完成**：`README.md`, `AGENTS.md`, `ARCHITECTURE.md`, `WORKFLOW.md`, `CLAUDE.md`
- **待补充**：
  - API 文档（Dashboard REST 端点）
  - Agent prompt 模板文档
  - 部署指南
  - 开发上手指南（CONTRIBUTING.md）

#### T-006: Dashboard 集成测试修复
- **状态**：⏳ 待开始
- **说明**：`tests/test_dashboard_api.py` 和 `tests/test_dashboard_integration.py` 已修改但未验证是否全部通过
- **涉及**：Dashboard API routes, consumer, event bus

### 低优先级

#### T-007: 完善 BlockingIssue 闭环
- **状态**：⏳ 待开始
- **说明**：BlockingIssue 已有一等公民支持，但自动创建和人类介入闭环不完整
- **涉及**：`core/blocking_tracker.py`, `dashboard/coordinator.py`

#### T-008: ExecutionLedger 集成
- **状态**：⏳ 待开始
- **说明**：`core/execution_ledger.py` 已创建但未完全集成到执行流程
- **涉及**：`core/execution_ledger.py`, `core/project_manager.py`

#### T-009: ProgressLogger 集成
- **状态**：⏳ 待开始
- **说明**：`core/progress_logger.py` 已创建但未使用
- **涉及**：`core/progress_logger.py`

---

## 技术债

### 已知问题

1. **MagicMock 目录残留**：根目录有 `MagicMock/` 文件夹，需清理
2. **Dashboard UI submodule**：`dashboard-ui` 标记为 modified，需确认是否需要同步
3. **测试覆盖率分布不均**：core/ 覆盖较好，agents/ 和 dashboard/ 部分模块缺测试
4. **无 `.gitignore`**：大量不应提交的文件未被忽略

### 架构风险

1. **状态双写**：`features.json` 和 `StateRepository` 同时存在，有同步风险（已标注为审计副本，但需确保只写一处）
2. **Agent 健康检测缺失**：AgentPool 无实例心跳机制，长时间运行可能无法发现僵尸实例
3. **并发安全未验证**：多 Agent 并行 acquire/release 的竞态条件未做压力测试

---

## 下次启动清单

运行项目前确认：
- [ ] `uv sync` 依赖最新
- [ ] `.gitignore` 已配置
- [ ] `pytest tests/` 全绿（当前 265 passed）
- [ ] 环境变量 `ANTHROPIC_API_KEY` 已设置（如需要实际执行）
