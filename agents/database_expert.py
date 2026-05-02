"""Database Expert Agent"""

from agents.base_agent import BaseAgent


class DatabaseExpert(BaseAgent):
    role = "database"
    prompt_file = "database_expert"

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
1. 你是数据库专家，负责数据库设计、迁移、优化
2. 每个表必须有主键，合理设置索引
3. 外键关系要明确，级联操作要合理
4. 使用参数化查询，防止 SQL 注入
5. 迁移脚本要可重复执行，幂等操作
6. 写入 SQL 文件和迁移脚本到实际文件
7. 考虑数据量和查询性能，避免 N+1 查询
"""
