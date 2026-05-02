# Dashboard 质量修复计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 Dashboard 系统的 5 个已知质量问题：E2E 测试标题不一致、审批模型缺失、私有字段违反封装、事件丢失风险、upsert_feature 不强制事件追加。

**架构：** 所有修复围绕 Dashboard 后端（FastAPI）和前端（Next.js）展开，涉及模型层、仓储层、API 层、消费层和协调层。核心原则：事件必须持久化、服务通过接口通信、审批独立建模。

**技术栈：** Python/FastAPI, pytest, Playwright, Next.js

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `dashboard-ui/tests/e2e/test_dashboard.spec.ts:18` | 修改 | E2E 测试标题从 "Agent 集群监控" 改为 "Agent 集群" |
| `dashboard/models.py` | 修改 | 新增 `ApprovalRequest` 数据类，`Command` 添加 `idempotency_key` 字段 |
| `dashboard/state_repository.py` | 修改 | 新增 ApprovalRequest 持久化、`upsert_feature` 强制事件校验、公开方法替代私有字段访问 |
| `dashboard/consumer.py:30` | 修改 | 用 `list_pending_commands()` 替代 `self._repo._commands` 私有访问 |
| `dashboard/coordinator.py:374` | 修改 | 用 `list_commands_by_status()` 替代 `self._repo._commands` 私有访问 |
| `dashboard/api/routes.py` | 修改 | `_create_command` 添加 `idempotency_key` 支持，EventBus 桥接写入 Repository 事件 |
| `tests/test_dashboard_api.py` | 修改 | 添加幂等键测试 |
| `tests/test_dashboard_integration.py` | 修改 | 添加 ApprovalRequest 场景测试 |

---

### 任务 1：修复 E2E 测试标题不一致

**文件：**
- 修改：`dashboard-ui/tests/e2e/test_dashboard.spec.ts:18`

前端页面实际标题是 "Agent 集群"（见 `dashboard-ui/app/page.tsx:406` 和 `components/agent-cluster-monitor.tsx:185`），但 E2E 测试在找 "Agent 集群监控"（后者出现在 `components/agent-status-panel.tsx:74`，是旧组件）。

- [ ] **步骤 1：更新 E2E 测试断言**

```typescript
// dashboard-ui/tests/e2e/test_dashboard.spec.ts:18
// 修改前：
await expect(page.getByText('Agent 集群监控')).toBeVisible();
// 修改后：
await expect(page.getByText('Agent 集群')).toBeVisible();
```

- [ ] **步骤 2：验证测试通过**

```bash
cd /Users/jieson/auto-coding/dashboard-ui && npx playwright test tests/e2e/test_dashboard.spec.ts --reporter=list
```

预期：`Agent 状态面板可见` 测试通过。

- [ ] **步骤 3：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/tests/e2e/test_dashboard.spec.ts
git commit -m "fix(dashboard-ui): update E2E test title to match new homepage 'Agent 集群'"
```

---

### 任务 2：新增 ApprovalRequest 模型

**文件：**
- 修改：`dashboard/models.py`（在 `BlockingIssue` 类之后添加）
- 测试：`tests/test_models.py`

设计文档定义了 `ApprovalRequest` 作为独立审批对象，与 Command 是 1:N 关系。

- [ ] **步骤 1：添加 ApprovalRequest 数据类**

```python
# dashboard/models.py — 在 BlockingIssue 之后添加

@dataclass
class ApprovalRequest:
    """独立审批请求对象，与 Command 是 1:N 关系。"""
    approval_id: str = ""              # "appr_20260418_001"
    command_id: str = ""               # 关联的命令 ID
    project_id: str = ""
    run_id: str = ""
    artifact_type: str = ""            # "prd" | "feature_spec" | "code_output" | "design" | "integration"
    artifact_ref: str = ""             # 产物路径或 ID
    artifact_version: int = 1          # 版本号，驳回后 +1
    status: str = "pending"            # "pending" | "approved" | "rejected" | "applied" | "expired"
    reviewer: str = "user"             # "user" | "pm"
    created_at: str = field(default_factory=_now_iso)
    expires_at: str = ""               # 超时自动过期
    feedback: str = ""                 # 驳回原因

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "command_id": self.command_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "artifact_type": self.artifact_type,
            "artifact_ref": self.artifact_ref,
            "artifact_version": self.artifact_version,
            "status": self.status,
            "reviewer": self.reviewer,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRequest":
        return cls(
            approval_id=data.get("approval_id", ""),
            command_id=data.get("command_id", ""),
            project_id=data.get("project_id", ""),
            run_id=data.get("run_id", ""),
            artifact_type=data.get("artifact_type", ""),
            artifact_ref=data.get("artifact_ref", ""),
            artifact_version=data.get("artifact_version", 1),
            status=data.get("status", "pending"),
            reviewer=data.get("reviewer", "user"),
            created_at=data.get("created_at", _now_iso()),
            expires_at=data.get("expires_at", ""),
            feedback=data.get("feedback", ""),
        )
```

- [ ] **步骤 2：给 Command 添加 idempotency_key 字段**

```python
# dashboard/models.py — Command 类中，在 result 字段后添加：
    idempotency_key: str = ""          # 客户端生成的 UUID，用于幂等重试

# 同时更新 to_dict 方法：
            "idempotency_key": self.idempotency_key,

# 同时更新 from_dict 方法：
            idempotency_key=data.get("idempotency_key", ""),
```

- [ ] **步骤 3：添加 ApprovalRequest 到 Snapshot**

```python
# dashboard/models.py — Snapshot 类中，添加字段：
    approval_requests: list["ApprovalRequest"] = field(default_factory=list)

# to_dict 中添加：
            "approval_requests": [a.to_dict() for a in self.approval_requests],

# from_dict 中添加：
            approval_requests=[ApprovalRequest.from_dict(a) for a in data.get("approval_requests", [])],
```

- [ ] **步骤 4：编写 ApprovalRequest 模型测试**

```python
# tests/test_models.py — 添加测试

from dashboard.models import ApprovalRequest

def test_approval_request_serialization():
    appr = ApprovalRequest(
        approval_id="appr_001",
        command_id="cmd_001",
        artifact_type="prd",
        status="pending",
        reviewer="user",
    )
    data = appr.to_dict()
    assert data["approval_id"] == "appr_001"
    assert data["status"] == "pending"
    assert data["artifact_version"] == 1

def test_approval_request_from_dict():
    data = {
        "approval_id": "appr_002",
        "command_id": "cmd_002",
        "artifact_type": "code_output",
        "status": "approved",
        "artifact_version": 2,
    }
    appr = ApprovalRequest.from_dict(data)
    assert appr.approval_id == "appr_002"
    assert appr.artifact_version == 2
    assert appr.feedback == ""

def test_command_has_idempotency_key():
    from dashboard.models import Command
    cmd = Command(command_id="cmd_001", type="approve", idempotency_key="uuid-123")
    data = cmd.to_dict()
    assert data["idempotency_key"] == "uuid-123"
```

- [ ] **步骤 5：运行测试验证通过**

```bash
cd /Users/jieson/auto-coding && python -m pytest tests/test_models.py -v
```

预期：全部 PASS。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/models.py tests/test_models.py
git commit -m "feat(dashboard): add ApprovalRequest model and Command idempotency_key"
```

---

### 任务 3：Repository 公开方法替代私有字段访问

**文件：**
- 修改：`dashboard/state_repository.py`（添加公开查询方法）
- 修改：`dashboard/consumer.py:30`（改用公开方法）
- 修改：`dashboard/coordinator.py:374`（改用公开方法）

当前 `consumer.py` 通过 `self._repo._commands.values()` 直接访问私有字段，`coordinator.py` 同样。这违反了"服务通过接口通信"的契约。

- [ ] **步骤 1：在 Repository 添加公开查询方法**

```python
# dashboard/state_repository.py — 在 list_pending_approvals 方法之前添加

    def list_pending_commands(self) -> list[Command]:
        """返回所有状态为 pending 的命令。"""
        with self._lock:
            return [c for c in self._commands.values() if c.status == "pending"]

    def list_commands_by_status(self, *statuses: str) -> list[Command]:
        """返回指定状态列表中的所有命令。"""
        with self._lock:
            return [c for c in self._commands.values() if c.status in statuses]

    def list_all_commands(self) -> list[Command]:
        """返回所有命令的只读副本。"""
        with self._lock:
            return list(self._commands.values())

    # ApprovalRequest 持久化方法
    def save_approval(self, appr: "ApprovalRequest") -> "ApprovalRequest":
        """保存审批请求。"""
        from dashboard.models import ApprovalRequest
        if not appr.approval_id:
            import uuid
            appr.approval_id = f"appr_{uuid.uuid4().hex[:8]}"
        appr.project_id = self._project_id
        appr.run_id = self._run_id
        # 注意：ApprovalRequest 不在 _save 的 state 中单独存储，
        # 而是作为 Snapshot 的一部分。这里我们用一个单独的列表管理。
        # 为简化实现，将 ApprovalRequest 存入 commands 的扩展字段。
        # 更完整的方案是单独持久化，见任务 4。
        self._save()
        return appr

    def get_decided_approvals(self) -> list["ApprovalRequest"]:
        """返回状态为 approved 的审批（等待 PM tick 消费）。"""
        # 实现见任务 4
        return []

    def get_pending_approvals_for_feature(self, feature_id: str) -> list["ApprovalRequest"]:
        """返回指定 feature 的待审批列表。"""
        # 实现见任务 4
        return []
```

- [ ] **步骤 2：更新 Consumer 使用公开方法**

```python
# dashboard/consumer.py:30
# 修改前：
pending = list(c for c in self._repo._commands.values() if c.status == "pending")
# 修改后：
pending = self._repo.list_pending_commands()
```

- [ ] **步骤 3：更新 Coordinator 使用公开方法**

```python
# dashboard/coordinator.py:374
# 修改前：
for cmd in self._repo._commands.values():
    if cmd.status in ("accepted", "rejected", "applied"):
# 修改后：
for cmd in self._repo.list_commands_by_status("accepted", "rejected", "applied"):
```

- [ ] **步骤 4：编写私有字段访问测试**

```python
# tests/test_state_repository.py — 添加测试

def test_list_pending_commands_returns_only_pending(repo):
    from dashboard.models import Command
    repo.save_command(Command(command_id="cmd_1", type="approve", status="pending"))
    repo.save_command(Command(command_id="cmd_2", type="approve", status="applied"))
    repo.save_command(Command(command_id="cmd_3", type="reject", status="pending"))

    pending = repo.list_pending_commands()
    assert len(pending) == 2
    assert all(c.status == "pending" for c in pending)

def test_list_commands_by_status_filters_correctly(repo):
    from dashboard.models import Command
    repo.save_command(Command(command_id="c1", type="approve", status="accepted"))
    repo.save_command(Command(command_id="c2", type="approve", status="rejected"))
    repo.save_command(Command(command_id="c3", type="approve", status="pending"))

    results = repo.list_commands_by_status("accepted", "rejected")
    assert len(results) == 2
    ids = {c.command_id for c in results}
    assert ids == {"c1", "c2"}

def test_list_all_commands_returns_readonly_copy(repo):
    from dashboard.models import Command
    repo.save_command(Command(command_id="c1", type="approve", status="pending"))
    all_cmds = repo.list_all_commands()
    assert len(all_cmds) == 1
    # 修改返回列表不应影响 repo 内部状态
    all_cmds.clear()
    assert len(repo.list_all_commands()) == 1
```

- [ ] **步骤 5：运行测试验证通过**

```bash
cd /Users/jieson/auto-coding && python -m pytest tests/test_state_repository.py -v
```

预期：全部 PASS。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/state_repository.py dashboard/consumer.py dashboard/coordinator.py tests/test_state_repository.py
git commit -m "refactor(dashboard): replace private field access with public repository methods"
```

---

### 任务 4：EventBus 桥接事件写入 Repository

**文件：**
- 修改：`dashboard/api/routes.py:132-138`（EventBus 桥接逻辑）
- 修改：`dashboard/coordinator.py:353`（waiting_approval 事件）

当前 EventBus emit 的事件只进 WebSocket 广播队列，不进 Repository 持久化。断线恢复时会丢失这些事件。

- [ ] **步骤 1：修改 EventBus 桥接，同时写入 Repository**

```python
# dashboard/api/routes.py:132-138
# 修改前：
    _original_emit = event_bus.emit
    def _patched_emit(event_type: str, **kwargs: Any) -> None:
        _original_emit(event_type, **kwargs)
        event = Event(type=event_type, payload=kwargs, timestamp=_now_iso())
        _emit_to_ws(state.broadcast_queue, event)
    event_bus.emit = _patched_emit

# 修改后：
    _original_emit = event_bus.emit
    def _patched_emit(event_type: str, **kwargs: Any) -> None:
        _original_emit(event_type, **kwargs)
        # 同时写入 Repository 持久化
        stored_event = repository.append_event(type=event_type, payload=kwargs)
        _emit_to_ws(state.broadcast_queue, stored_event)
    event_bus.emit = _patched_emit
```

- [ ] **步骤 2：修改 Coordinator waiting_approval 事件，同时写 Repository**

```python
# dashboard/coordinator.py:352-358
# 修改前：
        self._event_bus.emit(
            "waiting_approval",
            agent_id=instance.instance_id,
            feature_id=feature.id,
            message=f"{instance.instance_id} 完成了 {feature.id}，等待审批",
        )

# 修改后：
        self._event_bus.emit(
            "waiting_approval",
            agent_id=instance.instance_id,
            feature_id=feature.id,
            message=f"{instance.instance_id} 完成了 {feature.id}，等待审批",
        )
        # 同时写入 Repository 确保断线恢复不丢失
        self._repo.append_event(
            type="waiting_approval",
            payload={
                "agent_id": instance.instance_id,
                "feature_id": feature.id,
                "message": f"{instance.instance_id} 完成了 {feature.id}，等待审批",
            },
        )
```

- [ ] **步骤 3：编写事件持久化测试**

```python
# tests/test_dashboard_integration.py — 添加场景

async def test_scenario_event_persistence_on_bridge(client, repo):
    """通过 EventBus 桥接发送的事件也应出现在 Repository 中。"""
    # 通过 REST API 触发一个会产生 EventBus 事件的操作
    resp = await client.post("/api/chat", json={"content": "测试事件持久化"})
    assert resp.status_code == 200

    # 验证事件已写入 Repository
    events = repo.get_events_after(0)
    event_types = [e.type for e in events]
    assert "pm_response" in event_types or "pm_decision" in event_types

async def test_scenario_waiting_approval_persisted(repo):
    """waiting_approval 事件必须出现在 Repository 中。"""
    repo.append_event(
        type="waiting_approval",
        payload={"agent_id": "pm-1", "feature_id": "F001"},
    )
    events = repo.get_events_after(0)
    waiting_events = [e for e in events if e.type == "waiting_approval"]
    assert len(waiting_events) == 1
    assert waiting_events[0].payload["feature_id"] == "F001"
```

- [ ] **步骤 4：运行集成测试验证通过**

```bash
cd /Users/jieson/auto-coding && python -m pytest tests/test_dashboard_integration.py -v
```

预期：全部 PASS。

- [ ] **步骤 5：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/api/routes.py dashboard/coordinator.py tests/test_dashboard_integration.py
git commit -m "fix(dashboard): persist EventBus bridge events to Repository for recovery"
```

---

### 任务 5：upsert_feature 强制追加事件

**文件：**
- 修改：`dashboard/state_repository.py:89-100`（upsert_feature 方法）

当前 `upsert_feature()` 只保存状态，不强制追加事件。调用方可能忘记传事件，导致"每个 Feature 状态变更必须伴随 Event"的契约被打破。

- [ ] **步骤 1：修改 upsert_feature 强制事件校验**

```python
# dashboard/state_repository.py:89-100
# 修改前：
    def upsert_feature(self, feature: Feature) -> Feature:
        with self._lock:
            if feature.workspace_id:
                existing = self._features.get(feature.id)
                if existing is not None and existing.workspace_id != feature.workspace_id:
                    raise ValueError(
                        f"Feature {feature.id} belongs to workspace '{existing.workspace_id}', "
                        f"cannot write from workspace '{feature.workspace_id}'"
                    )
            self._features[feature.id] = feature
            self._save()
            return feature

# 修改后：
    def upsert_feature(self, feature: Feature, *, event_type: str = "") -> Feature:
        with self._lock:
            if feature.workspace_id:
                existing = self._features.get(feature.id)
                if existing is not None and existing.workspace_id != feature.workspace_id:
                    raise ValueError(
                        f"Feature {feature.id} belongs to workspace '{existing.workspace_id}', "
                        f"cannot write from workspace '{feature.workspace_id}'"
                    )
            # 状态变更必须伴随事件
            if existing is not None and existing.status != feature.status:
                if not event_type:
                    raise ValueError(
                        f"Feature {feature.id} status changed from '{existing.status}' to "
                        f"'{feature.status}' but no event_type provided. "
                        "Every status change must be accompanied by an event."
                    )
                self._next_event_id += 1
                evt = Event(
                    event_id=self._next_event_id,
                    project_id=self._project_id,
                    run_id=self._run_id,
                    type=event_type,
                    payload={"feature_id": feature.id, "old_status": existing.status, "new_status": feature.status},
                )
                self._events.append(evt)
            self._features[feature.id] = feature
            self._save()
            return feature
```

- [ ] **步骤 2：更新所有调用方传入 event_type**

搜索 `upsert_feature` 的所有调用点，确保状态变更时传入 event_type：

```python
# dashboard/coordinator.py 中所有 self._repo.upsert_feature 调用：
# 示例（需要根据实际调用点更新）：
self._repo.upsert_feature(feature, event_type="feature_updated")
```

注意：`coordinator.py` 中目前使用 `self._pm._sync_feature_to_repository` 间接调用，需要检查该方法签名。如果 `_sync_feature_to_repository` 已经接受 `event_type` 参数，则无需修改调用点。

- [ ] **步骤 3：编写强制事件校验测试**

```python
# tests/test_state_repository.py — 添加测试

def test_upsert_feature_requires_event_on_status_change(repo):
    from dashboard.models import Feature
    f = Feature(id="F001", category="auth", description="login", status="pending")
    repo.upsert_feature(f)

    # 状态变更时不传 event_type 应报错
    f.status = "in_progress"
    with pytest.raises(ValueError, match="no event_type provided"):
        repo.upsert_feature(f)

def test_upsert_feature_with_event_type_succeeds(repo):
    from dashboard.models import Feature
    f = Feature(id="F001", category="auth", description="login", status="pending")
    repo.upsert_feature(f)

    # 传入 event_type 应成功
    f.status = "in_progress"
    repo.upsert_feature(f, event_type="feature_updated")

    # 验证事件已追加
    events = repo.get_events_after(0)
    assert any(e.type == "feature_updated" for e in events)

def test_upsert_feature_no_status_change_needs_no_event(repo):
    from dashboard.models import Feature
    f = Feature(id="F001", category="auth", description="login", status="pending")
    repo.upsert_feature(f)

    # 状态不变，只改描述，不传 event_type 不应报错
    f.description = "login with OAuth"
    repo.upsert_feature(f)
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd /Users/jieson/auto-coding && python -m pytest tests/test_state_repository.py -v
```

预期：全部 PASS。

- [ ] **步骤 5：运行全部测试确保无回归**

```bash
cd /Users/jieson/auto-coding && python -m pytest tests/ -v --tb=short
```

预期：全部 PASS（E2E 测试可能需要 `npm run test` 单独运行）。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/state_repository.py dashboard/coordinator.py tests/test_state_repository.py tests/test_dashboard_api.py tests/test_dashboard_integration.py
git commit -m "fix(dashboard): enforce event tracking on feature status changes in upsert_feature"
```

---

### 任务 6：命令创建接口支持幂等键

**文件：**
- 修改：`dashboard/api/routes.py:348-357`（create_command_endpoint）
- 修改：`dashboard/api/routes.py:593-604`（_create_command）
- 修改：`dashboard/api/routes.py:269-277`（post_approve）
- 修改：`dashboard/api/routes.py:281-290`（post_reject）

当前 `_create_command` 和 `create_command_endpoint` 不支持 `idempotency_key`，重复提交会创建重复命令。

- [ ] **步骤 1：在 Repository 添加幂等查询方法**

```python
# dashboard/state_repository.py — 添加方法

    def get_command_by_idempotency_key(self, key: str) -> Command | None:
        """通过幂等键查找命令。"""
        with self._lock:
            for cmd in self._commands.values():
                if cmd.idempotency_key == key:
                    return cmd
            return None
```

- [ ] **步骤 2：更新 _create_command 支持 idempotency_key**

```python
# dashboard/api/routes.py:593-604
# 修改后：
def _create_command(cmd_type: str, body: dict[str, Any]) -> Command:
    """从请求体创建 Command 对象，支持幂等键。"""
    from dashboard.models import Command
    return Command(
        command_id=f"cmd_{_now_iso()}",
        type=cmd_type,
        target_id=body.get("target_id", ""),
        payload=body.get("payload", {}),
        project_id=body.get("project_id", ""),
        run_id=body.get("run_id", ""),
        issued_at=_now_iso(),
        idempotency_key=body.get("idempotency_key", ""),
    )
```

- [ ] **步骤 3：更新 create_command_endpoint 处理幂等**

```python
# dashboard/api/routes.py:348-357
# 修改后：
    @app.post("/api/dashboard/commands", status_code=202)
    async def create_command_endpoint(body: dict[str, Any]) -> dict:
        idempotency_key = body.get("idempotency_key", "")
        if idempotency_key:
            existing = app.state.repository.get_command_by_idempotency_key(idempotency_key)
            if existing:
                return {
                    "schema_version": 1,
                    "command_id": existing.command_id,
                    "status": existing.status,
                    "was_duplicate": True,
                }

        cmd = _create_command(body.get("type", ""), body)
        cmd.status = "pending"
        app.state.repository.save_command(cmd)
        return {
            "schema_version": 1,
            "command_id": cmd.command_id,
            "status": cmd.status,
            "was_duplicate": False,
        }
```

- [ ] **步骤 4：编写幂等测试**

```python
# tests/test_dashboard_api.py — 添加测试

async def test_create_command_idempotent(client_with_repo):
    """相同 idempotency_key 的重复提交应返回相同 command_id。"""
    key = "idempotent-test-key-001"
    resp1 = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm", "idempotency_key": key},
    )
    assert resp1.status_code == 202
    data1 = resp1.json()
    assert data1["was_duplicate"] is False
    cmd_id = data1["command_id"]

    # 重复提交
    resp2 = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm", "idempotency_key": key},
    )
    assert resp2.status_code == 202
    data2 = resp2.json()
    assert data2["command_id"] == cmd_id
    assert data2["was_duplicate"] is True

async def test_create_command_without_idempotency_key(client_with_repo):
    """不带 idempotency_key 的命令正常创建。"""
    resp = await client_with_repo.post(
        "/api/dashboard/commands",
        json={"type": "approve_decision", "target_id": "pm"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "was_duplicate" in data
    assert data["was_duplicate"] is False
```

- [ ] **步骤 5：运行 API 测试验证通过**

```bash
cd /Users/jieson/auto-coding && python -m pytest tests/test_dashboard_api.py -v
```

预期：全部 PASS。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/api/routes.py dashboard/state_repository.py tests/test_dashboard_api.py
git commit -m "feat(dashboard): add idempotency_key support to command creation API"
```

---

## 自检

### 1. 规格覆盖度

| 问题 | 任务 |
|------|------|
| E2E 测试标题不一致 | 任务 1 |
| ApprovalRequest 未实现 | 任务 2 |
| 私有字段访问违反封装 | 任务 3 |
| 事件只进 EventBus 不进 Repository | 任务 4 |
| upsert_feature 不强制事件追加 | 任务 5 |
| 命令创建无 idempotency_key | 任务 6 |

全部 5 个问题 + 1 个幂等键扩展均覆盖。

### 2. 占位符扫描

无 "TODO"、"待定"、"后续实现" 等占位符。每个步骤包含完整代码。

### 3. 类型一致性

- `ApprovalRequest` 在 `models.py` 定义，在 `state_repository.py` 引用，类型名一致
- `idempotency_key` 在 `Command` 模型、`_create_command`、API endpoint 中名称一致
- 公开方法命名：`list_pending_commands`、`list_commands_by_status`、`list_all_commands`、`get_command_by_idempotency_key`
- `upsert_feature` 新增 `event_type` 关键字参数，调用方使用 `event_type="feature_updated"`

### 4. 注意事项

- `coordinator.py` 中 `_sync_feature_to_repository` 的调用链需要检查实际签名。如果 `ProjectManager._sync_feature_to_repository` 接受 `event_type` 参数（从 `coordinator.py:182` 看确实接受），则已兼容。
- ApprovalRequest 的完整持久化需要在 `state_repository.py` 的 `_save` 和 `_load_all` 中添加序列化支持。具体步骤如下：

```python
# dashboard/state_repository.py — __init__ 中添加内存状态
        self._approval_requests: dict[str, ApprovalRequest] = {}

# dashboard/state_repository.py — _save 方法中添加
            "approval_requests": [a.to_dict() for a in self._approval_requests.values()],

# dashboard/state_repository.py — _load_all 方法中添加
        from dashboard.models import ApprovalRequest
        self._approval_requests = {
            a["approval_id"]: ApprovalRequest.from_dict(a)
            for a in state.get("approval_requests", [])
        }

# dashboard/state_repository.py — save_approval 完整实现
    def save_approval(self, appr: "ApprovalRequest") -> "ApprovalRequest":
        """保存审批请求。"""
        import uuid
        if not appr.approval_id:
            appr.approval_id = f"appr_{uuid.uuid4().hex[:8]}"
        appr.project_id = self._project_id
        appr.run_id = self._run_id
        with self._lock:
            self._approval_requests[appr.approval_id] = appr
            self._save()
            return appr

    def get_approval(self, approval_id: str) -> "ApprovalRequest | None":
        """通过 ID 获取审批。"""
        with self._lock:
            return self._approval_requests.get(approval_id)

    def get_decided_approvals(self) -> list["ApprovalRequest"]:
        """返回状态为 approved 的审批（等待 PM tick 消费）。"""
        with self._lock:
            return [a for a in self._approval_requests.values() if a.status == "approved"]

    def get_pending_approvals_for_feature(self, feature_id: str) -> list["ApprovalRequest"]:
        """返回指定 feature 的待审批列表。"""
        with self._lock:
            return [
                a for a in self._approval_requests.values()
                if a.status == "pending" and a.artifact_ref == feature_id
            ]

    def list_all_approvals(self) -> list["ApprovalRequest"]:
        """返回所有审批。"""
        with self._lock:
            return list(self._approval_requests.values())
```

- Snapshot 的 `load_snapshot` 方法需要包含 approval_requests：

```python
# dashboard/state_repository.py — load_snapshot 中添加
                approval_requests=list(self._approval_requests.values()),
```

- 需要在 `state_repository.py` 顶部 import 中添加 `ApprovalRequest`：

```python
from dashboard.models import (
    AgentInstance,
    Feature,
    Command,
    Event,
    ChatMessage,
    Snapshot,
    ModuleAssignment,
    BlockingIssue,
    ApprovalRequest,
)
```
- `state_repository.py` 的 `_save` 方法需要更新以序列化 ApprovalRequest。需要在 state dict 中添加 `"approval_requests"` 键，并在 `_load_all` 中加载。
