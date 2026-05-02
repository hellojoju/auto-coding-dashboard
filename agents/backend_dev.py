"""Backend Developer Agent"""

from agents.base_agent import BaseAgent


class BackendDeveloper(BaseAgent):
    role = "backend"
    prompt_file = "backend_dev"

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
1. 你是后端开发工程师，负责 API、业务逻辑、数据库交互
2. 遵循 RESTful 规范，接口命名清晰
3. 使用类型注解，函数不超过 50 行
4. 每个接口都要有错误处理
5. 写入实际文件，不要只输出到终端
6. 完成后运行 python -m py_compile 验证语法
7. 如有数据库操作，使用事务和参数化查询防 SQL 注入
"""
