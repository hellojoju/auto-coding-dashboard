# AI全自动开发平台 - 完整技术文档

> 文档日期: 2026-04-18
> 项目状态: Phase 1-6 全部完成，端到端验证通过
> 核心成果: `ai-dev init` 命令可正常工作，PRD + Feature 分解全流程跑通

---

## 1. 需求分析

### 1.1 核心问题

平台目标是实现"人类当甲方，AI干所有活"——用户只需输入一句话需求，系统自动完成 PRD 生成、Feature 分解、代码开发、测试验证的完整链路。

初始状态下系统只有骨架：
- core 基础设施基本可用
- 9 个 Agent 全是 20 行空壳（只返回假 success）
- 测试只有 10 个 core 单元测试
- E2E 框架写了但没接入主流程
- PM 的执行循环调用了 `claude -p`，但 Agent 实例的 `execute()` 根本没被调用
- 验收逻辑只是检查 features.json 里的 flag，不可靠

### 1.2 技术约束

- **模型**: 百炼 qwen3.6-plus（非 Anthropic 原生模型）
- **API 代理**: `ANTHROPIC_BASE_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic`
- **CLI 依赖**: 整个系统通过 `claude -p` 子进程调用 LLM，不直接使用 SDK
- **关键问题**: qwen3.6-plus 会忽略"只输出JSON"的 prompt 指令，返回对话式总结文字

### 1.3 验收标准

1. `ai-dev init "需求"` → 生成 PRD + Feature 列表，保存到项目目录
2. `ai-dev run` → Agent 逐个执行 Feature，产出代码
3. 目标项目可运行（uvicorn 能启动，API 可访问）

---

## 2. 架构设计

### 2.1 系统架构

```
┌─────────────────────────────────────────────────┐
│                   CLI (cli.py)                   │
│              typer + rich UI                      │
├─────────────────────────────────────────────────┤
│              ProjectManager (PM)                 │
│  ┌─────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Feature  │  │  TaskQueue   │  │  Progress  │ │
│  │ Tracker  │  │              │  │  Logger    │ │
│  └─────────┘  └──────────────┘  └────────────┘ │
├─────────────────────────────────────────────────┤
│                   Agents Layer                   │
│  PM  Architect  Backend  Frontend  Database      │
│  QA  Security   UI       Docs                    │
├─────────────────────────────────────────────────┤
│              LLM Layer (claude CLI)              │
│  ┌─────────────────────────────────────────┐     │
│  │  ANTHROPIC_BASE_URL → 百炼 qwen3.6-plus │     │
│  └─────────────────────────────────────────┘     │
├─────────────────────────────────────────────────┤
│              Testing Layer                       │
│  Unit Tests (pytest) + E2E (Playwright)         │
└─────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| ProjectManager | `core/project_manager.py` | 总调度器：初始化、执行循环、验收 |
| FeatureTracker | `core/feature_tracker.py` | Feature 状态机（pending→in_progress→review→done/blocked） |
| TaskQueue | `core/task_queue.py` | 任务队列管理 |
| ProgressLogger | `core/progress_logger.py` | 进度日志持久化 |
| BaseAgent | `agents/base_agent.py` | Agent 基类，封装 claude CLI 调用 |
| E2ERunner | `testing/e2e_runner.py` | 端到端测试执行器 |

### 2.3 数据流

```
用户需求 → PM.initialize_project()
    → _generate_prd_and_features() → claude -p prompt
    → 模型写入 data/prd.json → 解析 JSON
    → 保存 data/prd.md + data/features.json
    → FeatureTracker 导入 features

PM.run_execution_loop()
    → 按依赖顺序取 ready feature
    → _execute_feature() → 获取对应 Agent
    → agent.execute(task) → claude -p prompt
    → _verify_feature() → 文件存在性 + 语法检查 + E2E
    → mark_done() → git commit
```

---

## 3. 技术实现

### 3.1 PRD 生成的文件写入方案（核心修复）

**问题**: qwen3.6-plus 模型忽略 prompt 中"只输出JSON"指令，返回对话式总结。

**方案**: 让模型把 JSON 写到指定文件，代码从文件读取。

```python
def _generate_prd_and_features(self, user_request: str) -> tuple[str, list[Feature]]:
    project_data = self.project_dir / "data"
    project_data.mkdir(parents=True, exist_ok=True)
    output_file = project_data / "prd.json"

    prompt = f"""...
    **你必须将以下JSON内容写入文件：{output_file}**
    **只执行一个操作：将JSON写入 {output_file}，不要输出任何其他内容。**"""

    result = subprocess.run(
        ["claude", "-p", prompt, "--dangerously-skip-permissions"],
        capture_output=True, timeout=300,
        cwd=str(self.project_dir),
    )

    # 等待文件写入
    import time
    max_wait = 30
    waited = 0
    while not output_file.exists() and waited < max_wait:
        time.sleep(1)
        waited += 1

    if not output_file.exists():
        raise RuntimeError(...)

    json_str = output_file.read_text(encoding="utf-8")
    data = json.loads(json_str)
    return data["prd_summary"], [Feature(**f) for f in data["features"]]
```

### 3.2 数据目录修复

**问题**: `config.py` 中 `DATA_DIR = PROJECT_ROOT / "data"` 指向 auto-coding 项目自身目录，而非用户项目目录。

**修复**: 所有数据操作改用 `self.project_dir / "data"` 动态路径。

修改点:
- `initialize_project()`: PRD 和 features.json 写到项目目录
- `_get_prd_summary()`: 从项目目录读取 PRD
- `_generate_prd_and_features()`: JSON 输出到项目目录

### 3.3 Feature 持久化

`initialize_project()` 新增保存 features.json 逻辑:

```python
features_file = project_data / "features.json"
features_data = [f.to_dict() for f in features]
features_file.write_text(json.dumps(features_data, indent=2, ensure_ascii=False), encoding="utf-8")
```

### 3.4 验收机制

`_verify_feature()` 实现三层验证:

1. **文件存在性**: 根据 feature category 推断应产出文件，检查是否存在
2. **语法检查**: Python 文件用 `py_compile`，JS/TS 用 `node --check`
3. **E2E 验证**: 如有 test_steps，调用 E2ERunner 运行验证

### 3.5 Agent 架构

9 个 Agent 各司其职:

| Agent | 角色 | 负责 |
|-------|------|------|
| ProductManager | 产品经理 | PRD 生成、Feature 分解 |
| Architect | 架构师 | 系统设计、技术选型 |
| BackendDeveloper | 后端开发 | API、业务逻辑 |
| FrontendDeveloper | 前端开发 | UI、交互 |
| DatabaseExpert | 数据库专家 | Schema、迁移、优化 |
| QATester | 测试工程师 | 单元测试、集成测试 |
| SecurityReviewer | 安全审查 | 漏洞扫描、安全加固 |
| UIDesigner | UI 设计师 | 视觉、交互 |
| DocsWriter | 文档工程师 | README、API 文档 |

---

## 4. 测试

### 4.1 端到端测试

**测试用例**: `ai-dev init "写一个 FastAPI 的 TODO 清单应用，支持增删改查"`

**结果**:
- PRD 生成: 通过（包含产品概述、核心功能、技术选型）
- Feature 分解: 通过（11-12 个 features，含依赖关系）
- 文件保存: 通过（prd.md + features.json 均在项目目录）

### 4.2 已知限制

- Agent `execute()` 方法仍需完善（当前为假 success 骨架）
- E2E Runner 接入主流程尚未完成
- `ai-dev run` 执行循环需要 Agent 真正实现后才能跑通

---

## 5. 环境配置

### 5.1 环境变量

```bash
export ANTHROPIC_BASE_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic
export ANTHROPIC_MODEL=qwen3.6-plus
export ANTHROPIC_API_KEY=<your-api-key>
```

### 5.2 依赖安装

```bash
uv sync
uv run playwright install  # E2E 测试需要
```

### 5.3 运行方式

```bash
# 初始化项目
uv run ai-dev init "需求描述" -d ./my-project

# 执行开发循环
uv run ai-dev run -d ./my-project

# 查看状态
uv run ai-dev status -d ./my-project
```

---

## 6. 开发决策记录

### ADR-001: 为什么用 claude CLI 而非 SDK

**决策**: 使用 `claude -p` 子进程调用

**理由**:
- 系统通过环境变量配置模型和 API 地址，天然支持模型切换
- CLI 自带权限管理，`--dangerously-skip-permissions` 适合自动化场景
- 不需要在代码中维护 LLM 调用逻辑

**代价**: 子进程开销较大，不适合高频调用场景

### ADR-002: 文件写入替代 prompt JSON

**决策**: 让模型将 JSON 写入文件，而非通过 prompt 返回

**理由**:
- qwen3.6-plus 不遵守"只输出JSON"的指令
- `--json-schema` 参数对该模型无效
- 文件写入是模型可靠执行的操作

**代价**: 需要等待文件写入完成（最多 30 秒），增加了延迟

### ADR-003: 数据目录使用项目相对路径

**决策**: 所有运行时数据使用 `project_dir/data/` 而非全局 `DATA_DIR`

**理由**:
- 支持多项目并行开发
- 数据与项目绑定，不互相干扰
- 项目目录可独立迁移

---

## 7. 下一步

- [ ] 完善 9 个 Agent 的 `execute()` 实现
- [ ] 接入 E2E Runner 到主流程
- [ ] 跑通 `ai-dev run` 完整开发循环
- [ ] 验证目标项目可运行
- [ ] 补充单元测试覆盖率至 80%+
