# Dashboard V2 — 可信控制台 & 审批驱动架构

> **状态：** 已审查 v2 — 2026-04-18 封口版
> **日期：** 2026-04-18
> **作者：** 数字分身

---

## 目标

将 Dashboard 从"演示界面"升级为"可信控制台"，同时将 PM 从"自动执行器"改造为"审批驱动的 Team Leader"。实现单一状态源、命令闭环、事件可恢复、多实例并行（Phase 3+）、前后端契约统一。

---

## 核心架构

### 系统角色关系

```
甲方（用户）
    │
    ▼
┌─────────────┐
│  Dashboard   │  快照 REST + 命令 REST + 事件 WebSocket
│  (FastAPI)   │
└──────┬──────┘
       │ 命令提交
       ▼
┌──────────────────────────────────┐
│  Project Manager (Team Leader)    │
│  - 唯一决策者                      │
│  - 接收甲方指令                     │
│  - 审批/驳回子 Agent 产出           │
│  - 任务分配给 AgentPool            │
│  - 组织多实例协调                   │
└──────┬───────────────────────────┘
       │ 分配任务
       ▼
┌──────────────────────────────────┐
│  AgentPool                       │
│  - 多实例管理 (2-3 前端、2 后端等) │
│  - workspace 隔离                 │
│  - 接口契约管理 InterfaceRegistry │
└──────────────────────────────────┘
```

### 数据流（9 步闭环）

1. **甲方** 在 Dashboard 输入指令或提交项目需求
2. **Dashboard** 创建 Command → POST `/api/dashboard/commands`
3. **PM** 消费命令，产出 PRD + Feature 列表，创建 ApprovalRequest（artifact_type="prd"）
4. **甲方** 在 Dashboard 审批 ApprovalRequest → 状态 `pending → approved`
5. **PM** 通过 AgentPool 分配 Feature 给合适的 Agent 实例（Phase 3 起支持多实例）
6. **Agent** 执行任务 → 产出代码/文档 → 提交 IntegrationRecord（review branch）
7. **PM** 验收产出 → 创建 ApprovalRequest（artifact_type="code_output"）或自动通过（Phase 1 仅 PM 审批）
8. **集成流水线** review → merge candidate → 集成验证 → mainline commit
9. **事件推送** `feature_completed` 或 `feature_rejected` → Dashboard 实时更新

---

## 关键组件

### 1. Project Manager — 非阻塞审批驱动循环

替换当前的 `run_execution_loop()`（全自动执行），改为**事件驱动的非阻塞 tick 循环**。PM 不做长时间 await 阻塞，每个 tick 处理一批状态迁移后立即返回。

```python
class ProjectManager:
    async def run_loop(self) -> None:
        """非阻塞主循环，每个 tick 处理一类状态迁移。"""
        while True:
            await self._tick()
            await asyncio.sleep(0.5)

    async def _tick(self) -> None:
        # 1. 处理到期超时的审批
        for appr in self.repo.get_expired_approvals():
            self._expire_approval(appr)

        # 2. 处理已审批的决策（approved/rejected）
        for appr in self.repo.get_decided_approvals():
            if appr.status == "approved":
                await self._apply_approval(appr)
            else:
                await self._reject_and_feedback(appr)

        # 3. 分配空闲 Feature 给空闲 Agent
        for agent in self.agent_pool.idle_agents():
            feature = self.feature_queue.pop_available(agent.role)
            if feature:
                self.agent_pool.assign(agent, feature)

        # 4. 收集运行中 Agent 的产出，创建审批或自动验收
        for agent in self.agent_pool.active_agents():
            if agent.has_output():
                await self._review_and_route(agent)

        # 5. 处理集成流水线状态迁移
        for record in self.integration_queue.pending():
            await self._advance_integration(record)
```

**与现有代码的差异：**
- 现有 `core/project_manager.py:run_execution_loop()` 是线性的：分配 → 执行 → 验证 → commit，无外部审批
- 新版改为非阻塞 tick 循环，PM 只做状态迁移，不做长时间 await 阻塞
- 每个 tick 最多 0.5s，保证控制台实时响应暂停/取消/重试等控制指令

### 审批矩阵

| 审批节点 | artifact_type | 审批人 | 超时处理 | Phase |
|----------|--------------|--------|----------|-------|
| PRD 审批 | "prd" | 甲方 | 不超时，必须甲方拍板 | Phase 1 |
| Feature 拆分审批 | "feature_spec" | 甲方 | 不超时 | Phase 1 |
| 代码验收 | "code_output" | PM（Phase 1-2）/ 甲方（Phase 4+） | PM 超时 30min 自动标记需人工 review | Phase 1 |
| 集成合并 | "integration" | PM（自动） | 自动运行集成测试，失败回滚 | Phase 3 |

### 2. AgentPool — 多实例管理（Phase 3+）

> Phase 1-2 仅单实例，AgentPool 作为接口预留。Phase 3 起启用多实例。

支持同一角色多个实例并行工作，每个实例有独立 workspace 和 branch。

```python
class AgentPool:
    def __init__(self, base_workspace: Path) -> None:
        self._base = base_workspace
        self._instances: dict[str, list[BaseAgent]] = defaultdict(list)
        self._assignments: dict[str, str] = {}  # agent_id -> feature_id

    def get_or_create(self, role: str, workspace_id: str) -> BaseAgent:
        for agent in self._instances[role]:
            if agent.workspace_id == workspace_id:
                return agent
        agent = create_agent(role, instance_number=len(self._instances[role]) + 1)
        agent.workspace_id = workspace_id
        agent.workspace_path = str(self._base / f"{role}_{workspace_id}")
        self._instances[role].append(agent)
        return agent

    def assign(self, agent: BaseAgent, feature: Feature) -> None:
        self._assignments[agent.id] = feature.id
        agent.start(feature)

    def idle_agents(self) -> list[BaseAgent]:
        return [a for agents in self._instances.values() for a in agents if a.is_idle]

    def active_agents(self) -> list[BaseAgent]:
        return [a for agents in self._instances.values() for a in agents if a.is_running]
```

### 2.1 集成流水线 — workspace 回主线协议

多实例最关键的环节：workspace 隔离只解决"同时写不冲突"，不解决"安全并回主线"。
每条 Feature 的工作产出必须经过以下集成流水线：

```
workspace (独立 branch: feature/{feature_id})
    ↓ Agent 完成，push 到 review branch
review branch (review/{feature_id})
    ↓ PM 验收（ApprovalRequest: artifact_type="code_output"）
merge candidate branch (integration/{feature_id})
    ↓ 集成验证（接口兼容性 + 冒烟测试）
validated
    ↓ 合并到 main
mainline commit
    ↓ 失败（冲突/测试不通过）
conflict → 回滚到 workspace，标记冲突归属 → Agent 修复
```

```python
@dataclass
class IntegrationRecord:
    integration_id: str
    workspace_id: str
    feature_id: str
    agent_id: str
    review_branch: str             # "review/F001"
    merge_candidate_branch: str     # "integration/F001"
    status: str                     # "reviewing" | "integrating" | "validated" | "merged" | "conflict" | "rolled_back"
    conflict_details: list[str] = field(default_factory=list)
    validated_at: str | None = None
    created_at: str = ""
```

**冲突归属规则：**
- 如果是 Agent 产出的代码与 main 冲突 → 标记 `conflict`，回滚给原 Agent 修复
- 如果是两个 Agent 并行产出的互相冲突 → PM 决定合并顺序，后合并的 Agent 修复
- 连续 3 次冲突 → 自动暂停该 Feature，通知甲方人工介入

**`merged` 终态语义：**
- `validated` → `merged`：集成验证通过，已合并到 main，为终态
- `pending()` 仅返回 `status IN ("reviewing", "integrating")` 的记录，不包含 `validated`/`merged`/`conflict`/`rolled_back`
- `_advance_integration(record)` 为幂等操作：对同一 record 调用多次，状态仅推进一次，不会重复合并
- `conflict` 状态 record 在 Agent 修复后重新提交时，新建 IntegrationRecord，原 record 保留为历史审计

### 3. InterfaceRegistry — 接口登记簿（Phase 3+）

> **定位降级：** InterfaceRegistry 只做接口登记和依赖关系记录，供 PM 分配任务时参考。不做运行时 schema diff，不做版本兼容性校验，不做 breaking change 检测——那些是 CI/CD 集成验证的职责。

```python
@dataclass
class InterfaceSpec:
    module_name: str
    api_endpoints: list[dict]  # {path, method, request_schema, response_schema}
    dependencies: list[str]     # 依赖的其他模块
    version: str = "1.0.0"

class InterfaceRegistry:
    """接口登记簿：注册模块接口定义和依赖关系。"""

    def __init__(self) -> None:
        self._specs: dict[str, InterfaceSpec] = {}

    def register(self, module_name: str, api_spec: dict) -> None:
        """登记一个模块的接口定义。"""
        self._specs[module_name] = InterfaceSpec(**api_spec)

    def get_dependencies(self, module_name: str) -> list[str]:
        """获取模块声明的依赖列表。"""
        spec = self._specs.get(module_name)
        return spec.dependencies if spec else []

    def get_module_interface(self, module_name: str) -> InterfaceSpec | None:
        """获取模块接口定义。"""
        return self._specs.get(module_name)

    def list_all(self) -> dict[str, InterfaceSpec]:
        return dict(self._specs)
```

**PM 使用场景：** 分配 Feature 给前端 Agent A（用户页面）和前端 Agent B（订单页面）时，PM 查询 InterfaceRegistry 确认两者是否有共同的依赖模块（如共享的 API 网关），如果有则在分配时声明接口边界，避免两个 Agent 修改同一组 API。

### 4. Command 生命周期

```
pending → accepted → applied
        → accepted → failed       (运行时错误)
        → rejected                (业务驳回)
        → cancelled               (主动取消)
```

- `pending`: 命令已创建，等待 PM 处理
- `accepted`: PM 已接收，开始执行
- `applied`: 执行完成，产出已提交
- `failed`: 运行时错误（依赖缺失、超时、目标不存在、代码执行异常）
- `rejected`: 业务驳回（甲方不同意方案、PM 驳回代码产出）
- `cancelled`: 被甲方主动取消

**rejected ≠ failed：**
- `rejected` = "方案/代码不行，重做"，附带反馈原因，Agent 根据原因修改后重新提交
- `failed` = "执行出错了"，属于基础设施问题，通常需要系统修复或环境调整

### 5. ApprovalRequest — 独立审批对象

Command 是"意图"，ApprovalRequest 是"审批实例"。一个 Command 可能触发多轮审批（PRD v1 驳回 → PRD v2 再审），所以必须拆开。

```python
@dataclass
class ApprovalRequest:
    approval_id: str           # "appr_20260418_001"
    command_id: str            # 关联的命令 ID
    project_id: str
    run_id: str
    artifact_type: str         # "prd" | "feature_spec" | "code_output" | "design" | "integration"
    artifact_ref: str          # 产物路径或 ID，如 "docs/prd_v1.md"
    artifact_version: int      # 版本号，驳回后 +1
    status: str                # "pending" | "approved" | "rejected" | "applied" | "expired"
    reviewer: str              # "user" | "pm"
    created_at: str
    expires_at: str | None     # 超时自动过期（PM 审批有超时，甲方审批不超时）
    feedback: str = ""         # 驳回原因
```

**持久化：** ApprovalRequest 存储在 `ProjectStateRepository` 中，服务重启后不丢。`get_decided_approvals()` 返回当前待审批列表，是 Repository 的持久化视图，不是内存队列。

**`applied` 终态语义与原子领取：**

```
pending → approved → applied（已消费）
pending → rejected（驳回，无需 applied）
pending → expired（超时，无需 applied）
```

- `approved` = 甲方/PM 已拍板同意，但尚未被 PM tick 循环消费
- `applied` = PM tick 循环已读取并执行了对应决策，**不允许二次消费**
- `get_decided_approvals()` **仅返回 `status="approved"` 的审批**，不返回 `applied`，避免 tick 重启后重复处理
- `_apply_approval(appr)` 使用 Repository 内部锁做原子 CAS：`UPDATE status SET applied WHERE status=approved AND approval_id=xxx`，确保多 tick 并发场景下只有一个 tick 能领取
- 服务宕机重启后，所有 `approved` 状态的审批会被新实例的 tick 循环重新消费，`applied` 状态的审批不重复处理

**与 Command 的关系：**
```
Command (意图)  1:N  ApprovalRequest (审批实例)
```

### Command 聚合状态规则

一个 Command 可能触发多轮审批（PRD v1 驳回 → PRD v2 再审），因此 Command 状态由其所关联的 ApprovalRequest 集合聚合决定：

| Command 状态 | 触发条件 | 说明 |
|-------------|---------|------|
| `pending` | Command 刚创建，尚未生成任何 ApprovalRequest | 等待 PM 产出首批审批 |
| `accepted` | PM 已开始处理，至少有一个 ApprovalRequest 处于 `pending` | Command 执行中 |
| `applied` | 所有关联的 ApprovalRequest 均已达到终态（`applied` 或 `rejected`），且至少有一个 `applied` | Command 整体成功 |
| `rejected` | 所有关联的 ApprovalRequest 均被 `rejected`，且无 `applied` | Command 整体被驳回 |
| `failed` | PM 处理过程中发生运行时错误（依赖缺失、超时、目标不存在） | 基础设施/运行时错误 |
| `cancelled` | 甲方主动取消 | 主动取消 |

**聚合逻辑示例：**
- Command `cmd_001`（需求：构建电商系统）→ PM 产出 PRD → 创建 ApprovalRequest `appr_001`（PRD）
- 甲方驳回 `appr_001` → PM 修改 PRD → 创建 `appr_002`（PRD v2）
- 甲方批准 `appr_002` → PM 消费 → 创建 `appr_003`~`appr_007`（Feature specs）
- 甲方逐个审批 → 每个 `approved` 的 ApprovalRequest 被 PM 消费后变为 `applied`
- 当 `appr_002`~`appr_007` 全部达到终态且至少有一个 `applied` → Command `cmd_001` 状态变为 `applied`

**查询接口：** `GET /api/dashboard/commands/{command_id}` 返回 Command 及其所有关联 ApprovalRequest 的当前状态，前端据此渲染完整审批链路。

### 6. EventBus 带 event_id 递增 + 恢复协议

每个事件有单调递增的 `event_id` 和 `schema_version`，支持断线补发和全量重同步。

```python
@dataclass
class Event:
    schema_version: int = 1    # 事件 schema 版本，不兼容时递增
    event_id: int              # 单调递增
    project_id: str
    run_id: str
    type: str                  # "agent_status_changed", "feature_completed", etc.
    timestamp: str
    caused_by_command_id: str | None
    payload: dict
```

**事件恢复协议：**

```python
@dataclass
class EventRecovery:
    """客户端断线后的事件恢复策略。"""
    client_last_event_id: int
    server_last_event_id: int
    gap: int = 0

    def __post_init__(self) -> None:
        self.gap = self.server_last_event_id - self.client_last_event_id

    def needs_resync(self) -> bool:
        return self.gap > 500  # 超过 500 个事件直接全量重同步

    def recovery_strategy(self) -> str:
        if self.gap < 0:
            return "resync_required"  # 客户端 event_id 比服务端新，说明服务端重启了
        elif self.needs_resync():
            return "full_snapshot"
        elif self.gap > 0:
            return "incremental_catchup"
        else:
            return "up_to_date"
```

**处理规则：**
- 客户端连接时发送 `after_event_id`，服务端从 Repository 查增量事件补发
- `gap < 0`（客户端比服务端新）：服务端重启过，强制要求客户端全量重同步
- `0 < gap <= 500`：增量补发
- `gap > 500`：增量太多，直接返回最新快照
- 事件 schema 版本不兼容时：`schema_version` 不匹配，强制 `resync_required`
- 服务重启后：从持久化 events 重建 `last_event_id`，不丢失事件序列

---

## Dashboard V2 API 契约

### 三层能力

| 能力 | 协议 | 路径 | 用途 |
|------|------|------|------|
| 快照 | REST GET | `/api/dashboard/state` | 加载时获取完整状态 |
| 命令 | REST POST | `/api/dashboard/commands` | 提交审批/决策 |
| 事件 | WebSocket | `/ws/dashboard` | 实时推送增量事件 |

### REST 端点

#### 幂等约束

所有 POST 端点支持幂等重试，防止网络重发和 WebSocket 断线重连导致的重复提交：

| 端点 | 幂等策略 | 说明 |
|------|---------|------|
| `POST /api/dashboard/commands` | `idempotency_key` | 客户端生成 UUID，重复提交返回已有 Command |
| `POST /api/dashboard/approvals/{approval_id}/decision` | `version` 前置条件 | 请求携带 `ApprovalRequest.version`，仅当版本匹配时接受 |

**命令幂等键：**
```python
# 客户端
cmd = {"type": "approve_decision", "idempotency_key": "uuid-v4-abc123", ...}
resp1 = POST("/api/dashboard/commands", cmd)  # 202, command_id="cmd_001"
resp2 = POST("/api/dashboard/commands", cmd)  # 202, command_id="cmd_001" (重复，返回相同结果)
```

**审批版本前置条件：**
```python
# 客户端提交审批决策时携带当前已知版本
resp = POST("/api/dashboard/approvals/appr_001/decision", {
    "decision": "approved",
    "version": 1  # 如果服务端当前版本已变化(如已被处理)，返回 409 Conflict
})
```

**重复提交返回规则：**
- 命令已存在：返回 `202` + 已有 `command_id` + `was_duplicate: true`
- 审批版本不匹配：返回 `409 Conflict` + 当前最新版本 + 建议重新拉取审批状态

#### 快照与命令

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/state?project_id=&run_id=` | 完整状态快照 |
| GET | `/api/dashboard/commands/{command_id}` | 查询命令状态 |
| POST | `/api/dashboard/commands` | 创建命令（审批/决策/暂停等） |

#### 审批

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/approvals?status=pending` | 待审批列表 |
| GET | `/api/dashboard/approvals/{approval_id}` | 审批详情 |
| POST | `/api/dashboard/approvals/{approval_id}/decision` | 提交审批决策（approve/reject） |

#### 事件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/events?after_event_id=0&limit=200` | 增量事件补发 |

### WebSocket 协议

```
客户端连接 → 服务端发送 hello {last_event_id}
客户端可发送 after_event_id 请求补发
服务端持续推送增量事件
```

---

## 现有代码变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `core/project_manager.py` | **重写** | `run_execution_loop()` → `run_loop()` + `_tick()` 非阻塞循环 |
| `core/agent_pool.py` | **新建** | AgentPool 多实例管理（Phase 3+ 启用） |
| `core/interface_registry.py` | **新建** | InterfaceRegistry 接口登记簿 |
| `core/integration_pipeline.py` | **新建** | IntegrationRecord 状态机 + 分支集成流水线 |
| `dashboard/models.py` | **修改** | 新增 Command、Event、Snapshot、ApprovalRequest 模型 |
| `dashboard/event_bus.py` | **修改** | 添加 event_id 递增 + schema_version |
| `dashboard/state_repository.py` | **新建** | ProjectStateRepository 统一读写 + 审批持久化 |
| `dashboard/command_processor.py` | **新建** | CommandProcessor 命令状态机 |
| `dashboard/api/routes.py` | **重写** | REST 快照/命令/审批 + WebSocket 事件推送 |
| `dashboard/api/schemas.py` | **新建** | Pydantic/TypedDict 契约定义 |
| `agents/__init__.py` | **修改** | 支持多实例创建 |
| `tests/test_dashboard_api.py` | **重写** | 匹配新 API 契约 |
| `tests/test_state_repository.py` | **新建** | Repository 读写 + 审批持久化测试 |
| `tests/test_command_processor.py` | **新建** | 命令状态机测试 |
| `tests/test_event_sequencing.py` | **新建** | event_id 单调递增 + 恢复协议测试 |
| `tests/test_integration_pipeline.py` | **新建** | 集成流水线和冲突处理测试 |

---

## 实施阶段

### Phase 0: 状态模型收敛
统一 AgentInstance、Feature、Command、Event、Snapshot、ApprovalRequest、IntegrationRecord 数据模型。

### Phase 1: 后端审批核心
- ProjectStateRepository 读写 + 审批持久化 + Command 聚合视图
- CommandProcessor 状态机（含 failed 状态）+ Command 聚合逻辑
- EventBus event_id 递增 + EventRecovery 协议
- 替换 PM 的 `run_execution_loop()` 为非阻塞 `run_loop()` + `_tick()`
- ApprovalRequest 独立审批对象 CRUD + `applied` 终态 + 原子 CAS 领取
- 控制面 API 幂等约束：`idempotency_key` + `version` 前置条件

### Phase 2: Dashboard API 重写
- REST 快照/命令/审批接口
- WebSocket hello + 增量同步 + 断线恢复
- 旧接口兼容层

### Phase 3: AgentPool 多实例
- AgentPool 实现
- workspace 隔离
- 接口登记簿
- 集成流水线（IntegrationPipeline + 分支管理）

### Phase 4: UI 接真实状态
- 前端快照加载
- 命令提交按钮
- 审批决策面板
- 实时事件流

### Phase 5: 集成测试
- 端到端场景：创建命令 → 审批 → 分配 → 执行 → 验收 → 集成
- WebSocket 断线重连不丢事件
- 多实例并行不冲突
- 冲突归属和自动回滚

---

## 风险和注意事项

- PM 主链路当前是自动执行的，改造为审批驱动需要重构核心循环为非阻塞 tick 模式
- ApprovalRequest 是独立持久化对象，必须在 Repository 层面保证不丢失；`applied` 终态 + 原子 CAS 领取确保 tick 重启/服务恢复后不重复消费
- Command 1:N ApprovalRequest 的聚合状态需要在 Repository 层面维护聚合视图，避免前端多次查询不一致
- 多实例模式下 workspace 隔离策略需要仔细设计，避免文件冲突
- 集成流水线（workspace → review → merge candidate → validated → merged）是 Phase 3 的关键路径，分支冲突处理需要明确的归属规则
- `_advance_integration()` 必须幂等，`pending()` 仅返回非终态记录
- InterfaceRegistry 仅做契约注册和依赖关系记录，不做运行时 schema diff 或兼容性校验
- 旧 features.json / agents.json 格式需要向后兼容迁移
- Phase 1-2 仅单实例 + PM 审批代码验收，Phase 3 起启用多实例 + 集成流水线，Phase 4 起甲方审批代码验收
- 前端部分（Phase 4）暂不涉及，先打通后端审批闭环
- 控制面 API 的幂等约束是 Phase 1 就需实现的基础能力，否则 WebSocket 断线重连场景下可能导致重复审批
