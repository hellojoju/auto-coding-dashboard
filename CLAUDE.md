# Auto-Coding 工作流协议

> 本文档定义 Agent 开发工作流的约束和步骤。所有参与的 Claude Code 实例必须遵循此协议。

## 工作流概述

Agent 按照 `features.json` 定义的任务列表，逐个执行 Feature。每个 Feature 完成后暂停，等待 PM 审批。

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
