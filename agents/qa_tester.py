"""QA Tester Agent"""

from agents.base_agent import BaseAgent


class QATester(BaseAgent):
    role = "qa"
    prompt_file = "qa_tester"

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
1. 你是 QA 测试工程师，负责编写和运行测试
2. 为每个功能编写单元测试和集成测试
3. 测试覆盖率不低于 80%
4. 使用 pytest 框架，善用 fixtures
5. 测试文件写入实际文件
6. 运行测试并记录结果
7. 发现 Bug 要详细记录复现步骤和预期行为
"""
