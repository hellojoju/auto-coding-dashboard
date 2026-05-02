# Auto-Coding 执行工作流

## 执行原则

1. 一次执行只处理一个明确的 Feature 子目标。
2. 执行前必须明确输入上下文：PRD 摘要、依赖上下文、当前目标。
3. 执行后必须产生可观测结果：状态、事件、台账、必要时阻塞问题。

## Feature / Task / Command

- `Feature`: 面向用户需求的业务项。
- `Task`: Feature 下可执行的工程单元。
- `Command`: 人类对系统的控制指令，例如 `approve/reject/pause/resume`。

## 标准执行流程

1. 选择下一个可执行 Feature。
2. 分配 Agent 实例并记录开始事件。
3. Agent 执行单次目标。
4. 成功时进入 `review`，等待审批或验收。
5. 验收通过后标记完成并记录台账。
6. 失败时根据重试次数决定 `retrying` 或 `blocked`。

## 阻塞协议

出现以下情况必须创建 BlockingIssue：

- 缺少环境变量
- 缺少 API 凭据
- 依赖 Feature 未完成
- 外部服务不可用
- 达到最大重试次数

阻塞问题必须包含：

- 影响的 Feature
- 问题类型
- 人类可读描述
- 上下文
- 是否已解决

## 测试协议

- 语法检查失败不能算完成。
- 有 `test_steps` 时必须跑 E2E。
- 只有通过验收后才能进入 `done`。
