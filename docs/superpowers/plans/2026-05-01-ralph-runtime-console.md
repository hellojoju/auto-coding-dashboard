# Ralph Runtime Console 前端实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 基于 `docs/DASHBOARD_ARCHITECTURE.md` 设计文档，实现 Ralph Runtime Console 前端，包含左侧可收起导航、二级 Tab 页管理、WorkUnit 列表/详情、审批中心、证据查看、WebSocket 实时事件。

**架构：** 采用 Command-Driven 架构，前端通过创建 Command 触发状态变更，Coordinator 消费 Command 后驱动 WorkUnit 状态流转。与现有 Feature 系统共存，通过独立的路由（`/ralph/*`）、API 层（`ralph-api.ts`）、Store（`ralph-store.ts`）实现隔离。P0 阶段聚焦 Ralph Runtime Console 范围（WorkUnit 生成之后），不涉及上游 brainstorm/PRD/plan 路由。

**技术栈：** Next.js 16 (App Router), React 19, TypeScript 5, Zustand 5, Tailwind CSS 4, shadcn/ui, lucide-react, vitest, Playwright

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `dashboard/api/routes.py` | 修改 | 新增 10 个 Ralph 只读 API + 3 个 Command API 端点 |
| `dashboard-ui/lib/ralph-types.ts` | 创建 | 完整的 Ralph TypeScript 类型定义 |
| `dashboard-ui/lib/ralph-api.ts` | 创建 | Ralph REST API 客户端 |
| `dashboard-ui/lib/ralph-websocket.ts` | 创建 | Ralph WebSocket 客户端（带 sequence 恢复） |
| `dashboard-ui/lib/ralph-store.ts` | 创建 | Zustand Ralph 状态管理 |
| `dashboard-ui/app/ralph/layout.tsx` | 创建 | Ralph 根布局（Sidebar + Tab + 内容区） |
| `dashboard-ui/components/ralph/sidebar.tsx` | 创建 | 可收起左侧导航栏 |
| `dashboard-ui/components/ralph/tab-bar.tsx` | 创建 | 二级 Tab 页管理栏 |
| `dashboard-ui/components/ralph/run-status-header.tsx` | 创建 | 运行状态头组件 |
| `dashboard-ui/app/ralph/page.tsx` | 创建 | WorkUnit 列表页 |
| `dashboard-ui/components/ralph/work-unit-list.tsx` | 创建 | WorkUnit 列表组件 |
| `dashboard-ui/app/ralph/[id]/page.tsx` | 创建 | WorkUnit 详情页 |
| `dashboard-ui/components/ralph/work-unit-detail.tsx` | 创建 | WorkUnit 详情组件 |
| `dashboard-ui/app/ralph/approvals/page.tsx` | 创建 | 审批中心页面 |
| `dashboard-ui/components/ralph/approval-center.tsx` | 创建 | 审批中心组件 |
| `dashboard-ui/components/ralph/evidence-viewer.tsx` | 创建 | 证据查看组件 |
| `dashboard-ui/lib/ralph-utils.ts` | 创建 | 工具函数（ID 生成、标签截断等） |
| `dashboard-ui/tests/ralph/` | 创建 | Ralph 前端测试目录 |

---

### 任务 A：后端 Ralph API 端点

**文件：**
- 修改：`dashboard/api/routes.py`（在现有 Feature API 之后添加）
- 测试：`tests/test_ralph_api.py`（新建）

在现有 670+ 行 `routes.py` 基础上，新增 Ralph 只读 API 和 Command API 端点，与现有 Feature API 共存。

- [ ] **步骤 1：添加序列化辅助函数**

```python
# dashboard/api/routes.py — 在文件末尾之前添加

def _serialize_work_unit(wu) -> dict:
    """将 WorkUnit 对象序列化为前端可用的 JSON。
    ContextPack 的 prd片段 字段需要序列化别名映射。
    """
    ctx = wu.context_pack
    context_pack = {
        "pack_id": ctx.pack_id,
        "task_goal": ctx.task_goal,
        "prd_fragment": ctx.prd片段,  # 中文字段，前端通过 alias 访问
        "related_files": ctx.related_files,
        "file_summaries": ctx.file_summaries,
        "upstream_summary": ctx.upstream_summary,
        "known_risks": ctx.known_risks,
        "acceptance_criteria": ctx.acceptance_criteria,
        "scope_deny": ctx.scope_deny,
        "trusted_data": ctx.trusted_data,
        "untrusted_data": ctx.untrusted_data,
    } if ctx else None

    harness = wu.task_harness
    task_harness = {
        "harness_id": harness.harness_id,
        "task_goal": harness.task_goal,
        "scope_allow": harness.scope_allow,
        "scope_deny": harness.scope_deny,
        "preflight_checks": harness.preflight_checks,
        "validation_gates": harness.validation_gates,
        "evidence_required": harness.evidence_required,
        "reviewer_role": harness.reviewer_role,
        "stop_conditions": harness.stop_conditions,
    } if harness else None

    return {
        "work_id": wu.work_id,
        "work_type": wu.work_type,
        "title": wu.title,
        "status": wu.status.value if hasattr(wu.status, "value") else wu.status,
        "target": wu.target,
        "scope_allow": wu.scope_allow,
        "scope_deny": wu.scope_deny,
        "dependencies": wu.dependencies,
        "input_files": wu.input_files,
        "expected_output": wu.expected_output,
        "acceptance_criteria": wu.acceptance_criteria,
        "context_pack": context_pack,
        "task_harness": task_harness,
        "assumptions": wu.assumptions,
        "impact_if_wrong": wu.impact_if_wrong,
        "producer_role": wu.producer_role,
        "reviewer_role": wu.reviewer_role,
        "created_at": wu.created_at,
        "updated_at": wu.updated_at,
    }
```

- [ ] **步骤 2：添加 10 个只读 Ralph API 端点**

```python
# dashboard/api/routes.py — 在 router 定义中添加

# GET /api/ralph/work-units — 列出所有 WorkUnit（支持 status 过滤）
@router.get("/ralph/work-units")
async def list_work_units(status: str | None = None):
    ...

# GET /api/ralph/work-units/{work_id} — 获取单个 WorkUnit 详情
@router.get("/ralph/work-units/{work_id}")
async def get_work_unit(work_id: str):
    ...

# GET /api/ralph/evidence/{work_id} — 获取 WorkUnit 的证据列表
@router.get("/ralph/evidence/{work_id}")
async def list_evidence(work_id: str):
    ...

# GET /api/ralph/evidence/{work_id}/{file_path} — 获取单个证据文件内容
@router.get("/ralph/evidence/{work_id}/{file_path:path}")
async def get_evidence_file(work_id: str, file_path: str):
    # 安全：验证 path 不包含上级目录，大文件截断，敏感数据脱敏
    ...

# GET /api/ralph/reviews/{work_id} — 获取 WorkUnit 的审查结果
@router.get("/api/ralph/reviews/{work_id}")
async def get_reviews(work_id: str):
    ...

# GET /api/ralph/blockers — 获取所有阻塞项
@router.get("/ralph/blockers")
async def list_blockers():
    ...

# GET /api/ralph/pending-actions — 获取需要人工处理的异常分支
@router.get("/ralph/pending-actions")
async def list_pending_actions():
    # 仅返回 exceptional branches: dangerous_op, scope_expansion,
    # review_dispute, missing_dep, execution_error, manual_intervention
    ...

# GET /api/ralph/transitions/{work_id} — 获取 WorkUnit 状态转换历史
@router.get("/ralph/transitions/{work_id}")
async def get_transitions(work_id: str):
    ...

# GET /api/ralph/summary — 获取运行概览摘要
@router.get("/ralph/summary")
async def get_summary():
    ...

# GET /api/ralph/health — Ralph 子系统健康检查
@router.get("/ralph/health")
async def ralph_health():
    ...
```

- [ ] **步骤 3：添加 3 个 Command API 端点**

```python
# dashboard/api/routes.py — Command API（前端创建 Command，Coordinator 消费）

# POST /api/ralph/commands — 创建 Command（带幂等键）
@router.post("/ralph/commands")
async def create_command(req: CreateCommandRequest):
    # 验证 command_type 在允许列表中
    # 生成 idempotency_key（如前端未提供）
    # 写入 Repository，异步通知 Coordinator
    ...

# GET /api/ralph/commands/{command_id} — 查询 Command 状态
@router.get("/ralph/commands/{command_id}")
async def get_command(command_id: str):
    ...

# POST /api/ralph/commands/{command_id}/cancel — 取消待执行的 Command
@router.post("/ralph/commands/{command_id}/cancel")
async def cancel_command(command_id: str):
    ...
```

- [ ] **步骤 4：编写后端 API 测试**

```python
# tests/test_ralph_api.py

from fastapi.testclient import TestClient

def test_list_work_units_returns_empty_list(client: TestClient):
    resp = client.get("/api/ralph/work-units")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_get_work_unit_not_found(client: TestClient):
    resp = client.get("/api/ralph/work-units/nonexistent")
    assert resp.status_code == 404

def test_create_command_with_valid_type(client: TestClient):
    resp = client.post("/api/ralph/commands", json={
        "command_type": "accept_review",
        "target_id": "wu-001",
        "reason": "验收通过",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["command_type"] == "accept_review"
    assert "idempotency_key" in data

def test_create_command_rejects_invalid_type(client: TestClient):
    resp = client.post("/api/ralph/commands", json={
        "command_type": "invalid_type",
        "target_id": "wu-001",
    })
    assert resp.status_code == 400

def test_get_evidence_file_validates_path(client: TestClient):
    # 路径遍历攻击应被拒绝
    resp = client.get("/api/ralph/evidence/wu-001/../../etc/passwd")
    assert resp.status_code == 400
```

- [ ] **步骤 5：运行测试验证**

```bash
cd /Users/jieson/auto-coding
python -m pytest tests/test_ralph_api.py -v
```

预期：5 个测试全部通过。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard/api/routes.py tests/test_ralph_api.py
git commit -m "feat(api): add Ralph read-only and Command API endpoints"
```

---

### 任务 B：前端类型系统

**文件：**
- 创建：`dashboard-ui/lib/ralph-types.ts`
- 测试：`dashboard-ui/tests/ralph/types.test.ts`

定义完整的 Ralph TypeScript 类型，与后端 Python schema 对齐。

- [ ] **步骤 1：创建 Ralph 核心类型**

```typescript
// dashboard-ui/lib/ralph-types.ts

// === 状态机 ===

export type WorkUnitStatus =
  | 'draft'
  | 'ready'
  | 'running'
  | 'needs_review'
  | 'accepted'
  | 'needs_rework'
  | 'blocked'
  | 'failed';

export const STATUS_TRANSITIONS: Record<WorkUnitStatus, WorkUnitStatus[]> = {
  draft: ['ready'],
  ready: ['running'],
  running: ['needs_review', 'failed', 'blocked'],
  needs_review: ['accepted', 'needs_rework', 'blocked'],
  failed: ['ready', 'blocked'],
  needs_rework: ['ready'],
  blocked: ['ready'],
  accepted: [],  // 终态
};

// === WorkUnit ===

export interface TaskHarness {
  harness_id: string;
  task_goal: string;
  context_sources: string[];
  context_budget: string;
  allowed_tools: string[];
  denied_tools: string[];
  scope_allow: string[];
  scope_deny: string[];
  preflight_checks: string[];
  checkpoints: string[];
  validation_gates: string[];
  evidence_required: string[];
  retry_policy: { max_retries: number; backoff: string };
  rollback_strategy: string;
  timeout_policy: { max_duration_ms: number; on_timeout: string };
  stop_conditions: string[];
  reviewer_role: string;
}

export interface ContextPack {
  pack_id: string;
  task_goal: string;
  // 注意：后端 Python 字段名为 prd片段，序列化时映射为 prd_fragment
  prd_fragment: string;
  related_files: string[];
  file_summaries: Record<string, string>;
  upstream_summary: string;
  known_risks: string[];
  acceptance_criteria: string[];
  scope_deny: string[];
  trusted_data: string[];
  untrusted_data: string[];
}

export interface WorkUnit {
  work_id: string;
  work_type: 'development' | 'test' | 'review' | 'rework' | 'recon';
  title: string;
  status: WorkUnitStatus;
  background: string;
  target: string;
  scope_allow: string[];
  scope_deny: string[];
  dependencies: string[];
  input_files: string[];
  expected_output: string;
  acceptance_criteria: string[];
  test_command: string;
  rollback_strategy: string;
  context_pack: ContextPack | null;
  task_harness: TaskHarness | null;
  assumptions: string[];
  impact_if_wrong: string;
  risk_notes: string;
  producer_role: string;
  reviewer_role: string;
  created_at: string;
  updated_at: string;
}

// === Evidence ===

export interface Evidence {
  evidence_id: string;
  work_id: string;
  file_name: string;
  file_type: 'diff' | 'test_output' | 'lint' | 'screenshot' | 'log' | 'other';
  size_bytes: number;
  created_at: string;
}

// === Review ===

export interface ReviewResult {
  work_id: string;
  reviewer_context_id: string;
  review_type: string;
  criteria_results: Array<{ criterion: string; passed: boolean; notes: string }>;
  issues_found: Array<{ severity: 'critical' | 'high' | 'medium' | 'low'; description: string; suggestion: string }>;
  evidence_checked: string[];
  harness_checked: boolean;
  conclusion: 'passed' | 'failed';
  recommended_action: string;
}

// === Blocker ===

export interface Blocker {
  blocker_id: string;
  work_id: string;
  reason: string;
  category: 'permission' | 'scope' | 'harness' | 'dependency' | 'resource';
  created_at: string;
  resolved: boolean;
}
```

- [ ] **步骤 2：创建 Command 和 WebSocket 类型**

```typescript
// dashboard-ui/lib/ralph-types.ts — 接续上面的内容

// === Command 类型 ===

export type CommandType =
  | 'accept_review'
  | 'request_rework'
  | 'override_accept'
  | 'expand_scope'
  | 'retry_work_unit'
  | 'cancel_work_unit'
  | 'start_work_unit'
  | 'assign_agent'
  | 'dangerous_op_confirm'
  | 'scope_expansion_confirm'
  | 'review_dispute_resolve'
  | 'missing_dep_resolve'
  | 'execution_error_handle'
  | 'manual_intervention';

export type CommandStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';

export interface RalphCommand {
  command_id: string;
  command_type: CommandType;
  target_id: string;  // work_id 或 blocker_id
  payload: Record<string, unknown>;
  status: CommandStatus;
  idempotency_key: string;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

// === WebSocket Event ===

export type RalphEventType =
  | 'work_unit_created'
  | 'work_unit_updated'
  | 'work_unit_status_changed'
  | 'command_created'
  | 'command_status_changed'
  | 'review_completed'
  | 'evidence_added'
  | 'blocker_created'
  | 'blocker_resolved'
  | 'pending_action_created'
  | 'pending_action_resolved'
  | 'system_heartbeat';

export interface RalphEvent {
  event_id: string;       // UUID，仅作展示用
  sequence: number;       // 单调递增整数，用于断线重连恢复
  event_type: RalphEventType;
  work_id: string | null;
  command_id: string | null;
  data: Record<string, unknown>;
  timestamp: string;
  source: string;
  agent_name: string | null;
  tags: string[];
  sequence_reset: boolean;
  correlation_id: string | null;
}

// === Pending Action（仅异常分支需要人工处理）===

export type PendingActionType =
  | 'dangerous_op'
  | 'scope_expansion'
  | 'review_dispute'
  | 'missing_dep'
  | 'execution_error'
  | 'manual_intervention';

export interface PendingAction {
  action_id: string;
  action_type: PendingActionType;
  work_id: string;
  description: string;
  context: Record<string, unknown>;
  created_at: string;
}
```

- [ ] **步骤 3：创建 UI 辅助类型**

```typescript
// dashboard-ui/lib/ralph-types.ts — 接续

// === Tab 管理 ===

export interface Tab {
  id: string;
  label: string;
  type: 'work_unit' | 'approvals' | 'evidence' | 'overview';
  work_id?: string;
  pinned: boolean;
  created_at: number;
}

// === 运行状态 ===

export interface RunStatus {
  total: number;
  running: number;
  needs_review: number;
  blocked: number;
  accepted: number;
  failed: number;
  latest_event: RalphEvent | null;
  next_action: string | null;
}
```

- [ ] **步骤 4：编写类型测试**

```typescript
// dashboard-ui/tests/ralph/types.test.ts

import { describe, it, expect } from 'vitest';
import { STATUS_TRANSITIONS, type WorkUnitStatus } from '@/lib/ralph-types';

describe('STATUS_TRANSITIONS', () => {
  it('allows draft -> ready', () => {
    expect(STATUS_TRANSITIONS.draft).toContain('ready');
  });

  it('does not allow draft -> running directly', () => {
    expect(STATUS_TRANSITIONS.draft).not.toContain('running');
  });

  it('accepted has no next states (terminal)', () => {
    expect(STATUS_TRANSITIONS.accepted).toHaveLength(0);
  });

  it('covers all 8 statuses', () => {
    const allStatuses: WorkUnitStatus[] = [
      'draft', 'ready', 'running', 'needs_review',
      'accepted', 'needs_rework', 'blocked', 'failed',
    ];
    for (const s of allStatuses) {
      expect(STATUS_TRANSITIONS[s]).toBeDefined();
    }
  });
});
```

- [ ] **步骤 5：运行类型测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx vitest run tests/ralph/types.test.ts
```

预期：4 个测试全部通过。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/lib/ralph-types.ts dashboard-ui/tests/ralph/types.test.ts
git commit -m "feat(types): add complete Ralph TypeScript type system"
```

---

### 任务 C：前端 API 客户端

**文件：**
- 创建：`dashboard-ui/lib/ralph-api.ts`
- 测试：`dashboard-ui/tests/ralph/api.test.ts`

封装所有 Ralph REST API 调用，提供类型安全的客户端。

- [ ] **步骤 1：创建 API 客户端**

```typescript
// dashboard-ui/lib/ralph-api.ts

import type {
  WorkUnit,
  Evidence,
  ReviewResult,
  Blocker,
  PendingAction,
  RalphCommand,
  CommandType,
  RunStatus,
} from './ralph-types';

const BASE = '/api/ralph';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body}`);
  }
  return resp.json() as Promise<T>;
}

// === 只读 API ===

export async function listWorkUnits(status?: string): Promise<WorkUnit[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return request(`/work-units${query}`);
}

export async function getWorkUnit(workId: string): Promise<WorkUnit> {
  return request(`/work-units/${encodeURIComponent(workId)}`);
}

export async function listEvidence(workId: string): Promise<Evidence[]> {
  return request(`/evidence/${encodeURIComponent(workId)}`);
}

export async function getEvidenceFile(workId: string, filePath: string): Promise<string> {
  const encoded = encodeURIComponent(filePath);
  const resp = await fetch(`${BASE}/evidence/${encodeURIComponent(workId)}/${encoded}`);
  if (!resp.ok) throw new Error(`Evidence fetch failed: ${resp.status}`);
  return resp.text();
}

export async function getReviews(workId: string): Promise<ReviewResult[]> {
  return request(`/reviews/${encodeURIComponent(workId)}`);
}

export async function listBlockers(): Promise<Blocker[]> {
  return request('/blockers');
}

export async function listPendingActions(): Promise<PendingAction[]> {
  return request('/pending-actions');
}

export async function getTransitions(workId: string): Promise<Array<{
  from: string; to: string; timestamp: string; agent: string;
}>> {
  return request(`/transitions/${encodeURIComponent(workId)}`);
}

export async function getSummary(): Promise<RunStatus> {
  return request('/summary');
}

// === Command API ===

export async function createCommand(params: {
  command_type: CommandType;
  target_id: string;
  reason?: string;
  payload?: Record<string, unknown>;
}): Promise<RalphCommand> {
  return request('/commands', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getCommand(commandId: string): Promise<RalphCommand> {
  return request(`/commands/${encodeURIComponent(commandId)}`);
}

export async function cancelCommand(commandId: string): Promise<void> {
  return request(`/commands/${encodeURIComponent(commandId)}/cancel`, {
    method: 'POST',
  });
}
```

- [ ] **步骤 2：编写 API 客户端测试**

```typescript
// dashboard-ui/tests/ralph/api.test.ts

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { listWorkUnits, createCommand } from '@/lib/ralph-api';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('listWorkUnits', () => {
  it('returns empty array when no work units exist', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    const result = await listWorkUnits();
    expect(result).toEqual([]);
    expect(global.fetch).toHaveBeenCalledWith('/api/ralph/work-units', expect.any(Object));
  });

  it('passes status query param when provided', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await listWorkUnits('blocked');
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/ralph/work-units?status=blocked',
      expect.any(Object),
    );
  });

  it('throws on API error', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      text: () => Promise.resolve('Internal error'),
      status: 500,
    });

    await expect(listWorkUnits()).rejects.toThrow('API 500: Internal error');
  });
});

describe('createCommand', () => {
  it('sends POST with correct payload', async () => {
    const mockCommand = { command_id: 'cmd-1', command_type: 'accept_review' as const };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCommand),
    });

    const result = await createCommand({
      command_type: 'accept_review',
      target_id: 'wu-001',
      reason: '验收通过',
    });

    expect(result).toEqual(mockCommand);
    expect(global.fetch).toHaveBeenCalledWith('/api/ralph/commands', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command_type: 'accept_review',
        target_id: 'wu-001',
        reason: '验收通过',
      }),
    });
  });
});
```

- [ ] **步骤 3：运行测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx vitest run tests/ralph/api.test.ts
```

预期：4 个测试全部通过。

- [ ] **步骤 4：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/lib/ralph-api.ts dashboard-ui/tests/ralph/api.test.ts
git commit -m "feat(api): add Ralph REST API client with type-safe methods"
```

---

### 任务 D：前端 WebSocket 客户端

**文件：**
- 创建：`dashboard-ui/lib/ralph-websocket.ts`
- 测试：`dashboard-ui/tests/ralph/websocket.test.ts`

实现带 sequence 恢复的 WebSocket 客户端，单调递增 sequence 用于断线重连。

- [ ] **步骤 1：创建 WebSocket 客户端**

```typescript
// dashboard-ui/lib/ralph-websocket.ts

import type { RalphEvent, RalphEventType } from './ralph-types';

export type RalphEventHandler = (event: RalphEvent) => void;

export class RalphWebSocket {
  private ws: WebSocket | null = null;
  private lastSequence = 0;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private handlers: Set<RalphEventHandler> = new Set();
  private url: string;

  constructor(baseUrl: string) {
    // WebSocket URL 从 HTTP URL 转换
    this.url = baseUrl.replace(/^http/, 'ws') + '/ws/ralph';
  }

  connect() {
    const url = this.lastSequence > 0
      ? `${this.url}?after_sequence=${this.lastSequence}`
      : this.url;

    this.ws = new WebSocket(url);

    this.ws.onmessage = (ev) => {
      const event: RalphEvent = JSON.parse(ev.data);

      // 忽略已处理过的旧事件
      if (event.sequence <= this.lastSequence) return;

      this.lastSequence = event.sequence;

      if (event.sequence_reset) {
        this.lastSequence = 0;
        // 触发全量刷新
        this.emit({ ...event, event_type: 'system_heartbeat' as RalphEventType });
      }

      this.emit(event);
    };

    this.ws.onclose = () => {
      // 指数退避重连
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay,
      );
    };

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;  // 重置退避
    };
  }

  on(handler: RalphEventHandler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  get sequence() {
    return this.lastSequence;
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }

  private emit(event: RalphEvent) {
    for (const handler of this.handlers) {
      handler(event);
    }
  }
}
```

- [ ] **步骤 2：编写 WebSocket 测试**

```typescript
// dashboard-ui/tests/ralph/websocket.test.ts

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RalphWebSocket } from '@/lib/ralph-websocket';
import type { RalphEvent } from '@/lib/ralph-types';

describe('RalphWebSocket', () => {
  let rws: RalphWebSocket;

  beforeEach(() => {
    rws = new RalphWebSocket('http://localhost:8000');
  });

  it('constructs correct WebSocket URL', () => {
    expect((rws as any).url).toBe('ws://localhost:8000/ws/ralph');
  });

  it('appends after_sequence when resuming', () => {
    // 模拟已有 sequence
    (rws as any).lastSequence = 42;
    rws.connect();
    // 实际 URL 构建时应包含 ?after_sequence=42
    // 由于浏览器 WebSocket API 限制，这里测试内部 url 属性
    expect((rws as any).url).toContain('after_sequence');
  });

  it('emits events to handlers', () => {
    const handler = vi.fn();
    rws.on(handler);

    const event: RalphEvent = {
      event_id: 'evt-1',
      sequence: 1,
      event_type: 'work_unit_created',
      work_id: 'wu-001',
      command_id: null,
      data: {},
      timestamp: new Date().toISOString(),
      source: 'coordinator',
      agent_name: null,
      tags: [],
      sequence_reset: false,
      correlation_id: null,
    };

    (rws as any).emit(event);
    expect(handler).toHaveBeenCalledWith(event);
  });

  it('ignores events with sequence <= lastSequence', () => {
    (rws as any).lastSequence = 10;
    const handler = vi.fn();
    rws.on(handler);

    const oldEvent: RalphEvent = {
      event_id: 'evt-old',
      sequence: 5,
      event_type: 'work_unit_updated',
      work_id: 'wu-001',
      command_id: null,
      data: {},
      timestamp: new Date().toISOString(),
      source: 'coordinator',
      agent_name: null,
      tags: [],
      sequence_reset: false,
      correlation_id: null,
    };

    (rws as any).emit(oldEvent);
    expect(handler).not.toHaveBeenCalled();
  });
});
```

- [ ] **步骤 3：运行测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx vitest run tests/ralph/websocket.test.ts
```

预期：4 个测试全部通过。

- [ ] **步骤 4：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/lib/ralph-websocket.ts dashboard-ui/tests/ralph/websocket.test.ts
git commit -m "feat(websocket): add Ralph WebSocket client with sequence recovery"
```

---

### 任务 E：Zustand Store

**文件：**
- 创建：`dashboard-ui/lib/ralph-store.ts`
- 测试：`dashboard-ui/tests/ralph/store.test.ts`

管理 Ralph 前端状态，与现有 `store.ts`（Feature 模型）共存。

- [ ] **步骤 1：创建 Ralph Store**

```typescript
// dashboard-ui/lib/ralph-store.ts

import { create } from 'zustand';
import type {
  WorkUnit,
  WorkUnitStatus,
  RalphEvent,
  Tab,
  PendingAction,
  Blocker,
  RunStatus,
  RalphCommand,
  CommandType,
} from './ralph-types';
import * as api from './ralph-api';
import { generateTabId } from './ralph-utils';

interface RalphState {
  // WorkUnits
  workUnits: WorkUnit[];
  selectedWorkUnit: WorkUnit | null;
  statusFilter: WorkUnitStatus | 'all';

  // Tabs
  tabs: Tab[];
  activeTabId: string | null;

  // Approvals
  pendingActions: PendingAction[];
  blockers: Blocker[];

  // Run status
  runStatus: RunStatus | null;

  // WebSocket
  connected: boolean;
  lastEvent: RalphEvent | null;

  // Loading
  loading: boolean;

  // Actions
  setWorkUnits: (units: WorkUnit[]) => void;
  updateWorkUnit: (workId: string, updates: Partial<WorkUnit>) => void;
  setSelectedWorkUnit: (unit: WorkUnit | null) => void;
  setStatusFilter: (filter: WorkUnitStatus | 'all') => void;
  addTab: (tab: Omit<Tab, 'id' | 'created_at'>) => string;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  handleEvent: (event: RalphEvent) => void;
  setPendingActions: (actions: PendingAction[]) => void;
  setBlockers: (blockers: Blocker[]) => void;
  setRunStatus: (status: RunStatus) => void;
  setConnected: (connected: boolean) => void;
  fetchWorkUnits: () => Promise<void>;
  fetchWorkUnit: (workId: string) => Promise<void>;
  createCommand: (params: {
    command_type: CommandType;
    target_id: string;
    reason?: string;
  }) => Promise<RalphCommand>;
  refreshAll: () => Promise<void>;
}

const loadTabs = (): Tab[] => {
  try {
    const stored = localStorage.getItem('ralph-tabs');
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
};

const saveTabs = (tabs: Tab[]) => {
  localStorage.setItem('ralph-tabs', JSON.stringify(tabs));
};

export const useRalphStore = create<RalphState>((set, get) => ({
  workUnits: [],
  selectedWorkUnit: null,
  statusFilter: 'all',
  tabs: loadTabs(),
  activeTabId: null,
  pendingActions: [],
  blockers: [],
  runStatus: null,
  connected: false,
  lastEvent: null,
  loading: false,

  setWorkUnits: (units) => set({ workUnits: units }),

  updateWorkUnit: (workId, updates) =>
    set((state) => ({
      workUnits: state.workUnits.map((wu) =>
        wu.work_id === workId ? { ...wu, ...updates } : wu,
      ),
      selectedWorkUnit:
        state.selectedWorkUnit?.work_id === workId
          ? { ...state.selectedWorkUnit, ...updates }
          : state.selectedWorkUnit,
    })),

  setSelectedWorkUnit: (unit) => set({ selectedWorkUnit: unit }),

  setStatusFilter: (filter) => set({ statusFilter: filter }),

  addTab: (tab) => {
    const id = generateTabId();
    const newTab = { ...tab, id, created_at: Date.now() };
    set((state) => {
      const tabs = [...state.tabs, newTab];
      saveTabs(tabs);
      return { tabs, activeTabId: id };
    });
    return id;
  },

  closeTab: (tabId) =>
    set((state) => {
      const tabs = state.tabs.filter((t) => t.id !== tabId);
      saveTabs(tabs);
      const nextActive =
        state.activeTabId === tabId
          ? tabs[tabs.length - 1]?.id ?? null
          : state.activeTabId;
      return { tabs, activeTabId: nextActive };
    }),

  setActiveTab: (tabId) => set({ activeTabId: tabId }),

  handleEvent: (event) => {
    set({ lastEvent: event });

    // 根据事件类型更新对应数据
    if (
      event.event_type === 'work_unit_status_changed' ||
      event.event_type === 'work_unit_updated'
    ) {
      const { work_id, data } = event;
      if (work_id && data) {
        get().updateWorkUnit(work_id, data as Partial<WorkUnit>);
      }
    }

    if (event.event_type === 'work_unit_created') {
      // 触发全量刷新
      get().fetchWorkUnits();
    }
  },

  setPendingActions: (actions) => set({ pendingActions: actions }),

  setBlockers: (blockers) => set({ blockers }),

  setRunStatus: (status) => set({ runStatus: status }),

  setConnected: (connected) => set({ connected }),

  fetchWorkUnits: async () => {
    set({ loading: true });
    try {
      const { statusFilter } = get();
      const units = await api.listWorkUnits(
        statusFilter === 'all' ? undefined : statusFilter,
      );
      set({ workUnits: units, loading: false });
    } catch (err) {
      console.error('Failed to fetch work units:', err);
      set({ loading: false });
    }
  },

  fetchWorkUnit: async (workId) => {
    try {
      const unit = await api.getWorkUnit(workId);
      set({ selectedWorkUnit: unit });
    } catch (err) {
      console.error('Failed to fetch work unit:', err);
    }
  },

  createCommand: async (params) => {
    const cmd = await api.createCommand(params);
    return cmd;
  },

  refreshAll: async () => {
    await Promise.allSettled([
      get().fetchWorkUnits(),
      api.listPendingActions().then((a) => set({ pendingActions: a })),
      api.listBlockers().then((b) => set({ blockers: b })),
      api.getSummary().then((s) => set({ runStatus: s })),
    ]);
  },
}));
```

- [ ] **步骤 2：编写 Store 测试**

```typescript
// dashboard-ui/tests/ralph/store.test.ts

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useRalphStore } from '@/lib/ralph-store';
import * as api from '@/lib/ralph-api';
import type { WorkUnit, RalphEvent } from '@/lib/ralph-types';

vi.mock('@/lib/ralph-api', () => ({
  listWorkUnits: vi.fn(),
  getWorkUnit: vi.fn(),
  createCommand: vi.fn(),
  listPendingActions: vi.fn(),
  listBlockers: vi.fn(),
  getSummary: vi.fn(),
}));

const mockWorkUnit: WorkUnit = {
  work_id: 'wu-001',
  work_type: 'development',
  title: 'Test WorkUnit',
  status: 'ready',
  background: '',
  target: '',
  scope_allow: [],
  scope_deny: [],
  dependencies: [],
  input_files: [],
  expected_output: '',
  acceptance_criteria: [],
  test_command: '',
  rollback_strategy: 'none',
  context_pack: null,
  task_harness: null,
  assumptions: [],
  impact_if_wrong: '',
  risk_notes: '',
  producer_role: 'developer',
  reviewer_role: 'reviewer',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

beforeEach(() => {
  useRalphStore.setState({
    workUnits: [],
    selectedWorkUnit: null,
    tabs: [],
    pendingActions: [],
    blockers: [],
  });
  vi.clearAllMocks();
});

describe('work unit management', () => {
  it('sets work units', () => {
    useRalphStore.getState().setWorkUnits([mockWorkUnit]);
    expect(useRalphStore.getState().workUnits).toHaveLength(1);
  });

  it('updates a specific work unit', () => {
    useRalphStore.getState().setWorkUnits([mockWorkUnit]);
    useRalphStore.getState().updateWorkUnit('wu-001', { status: 'running' });
    expect(useRalphStore.getState().workUnits[0].status).toBe('running');
  });

  it('updates selected work unit when it matches', () => {
    useRalphStore.getState().setWorkUnits([mockWorkUnit]);
    useRalphStore.getState().setSelectedWorkUnit(mockWorkUnit);
    useRalphStore.getState().updateWorkUnit('wu-001', { status: 'running' });
    expect(useRalphStore.getState().selectedWorkUnit?.status).toBe('running');
  });
});

describe('event handling', () => {
  it('updates work unit on status changed event', () => {
    useRalphStore.getState().setWorkUnits([mockWorkUnit]);

    const event: RalphEvent = {
      event_id: 'evt-1',
      sequence: 1,
      event_type: 'work_unit_status_changed',
      work_id: 'wu-001',
      command_id: null,
      data: { status: 'running' },
      timestamp: new Date().toISOString(),
      source: 'coordinator',
      agent_name: null,
      tags: [],
      sequence_reset: false,
      correlation_id: null,
    };

    useRalphStore.getState().handleEvent(event);
    expect(useRalphStore.getState().workUnits[0].status).toBe('running');
  });
});

describe('tab management', () => {
  it('adds a tab and sets it active', () => {
    const id = useRalphStore.getState().addTab({
      label: 'Test Tab',
      type: 'overview',
      pinned: false,
    });
    const { tabs, activeTabId } = useRalphStore.getState();
    expect(tabs).toHaveLength(1);
    expect(activeTabId).toBe(id);
  });

  it('closes tab and activates previous', () => {
    const id1 = useRalphStore.getState().addTab({ label: 'Tab 1', type: 'overview', pinned: false });
    const id2 = useRalphStore.getState().addTab({ label: 'Tab 2', type: 'overview', pinned: false });
    expect(useRalphStore.getState().activeTabId).toBe(id2);

    useRalphStore.getState().closeTab(id2);
    expect(useRalphStore.getState().activeTabId).toBe(id1);
  });
});
```

- [ ] **步骤 3：运行测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx vitest run tests/ralph/store.test.ts
```

预期：6 个测试全部通过。

- [ ] **步骤 4：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/lib/ralph-store.ts dashboard-ui/tests/ralph/store.test.ts
git commit -m "feat(store): add Zustand store for Ralph state management"
```

---

### 任务 F：工具函数

**文件：**
- 创建：`dashboard-ui/lib/ralph-utils.ts`
- 测试：`dashboard-ui/tests/ralph/utils.test.ts`

- [ ] **步骤 1：创建工具函数**

```typescript
// dashboard-ui/lib/ralph-utils.ts

let tabCounter = 0;

export function generateTabId(): string {
  tabCounter += 1;
  return `tab_${Date.now()}_${tabCounter}`;
}

export function generateIdempotencyKey(): string {
  return `idem_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function truncateLabel(label: string, maxLen = 20): string {
  if (label.length <= maxLen) return label;
  return label.slice(0, maxLen - 1) + '…';
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: '草稿',
    ready: '就绪',
    running: '运行中',
    needs_review: '待审查',
    accepted: '已验收',
    needs_rework: '需返工',
    blocked: '已阻塞',
    failed: '已失败',
  };
  return labels[status] ?? status;
}

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    draft: 'text-gray-400',
    ready: 'text-green-500',
    running: 'text-blue-500',
    needs_review: 'text-yellow-500',
    accepted: 'text-emerald-500',
    needs_rework: 'text-orange-500',
    blocked: 'text-red-500',
    failed: 'text-red-600',
  };
  return colors[status] ?? 'text-gray-500';
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
```

- [ ] **步骤 2：编写测试**

```typescript
// dashboard-ui/tests/ralph/utils.test.ts

import { describe, it, expect } from 'vitest';
import {
  generateTabId,
  generateIdempotencyKey,
  truncateLabel,
  statusLabel,
  statusColor,
  formatDate,
} from '@/lib/ralph-utils';

describe('generateTabId', () => {
  it('returns unique IDs', () => {
    const id1 = generateTabId();
    const id2 = generateTabId();
    expect(id1).not.toBe(id2);
  });

  it('starts with tab_ prefix', () => {
    expect(generateTabId()).toMatch(/^tab_/);
  });
});

describe('truncateLabel', () => {
  it('does not truncate short labels', () => {
    expect(truncateLabel('Short')).toBe('Short');
  });

  it('truncates long labels with ellipsis', () => {
    const long = 'This is a very long label that exceeds twenty chars';
    const result = truncateLabel(long, 20);
    expect(result.length).toBe(20);
    expect(result).toMatch(/…$/);
  });
});

describe('statusLabel', () => {
  it('translates known statuses to Chinese', () => {
    expect(statusLabel('running')).toBe('运行中');
    expect(statusLabel('needs_review')).toBe('待审查');
  });

  it('returns original for unknown status', () => {
    expect(statusLabel('weird_status')).toBe('weird_status');
  });
});

describe('formatDate', () => {
  it('formats ISO date to Chinese locale', () => {
    const result = formatDate('2026-05-01T12:30:00Z');
    expect(result).toMatch(/05/);
    expect(result).toMatch(/12/);
  });
});
```

- [ ] **步骤 3：运行测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx vitest run tests/ralph/utils.test.ts
```

预期：7 个测试全部通过。

- [ ] **步骤 4：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/lib/ralph-utils.ts dashboard-ui/tests/ralph/utils.test.ts
git commit -m "feat(utils): add Ralph frontend utility functions"
```

---

### 任务 G：Sidebar + Tab 布局

**文件：**
- 创建：`dashboard-ui/app/ralph/layout.tsx`
- 创建：`dashboard-ui/components/ralph/sidebar.tsx`
- 创建：`dashboard-ui/components/ralph/tab-bar.tsx`
- 测试：`dashboard-ui/tests/ralph/sidebar.test.tsx`

可收起左侧导航栏（240px 展开 / 64px 收起）+ 二级 Tab 页管理栏（最多 8 个 Tab，localStorage 持久化）。

- [ ] **步骤 1：创建 Sidebar 组件**

```typescript
// dashboard-ui/components/ralph/sidebar.tsx

'use client';

import { useState } from 'react';
import { useRalphStore } from '@/lib/ralph-store';
import { ChevronLeft, ChevronRight, LayoutDashboard, ListTodo, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { id: 'overview', label: '概览', icon: LayoutDashboard },
  { id: 'work-units', label: '工作单元', icon: ListTodo },
  { id: 'approvals', label: '审批中心', icon: ShieldCheck },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { addTab, activeTabId } = useRalphStore();

  return (
    <aside
      className={cn(
        'flex flex-col border-r bg-background transition-all duration-200',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* Header */}
      <div className="flex h-12 items-center justify-between border-b px-3">
        {!collapsed && (
          <span className="text-sm font-semibold">Ralph Console</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="rounded p-1 hover:bg-muted"
          aria-label={collapsed ? '展开导航' : '收起导航'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* Nav Items */}
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => {
                addTab({
                  label: item.label,
                  type: item.id === 'work-units' ? 'overview' : item.id as Tab['type'],
                  pinned: true,
                });
              }}
              className={cn(
                'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-muted',
                collapsed && 'justify-center px-0',
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
```

- [ ] **步骤 2：创建 Tab Bar 组件**

```typescript
// dashboard-ui/components/ralph/tab-bar.tsx

'use client';

import { useRalphStore } from '@/lib/ralph-store';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { truncateLabel } from '@/lib/ralph-utils';

const MAX_TABS = 8;

export function TabBar() {
  const { tabs, activeTabId, setActiveTab, closeTab, addTab } = useRalphStore();

  return (
    <div className="flex items-center border-b bg-muted/30 overflow-x-auto">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={cn(
            'flex items-center gap-2 px-4 py-2 text-sm cursor-pointer border-r',
            'hover:bg-muted transition-colors min-w-0',
            tab.id === activeTabId && 'bg-background border-b-2 border-b-primary',
          )}
        >
          <span className="truncate">{truncateLabel(tab.label, 16)}</span>
          {!tab.pinned && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                closeTab(tab.id);
              }}
              className="rounded p-0.5 hover:bg-muted-foreground/20"
            >
              <X size={12} />
            </button>
          )}
        </div>
      ))}

      {tabs.length < MAX_TABS && (
        <button
          onClick={() =>
            addTab({ label: '新标签页', type: 'overview', pinned: false })
          }
          className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
        >
          +
        </button>
      )}
    </div>
  );
}
```

- [ ] **步骤 3：创建 Ralph 根布局**

```typescript
// dashboard-ui/app/ralph/layout.tsx

import { Sidebar } from '@/components/ralph/sidebar';
import { TabBar } from '@/components/ralph/tab-bar';

export default function RalphLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TabBar />
        <main className="flex-1 overflow-auto p-4">
          {children}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **步骤 4：编写 Sidebar 测试**

```typescript
// dashboard-ui/tests/ralph/sidebar.test.tsx

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sidebar } from '@/components/ralph/sidebar';

describe('Sidebar', () => {
  it('renders nav items', () => {
    render(<Sidebar />);
    expect(screen.getByText('概览')).toBeTruthy();
    expect(screen.getByText('工作单元')).toBeTruthy();
    expect(screen.getByText('审批中心')).toBeTruthy();
  });

  it('collapses when toggle button is clicked', () => {
    render(<Sidebar />);
    // 初始展开状态应看到 Ralph Console 标题
    expect(screen.getByText('Ralph Console')).toBeTruthy();

    // 点击收起按钮
    const toggle = screen.getByRole('button', { name: /收起导航/ });
    toggle.click();

    // 标题应消失（收起状态）
    expect(screen.queryByText('Ralph Console')).toBeNull();
  });
});
```

- [ ] **步骤 5：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/app/ralph/layout.tsx dashboard-ui/components/ralph/sidebar.tsx dashboard-ui/components/ralph/tab-bar.tsx dashboard-ui/tests/ralph/sidebar.test.tsx
git commit -m "feat(ui): add Ralph sidebar, tab bar, and root layout"
```

---

### 任务 H：RunStatusHeader 组件

**文件：**
- 创建：`dashboard-ui/components/ralph/run-status-header.tsx`

P0 最小运行状态显示，展示各状态 WorkUnit 数量和下一步行动建议。

- [ ] **步骤 1：创建 RunStatusHeader**

```typescript
// dashboard-ui/components/ralph/run-status-header.tsx

'use client';

import { useRalphStore } from '@/lib/ralph-store';
import { statusLabel, statusColor } from '@/lib/ralph-utils';
import { Loader2 } from 'lucide-react';

export function RunStatusHeader() {
  const { runStatus, connected, lastEvent, refreshAll } = useRalphStore();

  if (!runStatus) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 size={14} className="animate-spin" />
        加载运行状态...
      </div>
    );
  }

  const statusCounts = [
    { key: 'running', count: runStatus.running },
    { key: 'needs_review', count: runStatus.needs_review },
    { key: 'blocked', count: runStatus.blocked },
    { key: 'accepted', count: runStatus.accepted },
    { key: 'failed', count: runStatus.failed },
  ];

  return (
    <div className="flex items-center gap-4 flex-wrap">
      {/* Connection status */}
      <div className="flex items-center gap-1.5 text-xs">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            connected ? 'bg-green-500' : 'bg-red-500'
          }`}
        />
        {connected ? '已连接' : '断开'}
      </div>

      {/* Status counts */}
      <div className="flex items-center gap-3 text-sm">
        {statusCounts.map(({ key, count }) => (
          <span key={key} className="flex items-center gap-1">
            <span className={statusColor(key)}>{statusLabel(key)}</span>
            <span className="font-mono">{count}</span>
          </span>
        ))}
      </div>

      {/* Next action */}
      {runStatus.next_action && (
        <span className="text-xs text-muted-foreground">
          下一步：{runStatus.next_action}
        </span>
      )}

      {/* Refresh button */}
      <button
        onClick={() => refreshAll()}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        刷新
      </button>
    </div>
  );
}
```

- [ ] **步骤 2：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/components/ralph/run-status-header.tsx
git commit -m "feat(ui): add RunStatusHeader component for P0 minimal status display"
```

---

### 任务 I：WorkUnit 列表页

**文件：**
- 创建：`dashboard-ui/app/ralph/page.tsx`
- 创建：`dashboard-ui/components/ralph/work-unit-list.tsx`
- 测试：`dashboard-ui/tests/ralph/work-unit-list.test.tsx`

WorkUnit 列表页，支持按状态过滤，点击项打开详情页 Tab。

- [ ] **步骤 1：创建 WorkUnit List 组件**

```typescript
// dashboard-ui/components/ralph/work-unit-list.tsx

'use client';

import { useEffect } from 'react';
import { useRalphStore } from '@/lib/ralph-store';
import { statusLabel, statusColor, formatDate } from '@/lib/ralph-utils';
import type { WorkUnitStatus } from '@/lib/ralph-types';
import { cn } from '@/lib/utils';

const ALL_FILTERS: (WorkUnitStatus | 'all')[] = [
  'all', 'ready', 'running', 'needs_review', 'accepted', 'needs_rework', 'blocked', 'failed',
];

export function WorkUnitList() {
  const { workUnits, statusFilter, setStatusFilter, fetchWorkUnits, addTab, loading } =
    useRalphStore();

  useEffect(() => {
    fetchWorkUnits();
  }, [statusFilter]);

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        {ALL_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={cn(
              'px-3 py-1 text-xs rounded-full border transition-colors',
              f === statusFilter
                ? 'bg-primary text-primary-foreground border-primary'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {f === 'all' ? '全部' : statusLabel(f)}
          </button>
        ))}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="text-center py-8 text-muted-foreground">加载中...</div>
      )}

      {/* Empty state */}
      {!loading && workUnits.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          暂无工作单元
        </div>
      )}

      {/* List */}
      <div className="space-y-2">
        {workUnits.map((wu) => (
          <button
            key={wu.work_id}
            onClick={() =>
              addTab({
                label: wu.title,
                type: 'work_unit',
                work_id: wu.work_id,
                pinned: false,
              })
            }
            className="w-full text-left p-4 rounded-lg border hover:bg-muted/50 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-muted-foreground">
                  {wu.work_id}
                </span>
                <span className="font-medium">{wu.title}</span>
              </div>
              <span className={cn('text-xs font-medium', statusColor(wu.status))}>
                {statusLabel(wu.status)}
              </span>
            </div>
            {wu.target && (
              <p className="mt-1 text-sm text-muted-foreground truncate">
                {wu.target}
              </p>
            )}
            <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground">
              <span>{wu.work_type}</span>
              <span>{formatDate(wu.updated_at)}</span>
              {wu.dependencies.length > 0 && (
                <span>依赖: {wu.dependencies.join(', ')}</span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **步骤 2：创建列表页**

```typescript
// dashboard-ui/app/ralph/page.tsx

import { WorkUnitList } from '@/components/ralph/work-unit-list';
import { RunStatusHeader } from '@/components/ralph/run-status-header';

export default function RalphPage() {
  return (
    <div className="space-y-4">
      <RunStatusHeader />
      <h1 className="text-xl font-bold">工作单元</h1>
      <WorkUnitList />
    </div>
  );
}
```

- [ ] **步骤 3：编写列表组件测试**

```typescript
// dashboard-ui/tests/ralph/work-unit-list.test.tsx

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkUnitList } from '@/components/ralph/work-unit-list';
import { useRalphStore } from '@/lib/ralph-store';

vi.mock('@/lib/ralph-store', () => ({
  useRalphStore: vi.fn(),
}));

const mockStore = {
  workUnits: [],
  statusFilter: 'all' as const,
  setStatusFilter: vi.fn(),
  fetchWorkUnits: vi.fn(),
  addTab: vi.fn(),
  loading: false,
};

describe('WorkUnitList', () => {
  it('renders empty state when no work units', () => {
    (useRalphStore as any).mockReturnValue(mockStore);
    render(<WorkUnitList />);
    expect(screen.getByText('暂无工作单元')).toBeTruthy();
  });

  it('renders filter buttons', () => {
    (useRalphStore as any).mockReturnValue(mockStore);
    render(<WorkUnitList />);
    expect(screen.getByText('全部')).toBeTruthy();
    expect(screen.getByText('运行中')).toBeTruthy();
    expect(screen.getByText('待审查')).toBeTruthy();
  });

  it('calls fetchWorkUnits on mount', () => {
    (useRalphStore as any).mockReturnValue(mockStore);
    render(<WorkUnitList />);
    expect(mockStore.fetchWorkUnits).toHaveBeenCalled();
  });
});
```

- [ ] **步骤 4：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/app/ralph/page.tsx dashboard-ui/components/ralph/work-unit-list.tsx dashboard-ui/tests/ralph/work-unit-list.test.tsx
git commit -m "feat(ui): add WorkUnit list page with status filtering"
```

---

### 任务 J：WorkUnit 详情页

**文件：**
- 创建：`dashboard-ui/app/ralph/[id]/page.tsx`
- 创建：`dashboard-ui/components/ralph/work-unit-detail.tsx`
- 测试：`dashboard-ui/tests/ralph/work-unit-detail.test.tsx`

WorkUnit 详情页，展示任务信息、ContextPack、Harness、证据、审查结果、状态转换历史。

- [ ] **步骤 1：创建 WorkUnit Detail 组件**

```typescript
// dashboard-ui/components/ralph/work-unit-detail.tsx

'use client';

import { useEffect } from 'react';
import { useRalphStore } from '@/lib/ralph-store';
import { statusLabel, statusColor, formatDate } from '@/lib/ralph-utils';
import { EvidenceViewer } from './evidence-viewer';
import { cn } from '@/lib/utils';

export function WorkUnitDetail({ workId }: { workId: string }) {
  const { selectedWorkUnit, fetchWorkUnit, loading } = useRalphStore();

  useEffect(() => {
    fetchWorkUnit(workId);
  }, [workId]);

  if (loading || !selectedWorkUnit) {
    return <div className="text-center py-8 text-muted-foreground">加载中...</div>;
  }

  const wu = selectedWorkUnit;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-muted-foreground">{wu.work_id}</span>
          <span className={cn('px-2 py-0.5 text-xs rounded', statusColor(wu.status), 'bg-muted')}>
            {statusLabel(wu.status)}
          </span>
        </div>
        <h2 className="text-2xl font-bold mt-2">{wu.title}</h2>
        {wu.background && (
          <p className="mt-2 text-muted-foreground">{wu.background}</p>
        )}
      </div>

      {/* Target */}
      {wu.target && (
        <section className="p-4 rounded-lg border bg-muted/20">
          <h3 className="font-semibold mb-2">目标</h3>
          <p className="text-sm">{wu.target}</p>
        </section>
      )}

      {/* Acceptance Criteria */}
      {wu.acceptance_criteria.length > 0 && (
        <section className="p-4 rounded-lg border">
          <h3 className="font-semibold mb-2">验收标准</h3>
          <ul className="list-disc list-inside space-y-1 text-sm">
            {wu.acceptance_criteria.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Scope */}
      <section className="grid grid-cols-2 gap-4">
        {wu.scope_allow.length > 0 && (
          <div className="p-4 rounded-lg border border-green-200">
            <h3 className="font-semibold text-green-700 mb-2 text-sm">允许修改</h3>
            <ul className="list-disc list-inside text-xs text-muted-foreground space-y-1">
              {wu.scope_allow.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        {wu.scope_deny.length > 0 && (
          <div className="p-4 rounded-lg border border-red-200">
            <h3 className="font-semibold text-red-700 mb-2 text-sm">禁止修改</h3>
            <ul className="list-disc list-inside text-xs text-muted-foreground space-y-1">
              {wu.scope_deny.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
      </section>

      {/* Context Pack */}
      {wu.context_pack && (
        <section className="p-4 rounded-lg border">
          <h3 className="font-semibold mb-3">上下文包</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">关联文件：</span>
              {wu.context_pack.related_files.join(', ') || '无'}
            </div>
            <div>
              <span className="text-muted-foreground">上游摘要：</span>
              {wu.context_pack.upstream_summary || '无'}
            </div>
            {wu.context_pack.known_risks.length > 0 && (
              <div className="col-span-2">
                <span className="text-muted-foreground">已知风险：</span>
                <ul className="list-disc list-inside mt-1">
                  {wu.context_pack.known_risks.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Task Harness */}
      {wu.task_harness && (
        <section className="p-4 rounded-lg border">
          <h3 className="font-semibold mb-3">任务 Harness</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">目标：</span>
              {wu.task_harness.task_goal}
            </div>
            <div>
              <span className="text-muted-foreground">验收角色：</span>
              {wu.task_harness.reviewer_role}
            </div>
            {wu.task_harness.preflight_checks.length > 0 && (
              <div>
                <span className="text-muted-foreground">前置检查：</span>
                <ul className="list-disc list-inside mt-1">
                  {wu.task_harness.preflight_checks.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            )}
            {wu.task_harness.validation_gates.length > 0 && (
              <div>
                <span className="text-muted-foreground">验证门禁：</span>
                <ul className="list-disc list-inside mt-1">
                  {wu.task_harness.validation_gates.map((g, i) => <li key={i}>{g}</li>)}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Evidence */}
      <EvidenceViewer workId={wu.work_id} />

      {/* Meta */}
      <div className="text-xs text-muted-foreground flex gap-4">
        <span>创建：{formatDate(wu.created_at)}</span>
        <span>更新：{formatDate(wu.updated_at)}</span>
        <span>执行者：{wu.producer_role}</span>
        <span>审查者：{wu.reviewer_role}</span>
      </div>
    </div>
  );
}
```

- [ ] **步骤 2：创建详情页路由**

```typescript
// dashboard-ui/app/ralph/[id]/page.tsx

import { WorkUnitDetail } from '@/components/ralph/work-unit-detail';

export default function WorkUnitDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  // Next.js 16 params 是 Promise
  const { id } = React.use(params);

  return <WorkUnitDetail workId={id} />;
}
```

- [ ] **步骤 3：编写详情页测试**

```typescript
// dashboard-ui/tests/ralph/work-unit-detail.test.tsx

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkUnitDetail } from '@/components/ralph/work-unit-detail';
import { useRalphStore } from '@/lib/ralph-store';

vi.mock('@/lib/ralph-store', () => ({
  useRalphStore: vi.fn(),
}));

const mockWorkUnit = {
  work_id: 'wu-001',
  work_type: 'development',
  title: 'Test WorkUnit',
  status: 'running',
  background: 'Background info',
  target: 'Implement feature X',
  scope_allow: ['src/feature.ts'],
  scope_deny: ['src/core/'],
  dependencies: [],
  input_files: [],
  expected_output: 'Feature X implemented',
  acceptance_criteria: ['Test passes', 'No lint errors'],
  test_command: 'pytest tests/test_feature.py',
  rollback_strategy: 'none',
  context_pack: null,
  task_harness: null,
  assumptions: [],
  impact_if_wrong: '',
  risk_notes: '',
  producer_role: 'developer',
  reviewer_role: 'reviewer',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

describe('WorkUnitDetail', () => {
  it('renders loading state', () => {
    (useRalphStore as any).mockReturnValue({
      selectedWorkUnit: null,
      fetchWorkUnit: vi.fn(),
      loading: true,
    });
    render(<WorkUnitDetail workId="wu-001" />);
    expect(screen.getByText('加载中...')).toBeTruthy();
  });

  it('renders work unit details', () => {
    (useRalphStore as any).mockReturnValue({
      selectedWorkUnit: mockWorkUnit,
      fetchWorkUnit: vi.fn(),
      loading: false,
    });
    render(<WorkUnitDetail workId="wu-001" />);
    expect(screen.getByText('Test WorkUnit')).toBeTruthy();
    expect(screen.getByText('Implement feature X')).toBeTruthy();
    expect(screen.getByText('验收标准')).toBeTruthy();
  });
});
```

- [ ] **步骤 4：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/app/ralph/\[id\]/page.tsx dashboard-ui/components/ralph/work-unit-detail.tsx dashboard-ui/tests/ralph/work-unit-detail.test.tsx
git commit -m "feat(ui): add WorkUnit detail page with context pack and harness display"
```

---

### 任务 K：审批中心

**文件：**
- 创建：`dashboard-ui/app/ralph/approvals/page.tsx`
- 创建：`dashboard-ui/components/ralph/approval-center.tsx`
- 测试：`dashboard-ui/tests/ralph/approval-center.test.tsx`

审批中心仅展示需要人工处理的异常分支（dangerous_op, scope_expansion, review_dispute, missing_dep, execution_error, manual_intervention），通过创建 Command 处理。

- [ ] **步骤 1：创建审批中心组件**

```typescript
// dashboard-ui/components/ralph/approval-center.tsx

'use client';

import { useEffect, useState } from 'react';
import { useRalphStore } from '@/lib/ralph-store';
import { formatDate } from '@/lib/ralph-utils';
import type { PendingAction, CommandType } from '@/lib/ralph-types';
import { cn } from '@/lib/utils';
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import { toast } from 'sonner';

const ACTION_LABELS: Record<PendingAction['action_type'], string> = {
  dangerous_op: '危险操作审批',
  scope_expansion: '范围扩展审批',
  review_dispute: '审查争议处理',
  missing_dep: '缺失依赖处理',
  execution_error: '执行错误处理',
  manual_intervention: '人工干预',
};

const ACTION_ICONS: Record<PendingAction['action_type'], typeof AlertCircle> = {
  dangerous_op: AlertCircle,
  scope_expansion: AlertCircle,
  review_dispute: AlertCircle,
  missing_dep: AlertCircle,
  execution_error: XCircle,
  manual_intervention: CheckCircle,
};

export function ApprovalCenter() {
  const { pendingActions, blockers, setPendingActions, setBlockers, createCommand } =
    useRalphStore();
  const [processingId, setProcessingId] = useState<string | null>(null);

  useEffect(() => {
    // 初始加载
    import('@/lib/ralph-api').then((api) => {
      api.listPendingActions().then(setPendingActions);
      api.listBlockers().then(setBlockers);
    });
  }, []);

  const handleAction = async (action: PendingAction, approve: boolean) => {
    setProcessingId(action.action_id);
    try {
      const commandTypeMap: Record<PendingAction['action_type'], CommandType> = {
        dangerous_op: 'dangerous_op_confirm',
        scope_expansion: 'scope_expansion_confirm',
        review_dispute: 'review_dispute_resolve',
        missing_dep: 'missing_dep_resolve',
        execution_error: 'execution_error_handle',
        manual_intervention: 'manual_intervention',
      };

      await createCommand({
        command_type: commandTypeMap[action.action_type],
        target_id: action.work_id,
        reason: approve ? '批准执行' : '拒绝执行',
        payload: { action_id: action.action_id, approved: approve },
      });

      toast.success(approve ? '已批准' : '已拒绝');
    } catch (err) {
      toast.error('操作失败');
    } finally {
      setProcessingId(null);
    }
  };

  if (pendingActions.length === 0 && blockers.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        暂无待处理的审批事项
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">待处理审批</h2>

      {/* Pending Actions */}
      {pendingActions.map((action) => {
        const Icon = ACTION_ICONS[action.action_type];
        return (
          <div
            key={action.action_id}
            className="p-4 rounded-lg border flex items-start gap-4"
          >
            <Icon className="text-amber-500 mt-1 flex-shrink-0" size={20} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">
                  {ACTION_LABELS[action.action_type]}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDate(action.created_at)}
                </span>
              </div>
              <p className="text-sm mt-1 text-muted-foreground">
                {action.description}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                WorkUnit: {action.work_id}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => handleAction(action, true)}
                disabled={processingId === action.action_id}
                className={cn(
                  'px-4 py-1.5 text-sm rounded-md border transition-colors',
                  'text-green-600 border-green-300 hover:bg-green-50',
                  processingId === action.action_id && 'opacity-50',
                )}
              >
                批准
              </button>
              <button
                onClick={() => handleAction(action, false)}
                disabled={processingId === action.action_id}
                className={cn(
                  'px-4 py-1.5 text-sm rounded-md border transition-colors',
                  'text-red-600 border-red-300 hover:bg-red-50',
                  processingId === action.action_id && 'opacity-50',
                )}
              >
                拒绝
              </button>
            </div>
          </div>
        );
      })}

      {/* Blockers */}
      {blockers.length > 0 && (
        <>
          <h3 className="text-lg font-semibold mt-6">阻塞项</h3>
          {blockers.map((b) => (
            <div
              key={b.blocker_id}
              className="p-4 rounded-lg border border-red-200 bg-red-50/50"
            >
              <div className="flex items-center gap-2">
                <XCircle className="text-red-500" size={16} />
                <span className="font-medium text-sm">{b.reason}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {b.category} · {formatDate(b.created_at)}
              </p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
```

- [ ] **步骤 2：创建审批页路由**

```typescript
// dashboard-ui/app/ralph/approvals/page.tsx

import { ApprovalCenter } from '@/components/ralph/approval-center';
import { RunStatusHeader } from '@/components/ralph/run-status-header';

export default function ApprovalsPage() {
  return (
    <div className="space-y-4">
      <RunStatusHeader />
      <ApprovalCenter />
    </div>
  );
}
```

- [ ] **步骤 3：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/app/ralph/approvals/page.tsx dashboard-ui/components/ralph/approval-center.tsx dashboard-ui/tests/ralph/approval-center.test.tsx
git commit -m "feat(ui): add Approval Center for exceptional branch handling"
```

---

### 任务 L：Evidence Viewer 组件

**文件：**
- 创建：`dashboard-ui/components/ralph/evidence-viewer.tsx`
- 测试：`dashboard-ui/tests/ralph/evidence-viewer.test.tsx`

证据查看组件，支持 diff、测试输出、lint 结果、日志等文件类型。

- [ ] **步骤 1：创建 Evidence Viewer**

```typescript
// dashboard-ui/components/ralph/evidence-viewer.tsx

'use client';

import { useEffect, useState } from 'react';
import { listEvidence, getEvidenceFile } from '@/lib/ralph-api';
import type { Evidence } from '@/lib/ralph-types';
import { FileText, Code, Terminal, Image as ImageIcon, File } from 'lucide-react';
import { cn } from '@/lib/utils';

const TYPE_ICONS: Record<Evidence['file_type'], typeof FileText> = {
  diff: Code,
  test_output: Terminal,
  lint: Terminal,
  screenshot: ImageIcon,
  log: FileText,
  other: File,
};

const TYPE_LABELS: Record<Evidence['file_type'], string> = {
  diff: '代码变更',
  test_output: '测试输出',
  lint: 'Lint 结果',
  screenshot: '截图',
  log: '日志',
  other: '其他',
};

export function EvidenceViewer({ workId }: { workId: string }) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listEvidence(workId).then(setEvidence).catch(() => setEvidence([]));
  }, [workId]);

  const openEvidence = async (ev: Evidence) => {
    setSelected(ev);
    setLoading(true);
    try {
      const text = await getEvidenceFile(workId, ev.file_name);
      setContent(text);
    } catch {
      setContent('加载失败');
    } finally {
      setLoading(false);
    }
  };

  if (evidence.length === 0) {
    return null;
  }

  return (
    <section className="border rounded-lg overflow-hidden">
      <h3 className="font-semibold p-4 border-b">证据文件 ({evidence.length})</h3>
      <div className="grid grid-cols-3">
        {/* File list */}
        <div className="col-span-1 border-r max-h-64 overflow-auto">
          {evidence.map((ev) => {
            const Icon = TYPE_ICONS[ev.file_type];
            return (
              <button
                key={ev.evidence_id}
                onClick={() => openEvidence(ev)}
                className={cn(
                  'w-full text-left px-4 py-3 flex items-center gap-3 border-b text-sm hover:bg-muted',
                  selected?.evidence_id === ev.evidence_id && 'bg-muted',
                )}
              >
                <Icon size={14} className="text-muted-foreground flex-shrink-0" />
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs">{ev.file_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {TYPE_LABELS[ev.file_type]} · {(ev.size_bytes / 1024).toFixed(1)}KB
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="col-span-2 max-h-64 overflow-auto p-4 bg-muted/20">
          {loading && <div className="text-muted-foreground text-sm">加载中...</div>}
          {!loading && selected && (
            <pre className="text-xs whitespace-pre-wrap font-mono">
              {content}
            </pre>
          )}
          {!loading && !selected && (
            <div className="text-muted-foreground text-sm">选择文件查看内容</div>
          )}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **步骤 2：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/components/ralph/evidence-viewer.tsx dashboard-ui/tests/ralph/evidence-viewer.test.tsx
git commit -m "feat(ui): add EvidenceViewer component for evidence file browsing"
```

---

### 任务 M：集成测试与 E2E

**文件：**
- 创建：`dashboard-ui/tests/e2e/test_ralph.spec.ts`
- 创建：`dashboard-ui/tests/ralph/integration.test.ts`

- [ ] **步骤 1：创建 E2E 测试**

```typescript
// dashboard-ui/tests/e2e/test_ralph.spec.ts

import { test, expect } from '@playwright/test';

test.describe('Ralph Runtime Console', () => {
  test('Ralph page loads with sidebar', async ({ page }) => {
    await page.goto('/ralph');
    await expect(page.getByText('Ralph Console')).toBeVisible();
    await expect(page.getByText('工作单元')).toBeVisible();
    await expect(page.getByText('审批中心')).toBeVisible();
  });

  test('WorkUnit list shows empty state', async ({ page }) => {
    await page.goto('/ralph');
    await expect(page.getByText('暂无工作单元')).toBeVisible();
  });

  test('Status filter buttons are visible', async ({ page }) => {
    await page.goto('/ralph');
    await expect(page.getByText('全部')).toBeVisible();
    await expect(page.getByText('运行中')).toBeVisible();
    await expect(page.getByText('待审查')).toBeVisible();
  });

  test('Approvals page loads', async ({ page }) => {
    await page.goto('/ralph/approvals');
    await expect(page.getByText('待处理审批')).toBeVisible();
  });

  test('Sidebar collapses and expands', async ({ page }) => {
    await page.goto('/ralph');
    // 初始展开
    await expect(page.getByText('Ralph Console')).toBeVisible();

    // 点击收起
    await page.getByRole('button', { name: /收起导航/ }).click();
    await expect(page.getByText('Ralph Console')).not.toBeVisible();

    // 点击展开
    await page.getByRole('button', { name: /展开导航/ }).click();
    await expect(page.getByText('Ralph Console')).toBeVisible();
  });
});
```

- [ ] **步骤 2：运行 E2E 测试**

```bash
cd /Users/jieson/auto-coding/dashboard-ui
npx playwright test tests/e2e/test_ralph.spec.ts --reporter=list
```

预期：5 个 E2E 测试全部通过。

- [ ] **步骤 3：Commit**

```bash
cd /Users/jieson/auto-coding
git add dashboard-ui/tests/e2e/test_ralph.spec.ts
git commit -m "test(e2e): add Ralph Runtime Console E2E tests"
```

---

## 任务依赖关系

```
A (后端 API) → B (类型) → C (API 客户端) → E (Store)
              B → D (WebSocket) → E
              B → F (工具函数)
              E → G (Sidebar+Tab 布局) → H (RunStatusHeader)
              E → I (WorkUnit 列表) → J (WorkUnit 详情)
              E → K (审批中心)
              E → L (Evidence Viewer)
              I + J + K + L → M (集成测试与 E2E)
```

可并行的组：
- B + F（类型和工具函数互不依赖）
- C + D（API 客户端和 WebSocket 互不依赖，都只依赖 B）
- G + H（布局组件可并行）
- I + J + K + L（页面组件可并行，都只依赖 E）

## 技术约束

1. **不修改现有 Feature 系统**：所有 Ralph 代码在独立目录/命名空间下
2. **Tailwind CSS 4**：使用 `@import "tailwindcss"` 新语法
3. **shadcn/ui 现有组件**：优先复用 `components/ui/` 已有组件
4. **Zustand 5**：使用 `create` API，不使用 middleware
5. **Next.js 16**：`params` 是 Promise，需要 `React.use(params)` 或 `await params`
6. **localStorage 持久化 Tab**：读写在 store action 中封装
7. **WebSocket 重连**：指数退避，最大 30 秒
8. **证据安全**：大文件截断、路径验证、敏感数据脱敏在后端完成
9. **Command 语义**：前端只创建 Command，不直接修改状态
10. **测试覆盖率**：所有新文件 80%+ 覆盖率

## MVP 完成定义

- [ ] 所有 P0 组件（Sidebar, TabBar, RunStatusHeader, WorkUnitList, WorkUnitDetail, ApprovalCenter, EvidenceViewer）可正常渲染
- [ ] WebSocket 连接建立并能接收事件
- [ ] 状态过滤功能正常工作
- [ ] 点击 WorkUnit 能打开详情 Tab
- [ ] 审批中心能展示待处理项并能创建 Command
- [ ] 证据查看器能加载并显示文件内容
- [ ] 所有单元测试和 E2E 测试通过
- [ ] TypeScript 类型检查无错误 (`tsc --noEmit`)
- [ ] 无 `console.log` 语句在生产代码中
