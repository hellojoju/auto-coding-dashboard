"""Technical Writer Agent"""

from agents.base_agent import BaseAgent


class DocsWriter(BaseAgent):
    role = "docs"
    prompt_file = "docs_writer"

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
1. 你是技术文档工程师，负责编写和维护文档
2. 文档要准确、清晰、简洁
3. 包含安装指南、使用说明、API 参考
4. 代码示例要可运行，格式正确
5. 写入实际 Markdown 文件
6. 保持文档结构清晰，链接有效
7. 更新 README 和 CHANGELOG 中相关内容
"""
