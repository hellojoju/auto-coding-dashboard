# Ralph Orchestrator 二期架构方案

版本：v2.0 草案
日期：2026-05-02
文档语言：中文
依赖文档：

```text
Ralph docs/auto-coding-ralph-orchestrator-prd.zh.md
Ralph docs/auto-coding-ralph-orchestrator-ai-protocol.zh.md
Ralph docs/auto-coding-ralph-orchestrator-implementation-plan.zh.md
Ralph docs/auto-coding-ralph-orchestrator-mvp-checklist.zh.md
Ralph docs/auto-coding-ralph-orchestrator-reference-map.zh.md
```

---

## 1. 二期定位

一期目标是**可靠顺序执行**：需求清楚、任务够细、上下文隔离、权限可控、验收有证据。

二期目标是**可持续的自动化推进**：

```text
系统能在数小时甚至数天的周期内持续自主推进，
不需要人类频繁介入，
不会因为 context 爆炸而失忆、变粗或跑偏，
遇到不确定时知道该问谁、查什么、怎么恢复。
```

一句话：**从"能跑通一个任务"升级到"能跑通一个项目"。**

### 1.1 二期不做的事

1. 不做完全无人值守（保留人工兜底能力）。
2. 不做分布式多机部署（还是本地/单节点）。
3. 不替换一期的状态机、harness、review 体系（在之上增强）。
4. 不引入重型数据库（保持文件系统为主、轻量索引为辅）。

---

## 2. 从 Symphony 学到的（以及故意不学的）

| Symphony 设计 | Ralph 二期态度 | 原因 |
|--------------|---------------|------|
| **Issue-tracker-native 控制平面** | **全盘吸收** | 看板即队列是最自然的交互方式 |
| **多轮 Continuation（TurnComplete→ContinuationCheck）** | **全盘吸收** | 解决 context 超限和长时间任务的核心手段 |
| **物理隔离 workspace（独立目录+clone）** | **吸收并改进** | 用 git worktree 实现，比 scope_allow 更彻底 |
| **Proof of Work 证据包** | **吸收并增强** | Ralph 已有 EvidenceCollector，二期扩展维度 |
| **并发限制（max_concurrent_agents）** | **吸收** | 一期缺失，必须补 |
| **WORKFLOW.md 项目级配置** | **吸收** | 把分散的默认值收敛到单文件 |
| **Agent 角色专业化（Planner/Coder/Tester/Reviewer）** | **选择性吸收** | 通过 ToolAdapter + ModelAssignment 实现，不强绑定固定角色 |
| **全自动无人值守（人工只在最终 PoW 介入）** | **不学** | 我们的优势是任意阶段可介入，这是护城河 |
| **Elixir/OTP 运行时** | **不学** | Python 生态足够，用进程池+状态持久化实现等价容错 |
| **锁定 OpenAI/Codex** | **不学** | ToolAdapter + LLMProvider 已经支持多工具多模型 |

---

## 3. 核心架构升级

### 3.1 Context 分层与记忆系统（二期重中之重）

一期的问题：PM Agent（调度 agent）需要掌握项目全局状态、历史决策、当前进度、所有子 agent 产出，context 随项目推进线性膨胀，最终必然超限。

二期的解法：**四层 context 模型 + 三层记忆系统**。

#### 3.1.1 Context 四层模型

| 层级 | 名称 | 内容 | 大小控制 | 加载策略 |
|------|------|------|---------|---------|
| **L0** | 指令层（Instruction） | 系统角色定义、调度规则、安全策略、状态机协议 | <1k tokens | **永远加载**，硬编码在 prompt 中 |
| **L1** | 状态层（State） | 当前项目状态快照：活跃任务列表、阻塞项、最近决策 | <2k tokens | **每次加载**，由 MemoryManager 动态生成 |
| **L2** | 工作层（Working） | 当前正在处理的具体任务上下文（work unit、context pack、harness） | <5k tokens | **按需加载**，调度时才注入 |
| **L3** | 知识层（Knowledge） | 历史任务详情、代码库分析、决策日志、执行日志 | 无上限 | **不常驻**，通过 RAG 按需检索 |

**核心原则**：PM Agent 启动时只加载 L0 + L1（约 3k tokens），L2 在需要调度具体任务时注入，L3 永远不走 prompt，只走 RAG。

#### 3.1.2 记忆三层系统

```text
Ephemeral Memory（瞬态记忆）
  └── 单次 Agent 调用内的上下文
  └── 调用结束即丢弃

Short-term Memory（短期记忆）
  └── 最近 N 个已完成/失败任务的摘要（默认 N=10）
  └── 存储：.ralph/memory/short_term.json
  └── 由 MemoryManager 自动维护，旧任务自动归档到中期记忆

Medium-term Memory（中期记忆）
  └── 当前项目周期内的关键决策、冻结合同、活跃 PRD 摘要、重要风险
  └── 存储：.ralph/memory/medium_term.json
  └── 人工标记或自动识别的重要节点

Long-term Memory（长期记忆）
  └── 完整的执行日志、对话记录、代码库知识图谱
  └── 存储：
      - .ralph/memory/long_term/（执行日志、决策记录）
      - .ralph/graphify/graph.json（代码/文档知识图谱，由 graphify 维护）
      - .ralph/knowledge_graph/（任务级业务图谱，由 KnowledgeGraphService 维护）
  └── 通过 RAG 检索，不直接加载到 prompt
  └── 代码库变更时自动触发 graphify --update 增量更新
```

#### 3.1.3 记忆压缩策略

**任务级压缩（Task Compaction）**：

当一个 WorkUnit 进入 `accepted` 或 `failed` 终态时，MemoryManager 自动调用 `compaction_agent` 将其完整日志压缩成结构化摘要：

```json
{
  "work_id": "wu-xxx",
  "summary": "实现了用户登录接口，包括 JWT 签发和校验",
  "status": "accepted",
  "key_decisions": ["使用 bcrypt 而非 md5", "token 有效期设为 24h"],
  "files_changed": ["src/auth/login.ts", "src/middleware/jwt.ts"],
  "interfaces_modified": ["POST /api/login", "GET /api/me"],
  "risks_introduced": ["jwt secret 需要轮换机制"],
  "downstream_impact": ["用户注册接口需要同步调整错误码"],
  "evidence_refs": [".ralph/evidence/wu-xxx/test.log"],
  "detailed_log": ".ralph/logs/wu-xxx-full.md"
}
```

这个摘要进入短期记忆。完整日志进长期记忆，但**完整会话日志永远不可压缩**——它是审计和调试的底线数据。

**不可压缩数据清单**：
```text
1. 调度智能体与子 Agent 之间的完整对话记录（.ralph/sessions/）
   - 包含每轮输入输出、tool call、错误信息
   - 用于事后复盘、故障定位、质量审计
   - 即使任务进入终态，也不能被 compaction 删除或修改

2. 执行证据（.ralph/evidence/）
   - 测试输出、截图、trace、diff
   - 这些是"事实"，不是"记忆"

3. 决策日志（.ralph/decisions/）
   - 每个关键决策的完整上下文和理由
   - 用于追溯决策链
```

PM Agent 调度时只读摘要，不读完整日志。需要详情或排查问题时，才检索完整会话。

**Context Pack 压缩（Context Compaction）**：

当一个任务需要多轮 continuation 时，每轮结束后 `ContextPackManager` 对上下文进行增量压缩：

```
Turn 1: 完整 context pack（~5k tokens）
Turn 2: 增量 context（"上一轮完成了 X，当前错误是 Y，需要继续 Z"）+ 关键文件快照
Turn 3+: 只传变更 diff + 当前错误 + 下一步目标
```

**graphify 增量更新**：

任务执行产生新代码或新文档后，自动触发 `graphify --update`：
- 只提取新增/变更文件，合并到已有图谱
- 新产生的 `DecisionNode`、`RiskNode` 同时写入 `KnowledgeGraphService`
- 查询结果（如"修改 X 会影响什么"）保存回 `.ralph/graphify/memory/`，下次更新时吸收进图谱，形成**记忆复利**

### 3.2 PM Agent 空记忆调度模式

这是二期最关键的行为模式改变。

#### 3.2.1 传统模式的问题

```text
PM Agent 加载：
  - 全部项目历史（10k tokens）
  - 全部活跃任务（5k tokens）
  - 全部阻塞项（2k tokens）
  - 全部合同和 PRD（8k tokens）
  = 25k tokens，超限、失忆、变粗
```

#### 3.2.2 空记忆调度模式

```text
PM Agent 启动：
  1. 加载 L0 指令层（系统角色+规则）
  2. 加载 L1 状态层（由 MemoryManager 生成的当前快照）
  3. 不加载任何历史任务详情
  4. 不加载任何已完成任务的日志

PM Agent 决策流程：
  1. 根据 L1 状态层决定"下一步该做什么"
  2. 如果需要历史信息，调用 RetrievalTool 查询 RAG/知识图谱
  3. 如果需要具体任务执行，创建 WorkUnit 并调度子 Agent
  4. 子 Agent 返回结构化结果（不是自然语言总结）
  5. PM Agent 读取结果摘要，更新状态层，结束本次调度
  6. 如果状态有变，可能触发下一轮调度（continuation）
```

#### 3.2.3 子 Agent 返回协议（结构化替代自然语言）

子 Agent 完成任务后，不返回长文本总结，而是返回结构化结果：

```json
{
  "work_id": "wu-xxx",
  "turn_id": 3,
  "result_type": "code_change|investigation|review|report|continuation",
  "status": "completed|failed|blocked|needs_continuation",
  "key_findings": [
    "实现了 JWT 登录接口",
    "发现 refresh token 机制缺失"
  ],
  "files_changed": [
    {"path": "src/auth/login.ts", "change_type": "created", "lines": 45}
  ],
  "decisions_made": [
    {"decision": "使用 bcrypt", "reason": "安全性要求", "alternatives_rejected": ["md5", "sha256"]}
  ],
  "risks_observed": [
    {"risk": "secret 硬编码", "severity": "high", "suggested_action": "移入环境变量"}
  ],
  "next_actions_suggested": [
    {"action": "创建 refresh token 机制", "priority": "high", "estimated_effort": "2h"}
  ],
  "continuation_context": {
    "current_progress": "登录接口主体完成，缺少 refresh token",
    "remaining_work": ["实现 refresh token", "添加 token 过期处理"],
    "checkpoint_state": {"last_file": "src/auth/login.ts", "last_test_status": "passed"}
  },
  "detailed_log_ref": ".ralph/logs/wu-xxx-turn-3.md",
  "token_usage": {"input": 3200, "output": 1800}
}
```

PM Agent 只读取 `key_findings`、`next_actions_suggested` 和 `continuation_context`（约 500 tokens），需要详情时才查 `detailed_log_ref`。

### 3.3 多轮 Continuation 执行模型

一期 `WorkUnitEngine.execute()` 是一次性调用，复杂任务容易因 context window 超限或超时失败。二期引入 Turn-based 执行模型。

#### 3.3.1 Turn 生命周期

```
WorkUnit 进入 running
  → Turn 1: 加载完整 context pack + task harness
  → Agent 执行（最多 1 个"推理轮次"，如：分析→修改→测试）
  → TurnComplete: 保存 checkpoint（文件状态、测试结果、当前进度）
  → ContinuationCheck: 检查是否还有剩余工作
      ├── 已完成 → 进入 needs_review
      ├── 需要继续 → 生成增量 context pack → Turn 2
      ├── 失败 → 进入 failed
      └── 阻塞 → 进入 blocked
```

#### 3.3.2 Checkpoint 设计

```json
{
  "checkpoint_id": "cp-wu-xxx-t3",
  "work_id": "wu-xxx",
  "turn_number": 3,
  "timestamp": "2026-05-02T10:30:00Z",
  "file_state_snapshot": {
    "src/auth/login.ts": "sha256:abc123...",
    "src/auth/jwt.ts": "sha256:def456..."
  },
  "test_status": {"unit_tests": "passed", "integration_tests": "pending"},
  "current_progress": "登录接口主体实现完成",
  "remaining_tasks": ["实现 refresh token", "添加错误码映射"],
  "context_summary": "已完成的修改和当前待解决问题摘要",
  "agent_session_id": "sess-xyz-789",
  "token_usage_cumulative": {"input": 9500, "output": 4200}
}
```

#### 3.3.3 增量 Context Pack 生成

Turn N+1 的 context pack 不是从头构建，而是基于 checkpoint 生成增量包：

```
增量 Context Pack = {
  "task_goal": "继续完成剩余工作：实现 refresh token",
  "completed_so_far": ["登录接口主体", "JWT 签发"],  # 来自 checkpoint
  "current_error_or_gap": "refresh token 机制缺失",
  "relevant_files": ["src/auth/login.ts"],  # 只包含需要继续修改的文件
  "full_context_ref": ".ralph/context_packs/wu-xxx-turn-1-full.md",  # 需要时去查
  "trust_level": "high"  # 因为是 continuation，可以信任之前的结果
}
```

### 3.4 双层知识图谱

二期的知识系统分为两层：**graphify 负责代码/文档级静态图谱**，**KnowledgeGraphService 负责任务级业务动态图谱**。两者互补，通过 `FileNode` 做映射关联。

#### 3.4.1 graphify 层（代码/文档知识图谱）

graphify 是 Ralph 长期记忆的**基础设施**，负责把代码库和文档库变成可查询的持久化图谱。

**graphify 提取的内容**：
- AST 关系：`imports`、`calls`、`extends`、`implements`
- 语义关系：`shared_data_with`、`conceptually_related_to`、`rationale_for`
- 社区检测：自动发现跨文件的隐性关联模块
- 置信度审计：EXTRACTED / INFERRED / AMBIGUOUS 三级标签

**graphify 的存储**：
```text
.ralph/graphify/
  graph.json              # 完整图谱（NetworkX node-link 格式）
  GRAPH_REPORT.md         # 审计报告（god nodes、surprising connections）
  memory/                 # 查询结果回填（记忆复利）
```

**graphify 的更新策略**：
- 项目初始化时：`/graphify <project_dir> --mode deep`
- 每次执行后：`/graphify <project_dir> --update`（只处理变更文件）
- 代码文件变更（如 agent 批量修改）：`--watch` 自动触发 AST 级重建（无 LLM 成本）

#### 3.4.2 KnowledgeGraphService 层（任务级业务图谱）

Ralph 自建的业务领域图谱，表达**调度语义**：任务依赖、文件修改影响、风险关联、阻塞关系。

**节点类型**：
```text
TaskNode:        work unit 的抽象
FileNode:        代码文件（与 graphify 的节点 ID 映射）
InterfaceNode:   API 接口、函数签名
DecisionNode:    架构决策、ADR
RiskNode:        识别的风险
BlockerNode:     阻塞项
MilestoneNode:   里程碑/阶段
```

**边类型**：
```text
depends_on:      TaskNode → TaskNode
modifies:        TaskNode → FileNode
implements:      TaskNode → InterfaceNode
requires:        InterfaceNode → InterfaceNode
introduced_by:   RiskNode → TaskNode
blocks:          BlockerNode → TaskNode
supersedes:      DecisionNode → DecisionNode
part_of:         TaskNode → MilestoneNode
```

**存储方案**：
```text
.ralph/knowledge_graph/
  nodes.jsonl       # 每行一个节点
  edges.jsonl       # 每行一条边
  index.json        # 快速查找索引
```

#### 3.4.3 两层映射关系

```text
KnowledgeGraphService.FileNode "src/auth/login.ts"
  └── 映射到 graphify 节点 "login_auth"（通过 source_file 字段匹配）
  └── graphify 提供：谁调用了这个文件、它依赖哪些模块、属于哪个社区
  └── KnowledgeGraphService 提供：哪些 TaskNode 修改过它、它被哪些接口依赖
```

#### 3.4.4 典型查询场景

```text
Q: "修改 src/auth/login.ts 会影响哪些任务？"
A: 
  1. KnowledgeGraphService 查询 modifies 边反向遍历 → 关联 TaskNode
  2. graphify 查询该文件的调用关系 → 关联的其他文件
  3. KnowledgeGraphService 再查这些文件被哪些 TaskNode 修改 → 完整影响面

Q: "之前为什么做决策 X？"
A: 
  1. KnowledgeGraphService 找到 DecisionNode
  2. graphify 检索相关文档中的 rationale_for 边
  3. 合并返回决策理由、引用来源、替代方案

Q: "当前有哪些阻塞项阻挡了 milestone 'v1.0 登录功能'？"
A: KnowledgeGraphService 查询 part_of + blocks 边联合遍历

### 3.5 RAG 增强检索系统

#### 3.5.1 语料库构成

```text
结构化语料（高置信度）：
  - .ralph/work_units/*.json
  - .ralph/reviews/*.json
  - .ralph/evidence/*.json
  - .ralph/decisions/*.md
  - .ralph/specs/current/*.md

半结构化语料（中置信度）：
  - .ralph/logs/*.md（执行日志）
  - .ralph/brainstorm/*.md
  - .ralph/reports/*.md

图谱语料（结构+语义混合）：
  - .ralph/graphify/graph.json（代码级节点/边/社区）
  - .ralph/knowledge_graph/*.jsonl（任务级节点/边）
  - .ralph/graphify/memory/（查询结果回填）

外部语料（低置信度，需标注来源）：
  - 拉取的官方文档
  - 代码库中的 README、注释
```

#### 3.5.2 三层检索策略

```text
L1 结构化索引（最快，覆盖 80%）：
  - 按 work_id、file_path、decision_id 建立倒排索引
  - 按时间戳、状态、类型建立二级索引
  - 存储：.ralph/memory/index.json

L2 图谱检索（结构化关联）：
  - graphify MCP 查询：代码调用关系、模块社区、隐性关联
  - KnowledgeGraphService 遍历：任务依赖、影响面、关键路径
  - 存储：graph.json + nodes/edges.jsonl

L3 语义检索（可选，覆盖长尾）：
  - 对非结构化日志和报告做 embedding
  - 轻量级本地向量库（如 faiss）或关键词+BM25
  - 仅在 L1/L2 未命中时启用
```

#### 3.5.3 graphify MCP 查询接口

graphify 通过 MCP server 暴露查询能力，Ralph 的 `RetrievalPipeline` 将其作为 L2 检索的主要路径：

```python
# 配置在 task_harness 中
mcp_servers:
  - name: graphify
    command: python3 -m graphify.serve .ralph/graphify/graph.json

# PM Agent 查询示例
result = mcp_client.call("query_graph", {
    "question": "What depends on src/auth/login.ts?",
    "mode": "bfs",           # bfs=广度优先（影响面）, dfs=深度优先（调用链）
    "budget": 1500           # token budget 控制
})
# 返回：关联节点列表、关系类型、置信度、source_location
```

graphify 支持的查询工具：
- `query_graph`: BFS/DFS 遍历
- `get_node`: 单个节点详情
- `get_neighbors`: 邻居节点
- `get_community`: 社区成员
- `shortest_path`: 两节点最短路径
- `god_nodes`: 高连接度节点（关键枢纽）

#### 3.5.4 检索接口

```python
class RetrievalPipeline:
    def retrieve(
        self,
        query: str,
        context: QueryContext,
        filters: RetrievalFilters,
        top_k: int = 5,
    ) -> List[RetrievalResult]:
        """
        三层检索，按优先级融合：
        1. 结构化索引（work_units、decisions、evidence）
        2. 图谱检索（graphify MCP + KnowledgeGraphService）
        3. 语义检索（可选 embedding/BM25）
        """
```

典型调用场景：

```python
# PM Agent 需要判断"修改文件 A 是否安全"
results = retrieval.retrieve(
    query="修改 src/auth/login.ts 会影响什么？",
    context=QueryContext(current_work_id="wu-xxx"),
    filters=RetrievalFilters(types=["task", "risk", "code"], min_confidence=0.7)
)
# 返回：
#   - 结构化：哪些 WorkUnit 修改过这个文件（KnowledgeGraphService）
#   - 图谱级：哪些代码调用了这个文件（graphify MCP）
#   - 风险：相关 DecisionNode、RiskNode（KnowledgeGraphService）
```

---

## 4. 子系统详细设计

### 4.1 MemoryManager（新增）

职责：
1. 维护短期记忆和中期记忆文件。
2. 在任务终态时自动触发 compaction，生成摘要。
3. 为 PM Agent 生成 L1 状态层快照。
4. 管理记忆的淘汰和升级（短期→中期→长期）。

```python
class MemoryManager:
    def __init__(self, ralph_dir: Path):
        self.short_term = ShortTermMemory(ralph_dir / "memory" / "short_term.json")
        self.medium_term = MediumTermMemory(ralph_dir / "memory" / "medium_term.json")
        self.long_term = LongTermMemory(ralph_dir / "memory" / "long_term")

    def on_work_unit_terminal(self, work_unit: WorkUnit) -> None:
        """任务进入终态时自动压缩"""
        summary = self.compaction_agent.summarize(work_unit)
        self.short_term.add(summary)
        if self.short_term.is_full():
            self._archive_oldest_to_medium()

    def get_state_snapshot(self) -> StateSnapshot:
        """生成 PM Agent 的 L1 状态层"""
        return StateSnapshot(
            active_work_units=self._get_active(),
            recent_summaries=self.short_term.get_recent(n=10),
            blockers=self._get_active_blockers(),
            key_decisions=self.medium_term.get_decisions(),
        )

    def retrieve(self, query: str, depth: str = "short") -> List[MemoryFragment]:
        """按深度检索记忆"""
        if depth == "short":
            return self.short_term.search(query)
        elif depth == "medium":
            return self.medium_term.search(query)
        else:
            return self.long_term.search(query)  # 走 RAG
```

### 4.2 ContextEngine（重构 ContextPackManager）

一期 ContextPackManager 负责组装最小上下文包。二期增强：

1. **支持增量 context pack 生成**（continuation 场景）。
2. **支持 L0/L1/L2 分层注入**。
3. **集成 RetrievalEngine**，在需要时自动补充 L3 知识层片段。

```python
class ContextEngine:
    def build_initial(self, work_unit: WorkUnit, prd_fragment: str) -> ContextPack:
        """首次执行的完整 context pack（L2）"""

    def build_continuation(
        self,
        work_unit: WorkUnit,
        checkpoint: Checkpoint,
        turn_number: int,
    ) -> ContextPack:
        """基于 checkpoint 的增量 context pack"""

    def build_pm_context(
        self,
        mode: str = "schedule",  # "schedule" | "decision" | "investigate"
    ) -> PMContext:
        """为 PM Agent 生成 L0 + L1 + 按需 L2/L3"""
```

### 4.3 TurnBasedExecutionEngine（重构 WorkUnitEngine）

在一期 `WorkUnitEngine` 基础上增加 turn 管理能力：

```python
class TurnBasedExecutionEngine(WorkUnitEngine):
    def __init__(self, ...):
        super().__init__(...)
        self.turn_manager = TurnManager()
        self.checkpoint_store = CheckpointStore()

    async def execute(
        self,
        work_id: str,
        max_turns: int = 20,
        **kwargs
    ) -> ExecutionResult:
        unit = self._repository.get_work_unit(work_id)
        turn = 1

        while turn <= max_turns:
            # ready → running
            if turn == 1:
                context_pack = self._context_engine.build_initial(unit, ...)
            else:
                checkpoint = self.checkpoint_store.get_last(work_id)
                context_pack = self._context_engine.build_continuation(unit, checkpoint, turn)

            # 执行当前 turn
            exec_result = self._execute_turn(unit, context_pack, turn)

            # 保存 checkpoint
            checkpoint = self._create_checkpoint(work_id, turn, exec_result)
            self.checkpoint_store.save(checkpoint)

            # ContinuationCheck：判断是否继续
            continuation = self._check_continuation(exec_result, turn, max_turns)

            if continuation.status == "completed":
                return self._finalize_success(work_id, exec_result)
            elif continuation.status == "failed":
                return self._finalize_failure(work_id, exec_result, continuation.reason)
            elif continuation.status == "blocked":
                return self._finalize_blocked(work_id, exec_result, continuation.reason)
            elif continuation.status == "continue":
                turn += 1
                continue

        # 超过 max_turns
        return self._finalize_blocked(work_id, None, f"超过最大轮次限制 ({max_turns})")
```

### 4.4 KnowledgeGraphService（新增）

Ralph 自建的业务领域图谱，与 graphify 互补。

```python
class KnowledgeGraphService:
    def __init__(self, graph_dir: Path):
        self.graph = PropertyGraph()
        self.graphify_mcp = GraphifyMCPClient()  # graphify MCP 查询客户端

    def index_work_unit(self, work_unit: WorkUnit) -> None:
        """把 work unit 及其关系编入业务图谱"""
        self.graph.add_node(TaskNode(work_unit.work_id, ...))
        for f in work_unit.files_changed:
            self.graph.add_edge(work_unit.work_id, f, "modifies")
        for dep in work_unit.dependencies:
            self.graph.add_edge(work_unit.work_id, dep, "depends_on")

    def query_impact(self, file_path: str) -> ImpactResult:
        """
        查询修改某文件的影响面。
        联合 KnowledgeGraphService（任务级）和 graphify（代码级）。
        """
        # 第一层：哪些任务直接修改过这个文件
        direct_tasks = self.graph.traverse(file_path, edge_type="modifies", direction="reverse")

        # 第二层：graphify 查询哪些代码调用/依赖这个文件
        code_neighbors = self.graphify_mcp.query(
            question=f"What depends on {file_path}?",
            mode="bfs", budget=1500
        )

        # 第三层：这些代码文件又被哪些任务修改
        indirect_tasks = []
        for node in code_neighbors.nodes:
            if node.type == "file":
                tasks = self.graph.traverse(node.source_file, edge_type="modifies", direction="reverse")
                indirect_tasks.extend(tasks)

        return ImpactResult(direct=direct_tasks, indirect=indirect_tasks, code_relations=code_neighbors)

    def sync_with_graphify(self) -> None:
        """
        同步映射：确保 KnowledgeGraphService 的 FileNode 与 graphify 节点对齐。
        定期运行（如每次 --update 后）。
        """
        for file_node in self.graph.nodes_by_type("FileNode"):
            graphify_node = self.graphify_mcp.get_node_by_source(file_node.path)
            if graphify_node:
                file_node.graphify_id = graphify_node.id
```

### 4.5 RetrievalPipeline（新增）

```python
class RetrievalPipeline:
    def __init__(self):
        self.structured_retriever = StructuredRetriever()     # L1: JSON/YAML 检索
        self.graphify_retriever = GraphifyMCPRetriever()       # L2: graphify MCP 查询
        self.kg_retriever = KnowledgeGraphRetriever()          # L2: 任务级图谱遍历
        self.semantic_retriever = Optional[SemanticRetriever]  # L3: 可选语义检索

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        # L1: 结构化索引（最快）
        structured_results = self.structured_retriever.search(query)

        # L2: 并行图谱检索
        graphify_results = self.graphify_retriever.search(query)  # 代码级关系
        kg_results = self.kg_retriever.search(query)              # 任务级关系

        # L1 + L2 融合排序
        merged = self._fusion_rank(structured_results, graphify_results, kg_results)

        # L3: 语义检索兜底（可选）
        if self.semantic_retriever and len(merged) < query.top_k:
            semantic_results = self.semantic_retriever.search(query)
            merged = self._re_rank_with_semantic(merged, semantic_results)

        return RetrievalResult(items=merged[:query.top_k])
```

**graphify 查询结果回填**：

每次通过 graphify MCP 查询后，结果自动保存到 `.ralph/graphify/memory/`：

```python
save_query_result(
    question="What depends on src/auth/login.ts?",
    answer="...",
    memory_dir=Path(".ralph/graphify/memory"),
    query_type="query",
    source_nodes=["login_auth", "jwt_handler"],
)
```

下次 `/graphify --update` 时，这些 Q&A 会被提取为新节点编入图谱，形成**记忆复利**——越查越准。

### 4.6 Issue-Tracker-Native 控制平面升级

在一期 Issue Governance 基础上，把 Issue Tracker 从"信息源"升级为"控制平面"：

```text
GitHub Issues / Linear
  ├── 作为输入队列：新 issue → Ralph 自动拉取分类
  ├── 作为状态面板：Ralph 状态变化 → 自动同步回 issue（label、comment、状态）
  ├── 作为命令入口：issue comment 中的 /ralph 命令 → 生成 Command
  └── 作为输出渠道：work unit 完成 → 自动关联 PR、关闭 issue
```

新增双向同步协议：

```python
class IssueSyncProtocol:
    def on_ralph_status_change(self, work_unit: WorkUnit) -> None:
        """Ralph 状态变化时同步回 issue tracker"""
        if work_unit.status == WorkUnitStatus.RUNNING:
            self.issue_source.add_label(work_unit.issue_id, "ralph/running")
        elif work_unit.status == WorkUnitStatus.NEEDS_REWORK:
            self.issue_source.add_comment(work_unit.issue_id, f"Ralph 审查不通过：{review_summary}")
        elif work_unit.status == WorkUnitStatus.ACCEPTED:
            self.issue_source.add_comment(work_unit.issue_id, f"已完成，关联 PR：{pr_url}")
            self.issue_source.close_issue(work_unit.issue_id)

    def on_issue_comment_command(self, issue_id: str, comment: str) -> Optional[Command]:
        """监听 issue comment 中的命令"""
        if "/ralph retry" in comment:
            return Command(type="retry_work_unit", issue_id=issue_id)
        elif "/ralph approve" in comment:
            return Command(type="accept_review", issue_id=issue_id)
```

### 4.7 并发与隔离强化

#### 4.7.1 并发控制

```python
class ConcurrencyController:
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.token_budget = TokenBudget(daily_limit=1_000_000)

    async def acquire(self, work_unit: WorkUnit) -> bool:
        if not self.token_budget.check(work_unit.estimated_tokens):
            return False  # 进入等待队列
        return await self.semaphore.acquire()
```

#### 4.7.2 物理隔离（git worktree）

```python
class WorkspaceManager:
    def create_isolated_workspace(self, work_id: str) -> Path:
        """为 work unit 创建独立的 git worktree"""
        worktree_path = self.base_dir / work_id
        run_git_command(f"git worktree add {worktree_path} -b ralph/{work_id}")
        return worktree_path

    def merge_back(self, work_id: str) -> MergeResult:
        """执行成功后把变更合并回主工作区"""
        worktree_path = self.base_dir / work_id
        # 生成 patch，应用到主分支
        patch = run_git_command(f"git -C {worktree_path} diff HEAD")
        return self._apply_patch_to_main(patch)
```

---

## 5. 数据流与交互

### 5.1 PM Agent 调度流程（空记忆模式）

```
[启动]
  │
  ▼
[MemoryManager] 生成 L1 状态快照
  │   （活跃任务、最近摘要、阻塞项、关键决策）
  ▼
[PM Agent] 加载 L0（指令） + L1（状态）
  │   （~3k tokens，恒定大小，不随项目膨胀）
  ▼
[PM Agent 决策] "下一步做什么？"
  │
  ├── 需要历史信息？ ──→ [RetrievalEngine] 查询 RAG/知识图谱
  │                         └── 返回 Top-K 片段 → PM Agent
  │
  ├── 创建新任务？ ──→ [TaskDecomposer] 生成 WorkUnit
  │                       └── [WorkUnitEngine] 进入状态机
  │
  ├── 调度执行任务？ ──→ [TurnBasedExecutionEngine] 启动 Turn 1
  │                        └── [ToolAdapter] 调用 Claude Code
  │
  └── 处理返回结果？ ──→ 子 Agent 返回结构化结果
                           ├── 更新状态机
                           ├── [MemoryManager] 触发 compaction
                           ├── [KnowledgeGraphService] 更新图谱
                           └── [IssueSyncProtocol] 同步回 issue tracker
```

### 5.2 多轮 Continuation 数据流

```
[WorkUnit: ready]
  │
  ▼
[Turn 1] ContextEngine.build_initial() → 完整 context pack
  │        └── Agent 执行
  │        └── Checkpoint 保存（完整文件快照）
  │        └── ContinuationCheck: "还有剩余工作"
  │
  ▼
[Turn 2] ContextEngine.build_continuation() → 增量 context pack
  │        └── Agent 从 checkpoint 恢复
  │        └── 只传变更 diff + 当前错误 + 下一步目标
  │        └── Checkpoint 保存
  │        └── ContinuationCheck: "还有剩余工作"
  │
  ▼
[Turn N] ...
  │
  ▼
[ContinuationCheck: "已完成"]
  │
  ▼
[WorkUnit: needs_review]
```

---

## 6. 实施路线图

### 阶段一：基础能力（2-3 周）

目标：让 PM Agent 不再 context 爆炸。

1. **MemoryManager 实现**
   - 短期记忆文件格式和 compaction 逻辑
   - 状态快照生成
2. **ContextEngine 重构**
   - L0/L1/L2 分层注入
   - 增量 context pack 生成
3. **结构化返回协议**
   - 定义 `AgentResult` schema
   - 改造 `ClaudeCodeRunner` 返回结构化数据
4. **PM Agent 空记忆调度**
   - 改造 `CommandConsumer` 或新增 `PMCoordinator`
   - 只加载 L0 + L1

### 阶段二：Continuation 与隔离（2-3 周）

目标：复杂任务可恢复，并发不冲突。

1. **TurnBasedExecutionEngine**
   - Checkpoint 设计和存储
   - ContinuationCheck 逻辑
   - `max_turns` 和 `turn_budget` 控制
2. **WorkspaceManager（git worktree）**
   - 隔离 workspace 创建
   - 生命周期 hooks
   - merge back 策略
3. **并发控制**
   - Semaphore 实现
   - Token budget 监控

### 阶段三：知识系统（3-4 周）

目标：历史可检索，关联可查询。

1. **graphify 初始化与集成**
   - 项目初始化时 `/graphify <project_dir> --mode deep`
   - 配置 MCP server 接入 Ralph
   - 实现 `--update` 触发逻辑（每次执行后自动调用）
2. **KnowledgeGraphService**
   - 节点/边类型定义
   - 文件存储格式
   - 与 graphify 的 FileNode 映射
   - 基础查询（impact、critical path）
3. **RetrievalPipeline**
   - 结构化检索（L1）
   - graphify MCP + KnowledgeGraphService 联合检索（L2）
   - 可选语义检索兜底（L3）
   - 查询结果回填机制
4. **与 MemoryManager 集成**
   - compaction 时自动更新图谱
   - 检索时联动短期记忆和长期记忆

### 阶段四：Issue-Tracker-Native（2 周）

目标：看板即队列。

1. **IssueSyncProtocol**
   - 双向同步实现
   - Issue comment 命令解析
2. **GitHub Issues 适配器增强**
   - Webhook 支持
   - Label 策略映射
3. **Dashboard 增强**
   - 显示 issue 关联状态
   - 支持从 Dashboard 直接操作 issue

---

## 7. 与一期架构的兼容性

### 7.1 向后兼容

| 一期组件 | 二期变化 | 兼容性 |
|---------|---------|--------|
| `WorkUnit` schema | 增加 `turn_history`、`checkpoint_refs` | 兼容，新增可选字段 |
| `task_harness` schema | 增加 `max_turns`、`continuation_policy` | 兼容，新增可选字段 |
| `ContextPackManager` | 重命名为 `ContextEngine`，增加增量生成 | API 变化，调用点需更新 |
| `WorkUnitEngine` | 被 `TurnBasedExecutionEngine` 继承扩展 | 原 API 保留，新增 `execute_turn` |
| `RalphRepository` | 增加 checkpoint 存储 | 兼容 |
| `CommandConsumer` | 增加 `max_concurrent` 检查 | 兼容 |
| Dashboard API | 增加 `/checkpoints`、`/knowledge_graph` 路由 | 新增，不影响旧路由 |

### 7.2 迁移策略

1. **平滑过渡**：二期组件以新增模块方式引入，一期逻辑保持运行。
2. **灰度启用**：通过 `.ralph/config/phase2.yaml` 的 feature flag 控制：
   ```yaml
   phase2:
     turn_based_execution: true
     memory_manager: true
     knowledge_graph: false  # 先不启用
     issue_sync: false
   ```
3. **数据迁移**：已有 work unit 历史自动触发一次 compaction，生成短期记忆初始数据。

---

## 8. 关键决策记录

### ADR-001：不用向量数据库，用结构化检索+轻量语义

**问题**：RAG 是否需要引入 Pinecone/ChromaDB/Weaviate？

**决策**：先不引入重型向量数据库。

**理由**：
1. Ralph 的语料高度结构化（JSON/YAML/Markdown），结构化检索（倒排+图谱遍历）覆盖 80% 场景。
2. 非结构化日志可用关键词+BM25，embedding 检索作为可选插件。
3. 保持"文件系统为主"的哲学，不引入外部服务依赖。

### ADR-002：双层图谱存储策略

**问题**：知识图谱用什么存储？

**决策**：
- **代码/文档级图谱**：graphify 的 `graph.json`（NetworkX node-link 格式），由 graphify 工具链管理
- **任务级业务图谱**：Ralph 自建的 `nodes.jsonl` + `edges.jsonl` + 内存遍历

**理由**：
1. graphify 已经成熟处理代码库 AST+语义提取、社区检测、增量更新，不重复造轮子。
2. 任务级图谱是 Ralph 业务领域（TaskNode、BlockerNode 等），graphify 不理解这些概念，必须自建。
3. 两套图谱通过 FileNode 的 `source_file` 字段做映射关联，查询时联合使用。
4. 零外部数据库依赖，备份就是 `cp -r .ralph/`。

### ADR-003：PM Agent 不常驻内存，每次调度新建上下文

**问题**：PM Agent 是否应该像 Symphony Orchestrator 一样常驻内存？

**决策**：不常驻，每次调度时由 `PMCoordinator` 新建上下文。

**理由**：
1. Python 生态没有 BEAM 的轻量进程，常驻 agent 容易积累状态错误。
2. "空记忆调度"的核心就是每次从零开始，避免上下文污染。
3. 调度频率不高（秒级/分钟级），新建上下文的 overhead 可接受。

---

## 9. 成功标准

二期成功的标准：

1. PM Agent 调度时的 prompt 大小**不随项目规模线性增长**（始终 <5k tokens）。
2. 一个复杂任务（如"实现用户认证系统"）可以分 5-10 个 turns 完成，中间中断后可恢复。
3. 查询"修改文件 A 会影响什么"能在 1 秒内返回关联任务列表。
4. 系统连续运行 4 小时后，PM Agent 仍能准确判断下一步该做什么。
5. Issue tracker 上的 label/comment 与 Ralph 状态保持实时同步。
6. 并发执行 3 个 WorkUnit 时，彼此不冲突、不越界。
7. 人类在 GitHub Issues 里评论 `/ralph retry`，Ralph 能正确响应。

---

## 10. 风险提示

1. **Compaction 质量**：如果 compaction agent 压缩时丢失了关键信息，PM Agent 会做错误决策。需要 review compaction 结果。
2. **ContinuationCheck 准确性**：判断"是否还有剩余工作"本身需要 AI 判断，可能出错。需要保守策略（宁可多一轮，不要漏任务）。
3. **知识图谱一致性**：图谱和实际代码状态可能不同步（如手动修改了代码）。需要定期 recon 同步。
4. **RAG 幻觉**：检索到的历史信息可能不准确。需要标注置信度，高置信度信息优先。
5. **完整会话存储膨胀**：完整对话记录不可压缩，长期运行后 `.ralph/sessions/` 可能占用大量磁盘。需要定期归档策略（如保留最近 30 天，更早的压缩归档到冷存储），但归档≠压缩摘要——归档是物理移动，内容保持完整。
6. **Worktree 性能**：git worktree 创建和切换有 overhead。大量小任务时可能拖慢。需要权衡隔离粒度和性能。