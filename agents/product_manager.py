"""Product Manager Agent"""

from typing import Any

from agents.base_agent import BaseAgent


class ProductManager(BaseAgent):
    role = "product"
    prompt_file = "product_manager"

    def _build_prompt(self, task: dict) -> str:
        feature_id = task.get("feature_id", "")
        description = task.get("description", "")
        category = task.get("category", "")
        test_steps = task.get("test_steps", [])
        prd = task.get("prd_summary", "")
        deps = task.get("dependencies_context", "")
        project_dir = task.get("project_dir", "")

        steps_text = "\n".join(f"- {s}" for s in test_steps) if test_steps else "无具体测试步骤"

        return f"""{self.system_prompt}

---

## 任务信息
Feature ID: {feature_id}
分类: {category}
描述: {description}

## 验收标准
{steps_text}

## 依赖上下文
{deps}

## PRD摘要
{prd}

## 工作目录
{project_dir}

## 执行要求
1. 你是产品经理，负责需求分析和产品规划
2. 先理解现有文档和代码，再产出交付物
3. 交付物写入文件，不要只输出到终端
4. 保持文档结构清晰，标题层级一致
5. 完成后确保验收标准可被满足
"""

    def _summarize_history(self, messages: list) -> str:
        """将早期对话压缩为摘要，保留关键决策。

        当消息超过 5 条时，将除最近 5 条外的所有消息压缩为摘要。
        """
        if len(messages) <= 5:
            return ""

        old_messages = messages[:-5]
        history_lines = []
        for msg in old_messages:
            role_label = "用户" if msg.role == "user" else "PM"
            history_lines.append(f"{role_label}: {msg.content}")
        old_conversation = "\n".join(history_lines)

        summary_prompt = f"""你是一个项目助理。以下是一段产品开发对话的早期记录：

{old_conversation}

请将上述对话压缩为 3-5 句话的摘要，只保留：
1. 关键决策（技术选型、架构决定）
2. 已分配的任务和责任
3. 重要的项目状态变化
4. 用户明确要求记住的约束条件

忽略寒暄、重复确认和已解决的细节讨论。直接输出摘要，不要加任何前缀。"""

        result = self._run_with_claude(summary_prompt, timeout=60)
        if result["success"]:
            return result["stdout"].strip()
        return ""

    def chat_response(self, user_message: str, chat_history: list, repository: Any = None) -> str | None:
        """生成对话式 PM 回复（用于看板对话）。

        Args:
            user_message: 用户最新消息
            chat_history: ChatMessage 列表
            repository: ProjectStateRepository（可选，用于获取项目上下文）

        Returns:
            PM 回复文本，失败时返回 None
        """
        # 压缩早期历史
        history_summary = self._summarize_history(chat_history)

        # 只保留最近 5 条完整消息
        recent_messages = chat_history[-5:] if len(chat_history) > 5 else chat_history
        recent_lines = []
        for msg in recent_messages:
            role_label = "用户" if msg.role == "user" else "PM"
            recent_lines.append(f"{role_label}: {msg.content}")
        recent_conversation = "\n".join(recent_lines)

        # 从 Repository 获取当前项目状态作为上下文
        project_context = ""
        if repository is not None:
            try:
                snapshot = repository.load_snapshot()
                agents_info = "\n".join(
                    f"- {a.id} ({a.role}): {a.status}" for a in snapshot.agents
                )
                features_info = "\n".join(
                    f"- {f.id} ({f.description}): {f.status}" for f in snapshot.features
                )
                project_context = f"""
## 当前项目状态

### 在线 Agent
{agents_info}

### 功能特性
{features_info}
"""
            except Exception:
                project_context = "\n## 当前项目状态\n（无法加载）\n"

        # 对话式 system prompt，区别于 PRD 编写的的 system prompt
        chat_system_prompt = """你是一个资深产品经理和技术团队 Team Leader。
你正在通过聊天界面管理一个软件开发项目，有多个子 Agent（前端开发、后端开发、数据库专家、\
QA 测试、安全审查、UI 设计、文档编写）听你指挥。

你的回复风格：
- 简洁、明确、直接，不说废话
- 针对用户的具体问题给出具体回答
- 如果需要分解任务，说明你的计划
- 不要输出任何格式标记、工具调用或思考过程"""

        if history_summary:
            history_section = f"""
## 早期对话摘要
{history_summary}

## 最近对话
{recent_conversation}
"""
        else:
            history_section = f"""
## 当前对话
{recent_conversation}
"""

        prompt = f"""{chat_system_prompt}

{project_context}

---
{history_section}
## 你的任务

1. 分析用户最新消息的意图
2. 结合项目状态给出明确的回复
3. 如果需要进一步分解任务，说明你的计划
4. 回复要简洁、明确、可执行
5. 如果涉及多个同职能 Agent，你要合理划分功能模块和接口

请直接回复用户（不要输出额外的格式或标记）："""

        result = self._run_with_claude(prompt, timeout=120)
        if result["success"]:
            # 清理 Claude CLI 原始输出中的多余内容
            raw = result["stdout"].strip()
            # 移除可能的 thinking 标签包裹的内容
            import re
            raw = re.sub(r'<thinking>.*?</thinking>', '', raw, flags=re.DOTALL).strip()
            # 移除可能的 tool_use 块
            raw = re.sub(r'<tool_use>.*?</tool_use>', '', raw, flags=re.DOTALL).strip()
            # 如果结果为空，返回 None
            return raw or None
        return None
