# Auto-Coding 架构重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 auto-coding 项目从分散状态管理重构为统一架构，借鉴 multica 和 auto-coding-agent-demo 的最佳实践

**架构：** 通过 9 个阶段逐步实现：基线冻结 → 架构契约 → 工作流协议 → 统一状态源 → 阻塞协议 → 前端状态治理 → 统一操作入口 → 任务台账 → 服务拆分。核心原则是每次只改一个关注点，每步都有测试验证。

**技术栈：** Python 3.12+, FastAPI, SQLite, pytest, Next.js 14+ (dashboard UI), Zustand, TanStack Query

---

## 文件结构

**新建文件：**
- `AGENTS.md` — 架构契约文档（参考 multica/AGENTS.md）
- `CLAUDE.md` — 工作流约束文档（参考 agent-demo/CLAUDE.md）
- `Makefile` — 操作接口（参考 multica/Makefile）
- `dashboard/models.py` 扩展 — BlockingIssue 模型
- `core/blocking_tracker.py` — 阻塞问题追踪器
- `core/execution_ledger.py` — 执行计划台账
- `core/feature_execution_service.py` — 特性执行服务（从 ProjectManager 拆分）
- `core/feature_verification_service.py` — 特性验收服务（从 ProjectManager 拆分）
- `core/git_service.py` — Git 操作服务（从 ProjectManager 拆分）
- `tests/test_blocking_tracker.py`
- `tests/test_execution_ledger.py`
- `tests/test_feature_execution_service.py`
- `tests/test_feature_verification_service.py`
- `tests/test_git_service.py`
- `tests/test_unified_state.py`
- `dashboard-ui/lib/store.ts` — Zustand store 重构
- `dashboard-ui/lib/api.ts` — API 客户端统一

**修改文件：**
- `dashboard/models.py` — 添加 BlockingIssue 模型，扩展 Feature 模型
- `dashboard/state_repository.py` — 添加 BlockingIssue 和 ExecutionRun 持久化
- `core/feature_tracker.py` — 与统一状态源对接
- `core/project_manager.py` — 拆分服务后瘦身
- `dashboard/coordinator.py` — 使用新服务而非直接调用 ProjectManager
- `cli.py` — 添加 plan、explain-state、blocked、doctor 命令
- `dashboard/api.py` — 添加阻塞问题 API

---

## Phase 0：基线冻结（验证现有功能）

### 任务 0.1：验证现有测试基线

**文件：**
- 测试：`tests/test_feature_tracker.py`

- [ ] **步骤 1：编写 feature tracker 测试**

```python
"""测试 FeatureTracker 基本功能"""
import pytest
from pathlib import Path
import json
from core.feature_tracker import FeatureTracker, Feature
from core.config import FEATURES_FILE


@pytest.fixture(autouse=True)
def clean_features(tmp_path, monkeypatch):
    """每个测试使用独立的临时文件"""
    feat_file = tmp_path / "features.json"
    monkeypatch.setattr("core.config.FEATURES_FILE", feat_file)
    if feat_file.exists():
        feat_file.unlink()
    yield


def test_add_and_get_feature():
    tracker = FeatureTracker()
    feature = Feature(id="feat-1", category="backend", description="Test feature", priority="P1", assigned_to="backend")
    tracker.add(feature)
    result = tracker.get("feat-1")
    assert result is not None
    assert result.description == "Test feature"


def test_get_nonexistent_feature():
    tracker = FeatureTracker()
    assert tracker.get("nonexistent") is None
```

- [ ] **步骤 2：运行测试验证通过**

运行：`pytest tests/test_feature_tracker.py -v`
预期：全部 PASS

---

### 任务 0.2：编写 task queue 测试

**文件：**
- 测试：`tests/test_task_queue.py`

- [ ] **步骤 1：编写 task queue 测试**

```python
"""测试 TaskQueue 基本功能"""
import pytest
from pathlib import Path
from core.task_queue import TaskQueue, TaskStatus


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时数据库"""
    db_file = tmp_path / "tasks.db"
    monkeypatch.setattr("core.config.TASK_DB", db_file)
    if db_file.exists():
        db_file.unlink()
    yield


def test_enqueue_and_dequeue():
    queue = TaskQueue()
    task_id = queue.enqueue("feat-1", "backend", "Test task", priority=1)
    assert "task-feat-1-backend" == task_id

    task = queue.dequeue()
    assert task is not None
    assert task["feature_id"] == "feat-1"
    assert task["status"] == "running"


def test_dequeue_empty_queue():
    queue = TaskQueue()
    assert queue.dequeue() is None


def test_priority_ordering():
    queue = TaskQueue()
    queue.enqueue("feat-1", "backend", "Low priority", priority=1)
    queue.enqueue("feat-2", "frontend", "High priority", priority=5)

    task = queue.dequeue()
    assert task["feature_id"] == "feat-2"  # 高优先级先出


def test_complete_task():
    queue = TaskQueue()
    queue.enqueue("feat-1", "backend", "Test task")
    queue.dequeue()
    queue.complete("task-feat-1-backend", "Success")

    stats = queue.stats()
    assert stats.get("completed", 0) == 1


def test_retry_on_failure():
    queue = TaskQueue()
    queue.enqueue("feat-1", "backend", "Test task")
    queue.dequeue()
    should_retry = queue.fail("task-feat-1-backend", "Error occurred")
    assert should_retry is True  # retry_count < max_retries
```

- [ ] **步骤 2：运行测试验证通过**

运行：`pytest tests/test_task_queue.py -v`
预期：全部 PASS

---

## Phase 1：架构契约（AGENTS.md）

### 任务 1.1：创建 AGENTS.md 架构契约

**文件：**
- 创建：`AGENTS.md`
- 参考：`multica/AGENTS.md`（借鉴其结构）

- [ ] **步骤 1：读取 multica AGENTS.md 参考结构**

运行：`cat multica/AGENTS.md`
目的：了解 multica 的架构契约格式

- [ ] **步骤 2：创建 AGENTS.md**

```markdown
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
- 支持 agents/features/commands/events/chat/module_assignments

### PMCoordinator
- 在每步执行之间插入审批闸门
- 处理用户审批/驳回命令
- 同步状态到 Repository
- 静默检测和 Agent 进程管理

## 状态归属表

| 数据类型 | 唯一来源 | 写入者 | 读取者 |
|---------|---------|--------|--------|
| Feature 列表 | `features.json` + StateRepository | FeatureTracker | Dashboard, Coordinator |
| Agent 实例 | StateRepository | Coordinator | Dashboard |
| 任务队列 | SQLite `tasks.db` | TaskQueue | AgentPool |
| 命令 | StateRepository | REST API | Coordinator |
| 事件 | StateRepository | EventBus | Dashboard (WebSocket) |
| 阻塞问题 | StateRepository | Coordinator/Services | Dashboard, CLI |
| 执行台账 | `execution-plan.json` | ExecutionLedger | Dashboard, CLI |

## 数据流

```
用户发起项目 → CLI → ProjectManager.initialize_project()
                        ↓
                   生成 features.json
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

1. 所有状态写入必须通过 StateRepository，禁止直接写 features.json/state.json
2. 服务之间通过接口通信，不直接依赖实现
3. 阻塞问题必须作为一等公民记录，不能仅用 error_log 字符串
4. 每个 Feature 状态变更必须伴随一个 Event 记录
```

- [ ] **步骤 3：验证 AGENTS.md 格式正确**

运行：`cat AGENTS.md | head -5`
预期：看到正确的 frontmatter 和标题

---

## Phase 2：工作流协议（CLAUDE.md）

### 任务 2.1：创建 CLAUDE.md 工作流约束

**文件：**
- 创建：`CLAUDE.md`
- 参考：`auto-coding-agent-demo/CLAUDE.md`

- [ ] **步骤 1：读取 agent-demo CLAUDE.md 参考结构**

运行：`cat auto-coding-agent-demo/CLAUDE.md`
目的：了解工作流约束格式

- [ ] **步骤 2：创建 CLAUDE.md**

```markdown
# Auto-Coding 工作流协议

> 本文档定义 Agent 开发工作流的约束和步骤。所有参与的 Claude Code 实例必须遵循此协议。

## 工作流概述

Agent 按照 `task.json` 定义的任务列表，逐个执行 Feature。每个 Feature 完成后暂停，等待 PM 审批。

## Agent 执行步骤

1. **读取任务**：从 features.json 获取下一个 ready 的 Feature
2. **理解上下文**：
   - 读取 PRD 摘要
   - 读取已完成的依赖 Feature 的变更文件
3. **实现**：
   - 遵循 TDD：先写测试，再写实现
   - 每次修改后运行相关测试
   - 遵循项目编码风格（见 .claude/CLAUDE.md）
4. **验证**：
   - 确保涉及的文件已创建/修改
   - 运行语法检查
   - 运行 E2E 测试（如适用）
5. **报告**：输出结构化 JSON 结果：
   ```json
   {
     "success": true,
     "feature_id": "feat-1",
     "files_changed": ["src/a.py", "src/b.py"],
     "test_passed": true,
     "notes": "..."
   }
   ```

## 禁止行为

- 不要跳过测试
- 不要修改 features.json 或 state.json（由系统管理）
- 不要执行 git commit（由 GitService 统一管理）
- 不要在代码中硬编码密钥

## 错误处理

- 遇到无法解决的问题时，输出明确的错误原因和建议
- 不要静默失败
- 重试次数有限（默认 3 次），超限后标记为 blocked
```

- [ ] **步骤 3：验证 CLAUDE.md 格式正确**

运行：`cat CLAUDE.md | head -5`
预期：看到正确的标题

---

## Phase 3：统一状态源

### 任务 3.1：扩展 BlockingIssue 模型

**文件：**
- 修改：`dashboard/models.py`

- [ ] **步骤 1：添加 BlockingIssue 模型到 models.py**

在 `DashboardState` 之后添加：

```python
@dataclass
class BlockingIssue:
    """阻塞问题，作为一等公民对象。"""
    issue_id: str = ""
    issue_type: str = ""  # missing_env, missing_credentials, external_service_down, dependency_not_met, code_error, resource_exhausted
    feature_id: str = ""
    detected_by: str = ""  # coordinator, agent, verification
    detected_at: str = field(default_factory=_now_iso)
    description: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: str = ""
    resolution: str = ""

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "feature_id": self.feature_id,
            "detected_by": self.detected_by,
            "detected_at": self.detected_at,
            "description": self.description,
            "context": self.context,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlockingIssue":
        return cls(
            issue_id=data.get("issue_id", ""),
            issue_type=data.get("issue_type", ""),
            feature_id=data.get("feature_id", ""),
            detected_by=data.get("detected_by", ""),
            detected_at=data.get("detected_at", _now_iso()),
            description=data.get("description", ""),
            context=data.get("context", {}),
            resolved=data.get("resolved", False),
            resolved_at=data.get("resolved_at", ""),
            resolution=data.get("resolution", ""),
        )
```

- [ ] **步骤 2：扩展 Feature 模型添加 blocking_issues 字段**

在 `Feature` 数据类中添加：

```python
    blocking_issues: list[str] = field(default_factory=list)  # issue_id 列表
```

在 `to_dict` 中添加：

```python
            "blocking_issues": self.blocking_issues,
```

在 `from_dict` 中添加：

```python
            blocking_issues=data.get("blocking_issues", []),
```

---

### 任务 3.2：扩展 StateRepository 支持 BlockingIssue

**文件：**
- 修改：`dashboard/state_repository.py`

- [ ] **步骤 1：添加 BlockingIssue 导入**

在 imports 中添加 `BlockingIssue`：

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
)
```

- [ ] **步骤 2：添加 BlockingIssue 存储**

在 `__init__` 中添加：

```python
        self._blocking_issues: dict[str, BlockingIssue] = {}
```

在 `_save` 方法的 state dict 中添加：

```python
            "blocking_issues": [i.to_dict() for i in self._blocking_issues.values()],
```

在 `_load_all` 方法中添加：

```python
        self._blocking_issues = {
            i["issue_id"]: BlockingIssue.from_dict(i)
            for i in state.get("blocking_issues", [])
        }
```

- [ ] **步骤 3：添加 BlockingIssue CRUD 方法**

在 Module Assignment 方法之后添加：

```python
    # --- Blocking Issue ---

    def create_blocking_issue(self, issue: BlockingIssue) -> BlockingIssue:
        with self._lock:
            if not issue.issue_id:
                import uuid
                issue.issue_id = str(uuid.uuid4())[:8]
            self._blocking_issues[issue.issue_id] = issue
            self._save()
            return issue

    def resolve_blocking_issue(self, issue_id: str, resolution: str) -> bool:
        with self._lock:
            issue = self._blocking_issues.get(issue_id)
            if issue is None:
                return False
            issue.resolved = True
            issue.resolved_at = _now_iso()
            issue.resolution = resolution
            self._save()
            return True

    def get_blocking_issue(self, issue_id: str) -> BlockingIssue | None:
        with self._lock:
            return self._blocking_issues.get(issue_id)

    def list_blocking_issues(self, *, feature_id: str | None = None, resolved: bool | None = None) -> list[BlockingIssue]:
        with self._lock:
            issues = list(self._blocking_issues.values())
            if feature_id is not None:
                issues = [i for i in issues if i.feature_id == feature_id]
            if resolved is not None:
                issues = [i for i in issues if i.resolved == resolved]
            return issues
```

- [ ] **步骤 4：扩展 Snapshot 包含 blocking_issues**

在 `load_snapshot` 方法中添加：

```python
                blocking_issues=[i.to_dict() for i in self._blocking_issues.values()],
```

---

### 任务 3.3：编写 StateRepository 测试

**文件：**
- 测试：`tests/test_unified_state.py`

- [ ] **步骤 1：编写 BlockingIssue 测试**

```python
"""测试 StateRepository 的 BlockingIssue 功能"""
import pytest
from pathlib import Path
from dashboard.state_repository import ProjectStateRepository
from dashboard.models import BlockingIssue


@pytest.fixture
def repo(tmp_path):
    return ProjectStateRepository(base_dir=tmp_path, project_id="test-project")


def test_create_blocking_issue(repo):
    issue = BlockingIssue(
        feature_id="feat-1",
        issue_type="missing_env",
        detected_by="agent",
        description="Missing OPENAI_API_KEY",
    )
    saved = repo.create_blocking_issue(issue)
    assert saved.issue_id != ""

    retrieved = repo.get_blocking_issue(saved.issue_id)
    assert retrieved is not None
    assert retrieved.feature_id == "feat-1"
    assert retrieved.resolved is False


def test_resolve_blocking_issue(repo):
    issue = BlockingIssue(
        feature_id="feat-1",
        issue_type="missing_env",
        detected_by="agent",
        description="Missing key",
    )
    saved = repo.create_blocking_issue(issue)
    assert repo.resolve_blocking_issue(saved.issue_id, "Added to .env") is True

    resolved = repo.get_blocking_issue(saved.issue_id)
    assert resolved.resolved is True
    assert resolved.resolution == "Added to .env"


def test_list_blocking_issues_filtering(repo):
    issue1 = repo.create_blocking_issue(BlockingIssue(
        feature_id="feat-1", issue_type="missing_env", detected_by="agent", description="Missing key"
    ))
    issue2 = repo.create_blocking_issue(BlockingIssue(
        feature_id="feat-2", issue_type="dependency_not_met", detected_by="coordinator", description="Dep not met"
    ))

    all_issues = repo.list_blocking_issues()
    assert len(all_issues) == 2

    feat1_issues = repo.list_blocking_issues(feature_id="feat-1")
    assert len(feat1_issues) == 1

    repo.resolve_blocking_issue(issue1.issue_id, "Fixed")
    unresolved = repo.list_blocking_issues(resolved=False)
    assert len(unresolved) == 1
```

- [ ] **步骤 2：运行测试验证通过**

运行：`pytest tests/test_unified_state.py -v`
预期：全部 PASS

---

### 任务 3.4：编写 Makefile

**文件：**
- 创建：`Makefile`
- 参考：`multica/Makefile`

- [ ] **步骤 1：读取 multica Makefile 参考**

运行：`cat multica/Makefile`
目的：了解 Makefile 结构和常用命令

- [ ] **步骤 2：创建 Makefile**

```makefile
.PHONY: help dev test lint format install init dashboard dashboard-dev clean

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装 Python 依赖
	pip install -r requirements.txt

init: ## 初始化项目（创建 features.json 等）
	python -m core.initialize

dev: ## 开发模式启动（后端 + 前端）
	@echo "Starting backend..."
	python -m uvicorn dashboard.api:app --reload --port 8000 &
	@echo "Starting frontend..."
	cd dashboard-ui && npm run dev &
	wait

test: ## 运行所有测试
	pytest tests/ -v --cov=core --cov=dashboard --cov-report=term-missing

lint: ## 运行 ruff 检查
	ruff check core/ dashboard/ tests/

format: ## 格式化代码
	black core/ dashboard/ tests/
	isort core/ dashboard/ tests/

dashboard: ## 仅启动后端 API
	python -m uvicorn dashboard.api:app --reload --port 8000

dashboard-dev: ## 仅启动前端
	cd dashboard-ui && npm run dev

clean: ## 清理缓存和临时文件
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov
```

- [ ] **步骤 3：验证 Makefile 语法**

运行：`make help`
预期：显示所有可用命令列表

---

## Phase 4：阻塞协议

### 任务 4.1：创建 BlockingTracker

**文件：**
- 创建：`core/blocking_tracker.py`
- 测试：`tests/test_blocking_tracker.py`

- [ ] **步骤 1：编写 BlockingTracker 测试**

```python
"""测试 BlockingTracker"""
import pytest
from core.blocking_tracker import BlockingTracker, BlockingIssueType


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    from dashboard.state_repository import ProjectStateRepository
    repo = ProjectStateRepository(base_dir=tmp_path, project_id="test")
    return BlockingTracker(repo)


def test_detect_missing_env(tracker):
    issue = tracker.detect_missing_env("feat-1", "OPENAI_API_KEY")
    assert issue is not None
    assert issue.issue_type == BlockingIssueType.MISSING_ENV.value
    assert issue.feature_id == "feat-1"


def test_detect_dependency_not_met(tracker):
    issue = tracker.detect_dependency_not_met("feat-1", "feat-0", "feat-0 is blocked")
    assert issue is not None
    assert issue.issue_type == BlockingIssueType.DEPENDENCY_NOT_MET.value


def test_resolve_issue(tracker):
    issue = tracker.detect_missing_env("feat-1", "API_KEY")
    assert tracker.resolve_issue(issue.issue_id, "Added key to .env") is True

    remaining = tracker.list_open_issues()
    assert len(remaining) == 0


def test_list_open_issues(tracker):
    tracker.detect_missing_env("feat-1", "KEY_A")
    tracker.detect_missing_env("feat-2", "KEY_B")
    tracker.detect_missing_env("feat-3", "KEY_C")

    issues = tracker.list_open_issues()
    assert len(issues) == 3

    # 解决一个后只剩两个
    tracker.resolve_issue(issues[0].issue_id, "Fixed")
    assert len(tracker.list_open_issues()) == 2
```

- [ ] **步骤 2：创建 BlockingTracker 实现**

```python
"""BlockingIssue 追踪器 — 作为一等公民管理阻塞问题"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import TYPE_CHECKING

from dashboard.models import BlockingIssue

if TYPE_CHECKING:
    from dashboard.state_repository import ProjectStateRepository


class BlockingIssueType(str, Enum):
    MISSING_ENV = "missing_env"
    MISSING_CREDENTIALS = "missing_credentials"
    EXTERNAL_SERVICE_DOWN = "external_service_down"
    DEPENDENCY_NOT_MET = "dependency_not_met"
    CODE_ERROR = "code_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"


class BlockingTracker:
    """阻塞问题的高级追踪器，封装 StateRepository 的 issue CRUD。"""

    def __init__(self, repo: "ProjectStateRepository") -> None:
        self._repo = repo

    def detect_missing_env(self, feature_id: str, variable: str) -> BlockingIssue:
        """检测缺失环境变量"""
        return self._create_issue(
            issue_type=BlockingIssueType.MISSING_ENV,
            feature_id=feature_id,
            description=f"Missing environment variable: {variable}",
            context={"variable": variable},
            detected_by="agent",
        )

    def detect_dependency_not_met(self, feature_id: str, dep_id: str, reason: str) -> BlockingIssue:
        """检测依赖未满足"""
        return self._create_issue(
            issue_type=BlockingIssueType.DEPENDENCY_NOT_MET,
            feature_id=feature_id,
            description=f"Dependency {dep_id} not met: {reason}",
            context={"dependency": dep_id, "reason": reason},
            detected_by="coordinator",
        )

    def detect_code_error(self, feature_id: str, error: str) -> BlockingIssue:
        """检测代码执行错误"""
        return self._create_issue(
            issue_type=BlockingIssueType.CODE_ERROR,
            feature_id=feature_id,
            description=f"Code execution failed: {error}",
            context={"error": error},
            detected_by="agent",
        )

    def resolve_issue(self, issue_id: str, resolution: str) -> bool:
        """解决阻塞问题"""
        return self._repo.resolve_blocking_issue(issue_id, resolution)

    def list_open_issues(self, *, feature_id: str | None = None) -> list[BlockingIssue]:
        """列出所有未解决的阻塞问题"""
        return self._repo.list_blocking_issues(feature_id=feature_id, resolved=False)

    def get_issue(self, issue_id: str) -> BlockingIssue | None:
        """获取单个阻塞问题"""
        return self._repo.get_blocking_issue(issue_id)

    def _create_issue(
        self,
        *,
        issue_type: BlockingIssueType,
        feature_id: str,
        description: str,
        context: dict,
        detected_by: str,
    ) -> BlockingIssue:
        issue = BlockingIssue(
            issue_type=issue_type.value,
            feature_id=feature_id,
            description=description,
            context=context,
            detected_by=detected_by,
        )
        return self._repo.create_blocking_issue(issue)
```

- [ ] **步骤 3：运行测试验证通过**

运行：`pytest tests/test_blocking_tracker.py -v`
预期：全部 PASS

---

## Phase 5：前端状态治理

### 任务 5.1：重构 Zustand Store

**文件：**
- 修改：`dashboard-ui/lib/store.ts`

- [ ] **步骤 1：读取当前 store.ts 内容**

运行：`cat dashboard-ui/lib/store.ts`
目的：了解现有状态结构

- [ ] **步骤 2：重构 store 为分离关注点**

将 store 分为三个独立 slice：

```typescript
// Agent slice
interface AgentSlice {
  agents: AgentInstance[]
  updateAgent: (agent: AgentInstance) => void
  updateAgents: (agents: AgentInstance[]) => void
}

// Feature slice
interface FeatureSlice {
  features: Feature[]
  blockingIssues: BlockingIssue[]
  updateFeature: (feature: Feature) => void
  updateFeatures: (features: Feature[]) => void
  updateBlockingIssues: (issues: BlockingIssue[]) => void
}

// UI slice
interface UISlice {
  selectedFeature: string | null
  selectedAgent: string | null
  setSelectedFeature: (id: string | null) => void
  setSelectedAgent: (id: string | null) => void
}

const useAppStore = create<AgentSlice & FeatureSlice & UISlice>()(
  devtools(
    subscribeWithSelector(
      set => ({
        // Agent
        agents: [],
        updateAgent: (agent) =>
          set(state => ({
            agents: state.agents.map(a => (a.id === agent.id ? agent : a)),
          })),
        updateAgents: (agents) => set({ agents }),

        // Feature
        features: [],
        blockingIssues: [],
        updateFeature: (feature) =>
          set(state => ({
            features: state.features.map(f => (f.id === feature.id ? feature : f)),
          })),
        updateFeatures: (features) => set({ features }),
        updateBlockingIssues: (blockingIssues) => set({ blockingIssues }),

        // UI
        selectedFeature: null,
        selectedAgent: null,
        setSelectedFeature: (id) => set({ selectedFeature: id }),
        setSelectedAgent: (id) => set({ selectedAgent: id }),
      }),
    ),
  ),
)

export default useAppStore
```

---

## Phase 6：统一操作入口

### 任务 6.1：添加 CLI 命令

**文件：**
- 修改：`cli.py`

- [ ] **步骤 1：添加 `plan` 命令**

在 cli.py 的 argparse 中添加：

```python
    # plan 命令
    plan_parser = subparsers.add_parser("plan", help="Show execution plan and feature queue")
    plan_parser.set_defaults(func=cmd_plan)
```

实现 `cmd_plan`：

```python
def cmd_plan(args):
    """显示执行计划和特性队列"""
    from core.feature_tracker import FeatureTracker
    tracker = FeatureTracker()
    summary = tracker.summary()

    print(f"\n{'='*60}")
    print(f"  Execution Plan Summary")
    print(f"{'='*60}")
    print(f"  Total: {summary['total']}")
    print(f"  Done: {summary['done']}")
    print(f"  In Progress: {summary['in_progress']}")
    print(f"  Blocked: {summary['blocked']}")
    print(f"  Pending: {summary['pending']}")
    print(f"{'='*60}\n")

    # Pending features
    pending = [f for f in tracker.all_features() if f.status == "pending"]
    if pending:
        print("  Pending features:")
        for f in pending:
            deps = f.dependencies if f.dependencies else []
            deps_str = f" (deps: {', '.join(deps)})" if deps else ""
            print(f"    [{f.priority}] {f.id}: {f.description}{deps_str}")

    # Blocked features
    blocked = [f for f in tracker.all_features() if f.status == "blocked"]
    if blocked:
        print(f"\n  Blocked features:")
        for f in blocked:
            last_error = f.error_log[-1] if f.error_log else "Unknown"
            print(f"    {f.id}: {last_error}")
```

- [ ] **步骤 2：添加 `blocked` 命令**

```python
    blocked_parser = subparsers.add_parser("blocked", help="Show blocking issues")
    blocked_parser.set_defaults(func=cmd_blocked)
```

```python
def cmd_blocked(args):
    """显示所有阻塞问题"""
    from pathlib import Path
    from dashboard.state_repository import ProjectStateRepository
    from core.config import PROJECT_DIR

    repo = ProjectStateRepository(base_dir=PROJECT_DIR, project_id="auto-coding")
    issues = repo.list_blocking_issues(resolved=False)

    if not issues:
        print("No blocking issues.")
        return

    print(f"\n{'='*60}")
    print(f"  Blocking Issues ({len(issues)})")
    print(f"{'='*60}")
    for issue in issues:
        print(f"  [{issue.issue_type}] {issue.feature_id}")
        print(f"    Description: {issue.description}")
        print(f"    Detected by: {issue.detected_by}")
        print(f"    Detected at: {issue.detected_at}")
        if issue.context:
            print(f"    Context: {issue.context}")
        print()
```

- [ ] **步骤 3：添加 `doctor` 命令**

```python
    doctor_parser = subparsers.add_parser("doctor", help="Run health checks")
    doctor_parser.set_defaults(func=cmd_doctor)
```

```python
def cmd_doctor(args):
    """运行系统健康检查"""
    import os
    from pathlib import Path
    from core.config import FEATURES_FILE, TASK_DB, PROJECT_DIR

    print(f"\n{'='*60}")
    print(f"  System Health Check")
    print(f"{'='*60}")

    # Check environment variables
    required_vars = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    print("\n  Environment Variables:")
    for var in required_vars:
        value = os.environ.get(var)
        status = "OK" if value else "MISSING"
        print(f"    {var}: {status}")

    # Check feature file
    print(f"\n  Feature File:")
    if FEATURES_FILE.exists():
        print(f"    {FEATURES_FILE}: EXISTS")
    else:
        print(f"    {FEATURES_FILE}: MISSING")

    # Check task DB
    print(f"\n  Task Database:")
    if TASK_DB.exists():
        print(f"    {TASK_DB}: EXISTS")
    else:
        print(f"    {TASK_DB}: MISSING")

    # Check git
    print(f"\n  Git:")
    git_dir = PROJECT_DIR / ".git"
    if git_dir.exists():
        print(f"    Git repo: OK")
    else:
        print(f"    Git repo: NOT INITIALIZED")

    print(f"\n{'='*60}\n")
```

- [ ] **步骤 4：添加 `explain-state` 命令**

```python
    state_parser = subparsers.add_parser("explain-state", help="Explain current project state")
    state_parser.set_defaults(func=cmd_explain_state)
```

```python
def cmd_explain_state(args):
    """用自然语言解释当前项目状态"""
    from core.feature_tracker import FeatureTracker
    tracker = FeatureTracker()
    summary = tracker.summary()

    print(f"\nProject Status:")
    print(f"  {summary['done']}/{summary['total']} features completed")
    print(f"  {summary['in_progress']} in progress")
    print(f"  {summary['blocked']} blocked")
    print(f"  {summary['pending']} pending")

    if summary['blocked'] > 0:
        blocked = [f for f in tracker.all_features() if f.status == "blocked"]
        print(f"\nBlocking issues:")
        for f in blocked:
            print(f"  - {f.id}: {f.error_log[-1] if f.error_log else 'Unknown'}")

    next_ready = tracker.get_next_ready()
    if next_ready:
        print(f"\nNext feature to execute:")
        print(f"  [{next_ready.priority}] {next_ready.id}: {next_ready.description}")
    else:
        print(f"\nNo features ready to execute.")
```

---

## Phase 7：任务台账

### 任务 7.1：创建 ExecutionLedger

**文件：**
- 创建：`core/execution_ledger.py`
- 测试：`tests/test_execution_ledger.py`

- [ ] **步骤 1：编写 ExecutionLedger 测试**

```python
"""测试 ExecutionLedger"""
import pytest
import json
from pathlib import Path
from core.execution_ledger import ExecutionLedger, ExecutionEntry, ExecutionStatus


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    ledger_file = tmp_path / "execution-plan.json"
    monkeypatch.setattr("core.config.EXECUTION_LEDGER_FILE", ledger_file)
    if ledger_file.exists():
        ledger_file.unlink()
    return ExecutionLedger()


def test_log_execution(ledger):
    entry = ledger.log_execution(
        feature_id="feat-1",
        status=ExecutionStatus.COMPLETED,
        agent_id="backend-1",
        files_changed=["src/a.py"],
    )
    assert entry.feature_id == "feat-1"
    assert entry.status == ExecutionStatus.COMPLETED.value


def test_get_feature_history(ledger):
    ledger.log_execution("feat-1", ExecutionStatus.FAILED, "backend-1")
    ledger.log_execution("feat-1", ExecutionStatus.COMPLETED, "backend-1")

    history = ledger.get_feature_history("feat-1")
    assert len(history) == 2
    assert history[0].status == ExecutionStatus.FAILED.value
    assert history[1].status == ExecutionStatus.COMPLETED.value


def test_get_summary(ledger):
    ledger.log_execution("feat-1", ExecutionStatus.COMPLETED, "backend-1")
    ledger.log_execution("feat-2", ExecutionStatus.COMPLETED, "frontend-1")
    ledger.log_execution("feat-3", ExecutionStatus.FAILED, "backend-1")

    summary = ledger.get_summary()
    assert summary["total_executions"] == 3
    assert summary["completed"] == 2
    assert summary["failed"] == 1
```

- [ ] **步骤 2：创建 ExecutionLedger 实现**

```python
"""执行计划台账 — 审计文件，记录每次执行的完整生命周期"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from core.config import EXECUTION_LEDGER_FILE


class ExecutionStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    BLOCKED = "blocked"


@dataclass
class ExecutionEntry:
    feature_id: str
    status: str
    agent_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    files_changed: list[str] = field(default_factory=list)
    retry_count: int = 0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ExecutionLedger:
    """执行台账，记录每个 Feature 的执行历史"""

    def __init__(self) -> None:
        self._entries: list[ExecutionEntry] = []
        self._load()

    def _load(self) -> None:
        if EXECUTION_LEDGER_FILE.exists():
            data = json.loads(EXECUTION_LEDGER_FILE.read_text(encoding="utf-8"))
            self._entries = [ExecutionEntry.from_dict(e) for e in data.get("executions", [])]

    def _save(self) -> None:
        EXECUTION_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "executions": [e.to_dict() for e in self._entries],
            "summary": self.get_summary(),
        }
        EXECUTION_LEDGER_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def log_execution(
        self,
        feature_id: str,
        status: ExecutionStatus,
        agent_id: str = "",
        files_changed: list[str] | None = None,
        error: str = "",
    ) -> ExecutionEntry:
        entry = ExecutionEntry(
            feature_id=feature_id,
            status=status.value,
            agent_id=agent_id,
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat() if status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.BLOCKED) else "",
            error=error,
            files_changed=files_changed or [],
        )
        self._entries.append(entry)
        self._save()
        return entry

    def get_feature_history(self, feature_id: str) -> list[ExecutionEntry]:
        return [e for e in self._entries if e.feature_id == feature_id]

    def get_summary(self) -> dict:
        total = len(self._entries)
        completed = sum(1 for e in self._entries if e.status == ExecutionStatus.COMPLETED.value)
        failed = sum(1 for e in self._entries if e.status == ExecutionStatus.FAILED.value)
        return {
            "total_executions": total,
            "completed": completed,
            "failed": failed,
        }
```

- [ ] **步骤 3：在 core/config.py 中添加配置**

```python
EXECUTION_LEDGER_FILE = PROJECT_DIR / "data" / "execution-plan.json"
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_execution_ledger.py -v`
预期：全部 PASS

---

## Phase 8：PM/Coordinator 服务拆分

### 任务 8.1：创建 FeatureExecutionService

**文件：**
- 创建：`core/feature_execution_service.py`
- 测试：`tests/test_feature_execution_service.py`

- [ ] **步骤 1：编写 FeatureExecutionService 测试**

```python
"""测试 FeatureExecutionService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from core.feature_execution_service import FeatureExecutionService


@pytest.fixture
def service(tmp_path):
    mock_pm = MagicMock()
    mock_pm.project_dir = tmp_path
    mock_pm._get_prd_summary.return_value = "Test PRD"
    mock_pm._get_deps_context.return_value = {"deps": []}
    mock_pool = MagicMock()
    mock_tracker = MagicMock()
    return FeatureExecutionService(mock_pm, mock_pool, mock_tracker)


def test_execute_feature_success(service):
    """测试 Agent 成功执行 Feature"""
    feature = MagicMock()
    feature.id = "feat-1"
    feature.description = "Test feature"
    feature.category = "backend"
    feature.priority = "P1"
    feature.test_steps = []
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = MagicMock()
    mock_agent.execute.return_value = {
        "success": True,
        "files_changed": ["src/a.py"],
    }

    result = service.execute(feature, mock_agent)
    assert result["success"] is True
    assert result["files_changed"] == ["src/a.py"]


def test_execute_feature_failure(service):
    """测试 Agent 执行失败"""
    feature = MagicMock()
    feature.id = "feat-1"
    feature.description = "Test feature"
    feature.category = "backend"
    feature.priority = "P1"
    feature.test_steps = []
    feature.dependencies = []

    mock_agent = MagicMock()
    mock_agent.execute = MagicMock()
    mock_agent.execute.side_effect = Exception("Connection error")

    result = service.execute(feature, mock_agent)
    assert result["success"] is False
    assert "Connection error" in result["error"]
```

- [ ] **步骤 2：创建 FeatureExecutionService 实现**

```python
"""Feature 执行服务 — 从 ProjectManager 拆分的执行逻辑"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.feature_tracker import Feature, FeatureTracker
    from agents.pool import AgentPool

logger = logging.getLogger(__name__)


class FeatureExecutionService:
    """负责单个 Feature 的执行流程。"""

    def __init__(
        self,
        project_manager,
        pool: "AgentPool",
        tracker: "FeatureTracker",
    ) -> None:
        self._pm = project_manager
        self._pool = pool
        self._tracker = tracker

    def execute(self, feature: "Feature", agent) -> dict:
        """执行单个 Feature，返回执行结果。

        Returns:
            {"success": bool, "files_changed": list, "error": str (可选)}
        """
        try:
            result = asyncio.run(agent.execute({
                "feature_id": feature.id,
                "description": feature.description,
                "category": feature.category,
                "priority": feature.priority,
                "test_steps": getattr(feature, "test_steps", []),
                "project_dir": str(self._pm.project_dir),
                "workspace_dir": str(getattr(agent, "workspace_path", "")),
                "prd_summary": self._pm._get_prd_summary(),
                "dependencies_context": self._pm._get_deps_context(feature),
            }))
            return {
                "success": result.get("success", False),
                "files_changed": result.get("files_changed", []),
                "error": result.get("error", ""),
            }
        except Exception as e:
            logger.error(f"Feature execution error for {feature.id}: {e}")
            return {"success": False, "files_changed": [], "error": str(e)}
```

- [ ] **步骤 3：运行测试验证通过**

运行：`pytest tests/test_feature_execution_service.py -v`
预期：全部 PASS

---

### 任务 8.2：创建 FeatureVerificationService

**文件：**
- 创建：`core/feature_verification_service.py`
- 测试：`tests/test_feature_verification_service.py`

- [ ] **步骤 1：编写 FeatureVerificationService 测试**

```python
"""测试 FeatureVerificationService"""
import pytest
from pathlib import Path
from core.feature_verification_service import FeatureVerificationService


@pytest.fixture
def service(tmp_path):
    return FeatureVerificationService(tmp_path)


def test_verify_files_exist(service):
    """验证文件存在"""
    feature = type("Feature", (), {
        "id": "feat-1",
        "files_changed": ["test_a.py", "test_b.py"],
    })()

    # 创建文件
    (service._base_dir / "test_a.py").write_text("pass")
    (service._base_dir / "test_b.py").write_text("pass")

    result = service.verify(feature)
    assert result["pass"] is True


def test_verify_files_missing(service):
    """验证文件缺失"""
    feature = type("Feature", (), {
        "id": "feat-1",
        "files_changed": ["nonexistent.py"],
    })()

    result = service.verify(feature)
    assert result["pass"] is False
    assert len(result["errors"]) > 0


def test_verify_syntax_ok(service):
    """验证语法正确"""
    feature = type("Feature", (), {
        "id": "feat-1",
        "files_changed": ["test_syntax.py"],
    })()

    (service._base_dir / "test_syntax.py").write_text("x = 1 + 2\n")

    result = service.verify(feature, check_syntax=True)
    assert result["pass"] is True


def test_verify_syntax_error(service):
    """验证语法错误"""
    feature = type("Feature", (), {
        "id": "feat-1",
        "files_changed": ["test_bad_syntax.py"],
    })()

    (service._base_dir / "test_bad_syntax.py").write_text("def broken(\n")

    result = service.verify(feature, check_syntax=True)
    assert result["pass"] is False
    assert "syntax" in result["errors"][0].lower() or "invalid" in result["errors"][0].lower()
```

- [ ] **步骤 2：创建 FeatureVerificationService 实现**

```python
"""Feature 验收服务 — 从 ProjectManager 拆分的验证逻辑"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.feature_tracker import Feature

logger = logging.getLogger(__name__)


class FeatureVerificationService:
    """负责 Feature 执行后的验收检查。"""

    def __init__(self, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir)

    def verify(
        self,
        feature: "Feature",
        *,
        check_syntax: bool = False,
    ) -> dict:
        """验证 Feature 产物。

        Returns:
            {"pass": bool, "errors": list[str]}
        """
        errors: list[str] = []

        # 检查文件存在
        files_changed = getattr(feature, "files_changed", [])
        for file_path in files_changed:
            full_path = self._base_dir / file_path
            if not full_path.exists():
                errors.append(f"Missing file: {file_path}")

        # 语法检查
        if check_syntax and not errors:
            for file_path in files_changed:
                if file_path.endswith(".py"):
                    full_path = self._base_dir / file_path
                    if full_path.exists():
                        syntax_ok, syntax_err = self._check_python_syntax(full_path)
                        if not syntax_ok:
                            errors.append(f"Syntax error in {file_path}: {syntax_err}")

        return {"pass": len(errors) == 0, "errors": errors}

    def _check_python_syntax(self, file_path: Path) -> tuple[bool, str]:
        """检查 Python 文件语法"""
        try:
            source = file_path.read_text(encoding="utf-8")
            ast.parse(source)
            return True, ""
        except SyntaxError as e:
            return False, str(e)
```

- [ ] **步骤 3：运行测试验证通过**

运行：`pytest tests/test_feature_verification_service.py -v`
预期：全部 PASS

---

### 任务 8.3：创建 GitService

**文件：**
- 创建：`core/git_service.py`
- 测试：`tests/test_git_service.py`

- [ ] **步骤 1：编写 GitService 测试**

```python
"""测试 GitService"""
import pytest
from pathlib import Path
from core.git_service import GitService


@pytest.fixture
def git_service(tmp_path):
    service = GitService(tmp_path)
    service.init()
    return service


def test_init_creates_git_dir(git_service, tmp_path):
    assert (tmp_path / ".git").exists()


def test_commit(git_service, tmp_path):
    # 创建文件
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    git_service.commit("feat: add test file")

    log = git_service.log()
    assert len(log) >= 1
    assert "feat: add test file" in log[0]


def test_commit_no_changes(git_service, tmp_path):
    result = git_service.commit("nothing to commit")
    assert result is False


def test_create_branch(git_service, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    git_service.commit("initial commit")

    git_service.create_branch("test-branch")
    branches = git_service.list_branches()
    assert "test-branch" in branches
```

- [ ] **步骤 2：创建 GitService 实现**

```python
"""Git 操作服务 — 从 ProjectManager 拆分"""

from __future__ import annotations

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GitService:
    """封装所有 Git 操作"""

    def __init__(self, repo_dir: Path | str) -> None:
        self._repo_dir = Path(repo_dir)

    def init(self) -> None:
        """初始化 git 仓库"""
        if not (self._repo_dir / ".git").exists():
            self._run(["git", "init"], cwd=self._repo_dir)

    def commit(self, message: str) -> bool:
        """提交变更。如果没有变更返回 False。"""
        self._run(["git", "add", "-A"], cwd=self._repo_dir)
        # 检查是否有变更
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self._repo_dir,
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return False
        self._run(["git", "commit", "-m", message], cwd=self._repo_dir)
        return True

    def create_branch(self, branch: str) -> None:
        """创建分支"""
        self._run(["git", "branch", branch], cwd=self._repo_dir)

    def checkout(self, branch: str) -> None:
        """切换分支"""
        self._run(["git", "checkout", branch], cwd=self._repo_dir)

    def merge(self, branch: str) -> None:
        """合并分支"""
        self._run(["git", "merge", branch], cwd=self._repo_dir)

    def log(self, n: int = 10) -> list[str]:
        """获取最近 N 条提交信息"""
        result = self._run(
            ["git", "log", f"--oneline", f"-{n}"],
            cwd=self._repo_dir,
            capture_output=True,
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []

    def list_branches(self) -> list[str]:
        """列出所有本地分支"""
        result = self._run(
            ["git", "branch", "--list"],
            cwd=self._repo_dir,
            capture_output=True,
        )
        return [
            line.strip().lstrip("* ")
            for line in result.stdout.strip().split("\n")
            if line.strip()
        ]

    def _run(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, **kwargs)
```

- [ ] **步骤 3：运行测试验证通过**

运行：`pytest tests/test_git_service.py -v`
预期：全部 PASS

---

### 任务 8.4：重构 ProjectManager 使用新服务

**文件：**
- 修改：`core/project_manager.py`

- [ ] **步骤 1：在 ProjectManager 中注入新服务**

在 `__init__` 方法中，添加：

```python
from core.feature_execution_service import FeatureExecutionService
from core.feature_verification_service import FeatureVerificationService
from core.git_service import GitService

# 在 __init__ 末尾添加：
self.feature_execution = FeatureExecutionService(self, self.pool, self.feature_tracker)
self.feature_verification = FeatureVerificationService(self.project_dir)
self.git_service = GitService(self.project_dir)
```

- [ ] **步骤 2：替换 ProjectManager 中的内联 git 调用**

找到所有 `self._git_commit(...)` 和 `self._git_init(...)` 等调用，替换为：

```python
# 原来是 self._git_commit(message)
self.git_service.commit(message)

# 原来是 self._git_init()
self.git_service.init()
```

- [ ] **步骤 3：验证现有功能不受影响**

运行：`pytest tests/ -v`
预期：所有之前通过的测试仍然通过

---

## 自检

**1. 规格覆盖度：**

| Roadmap Phase | 实现任务 | 状态 |
|---|---|---|
| Phase 0: 基线冻结 | 任务 0.1, 0.2 | ✅ |
| Phase 1: 架构契约 | 任务 1.1 | ✅ |
| Phase 2: 工作流协议 | 任务 2.1 | ✅ |
| Phase 3: 统一状态源 | 任务 3.1, 3.2, 3.3, 3.4 | ✅ |
| Phase 4: 阻塞协议 | 任务 4.1 | ✅ |
| Phase 5: 前端状态治理 | 任务 5.1 | ✅ |
| Phase 6: 统一操作入口 | 任务 6.1 | ✅ |
| Phase 7: 任务台账 | 任务 7.1 | ✅ |
| Phase 8: 服务拆分 | 任务 8.1, 8.2, 8.3, 8.4 | ✅ |

**2. 占位符扫描：** 所有步骤包含实际代码或明确命令，无 "TODO"/"待定"/"类似任务N"。

**3. 类型一致性：**
- `BlockingIssue` 在 models.py 定义，在 state_repository.py 和 blocking_tracker.py 中一致使用
- `Feature` 模型扩展保持向后兼容（新增字段有默认值）
- 所有 Service 类使用一致的 constructor 参数模式

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-04-21-auto-coding-refactoring.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？
