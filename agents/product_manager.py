"""Product Manager Agent"""

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

    def chat_response(self, user_message: str, chat_history: list, repository: Any = None) -> str | None:
        """生成对话式 PM 回复（用于看板对话）。

        Args:
            user_message: 用户最新消息
            chat_history: ChatMessage 列表
            repository: ProjectStateRepository（可选，用于获取项目上下文）

        Returns:
            PM 回复文本，失败时返回 None
        """
        history_lines = []
        for msg in chat_history:
            role_label = "用户" if msg.role == "user" else "PM"
            history_lines.append(f"{role_label}: {msg.content}")
        conversation = "\n".join(history_lines)

        # 从 Repository 获取当前项目状态作为上下文
        project_context = ""
        if repository is not None:
            try:
                snapshot = repository.load_snapshot()
                agents_info = "\n".join(
                    f"- {a.id} ({a.role}): {a.status}" for a in snapshot.agents
                )
                features_info = "\n".join(
                    f"- {f.id} ({f.title}): {f.status}" for f in snapshot.features
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

        prompt = f"""{self.system_prompt}

你是一个资深产品经理和技术团队 Team Leader。
你正在管理一个软件开发项目，有多个子 Agent（前端开发、后端开发、数据库专家、QA 测试、安全审查、UI 设计、文档编写）听你指挥。

{project_context}

---

## 当前对话

以下是完整的对话历史：
{conversation}

## 你的任务

1. 分析用户最新消息的意图
2. 结合项目状态给出明确的回复
3. 如果需要进一步分解任务，说明你的计划
4. 回复要简洁、明确、可执行
5. 如果涉及多个同职能 Agent，你要合理划分功能模块和接口

请直接回复用户（不要输出额外的格式或标记）："""

        result = self._run_with_claude(prompt, timeout=120)
        if result["success"]:
            return result["stdout"].strip() or None
        return None
