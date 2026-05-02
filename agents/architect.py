"""Software Architect Agent"""

from agents.base_agent import BaseAgent


class Architect(BaseAgent):
    role = "architect"
    prompt_file = "architect"

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
1. 你是软件架构师，负责系统设计和模块划分
2. 设计要符合单一职责、开闭原则、依赖倒置
3. 交付架构图、模块说明、接口定义，写入文件
4. 考虑可扩展性和性能
5. 输出 Markdown 格式的架构图（使用 Mermaid 或 ASCII）
"""
