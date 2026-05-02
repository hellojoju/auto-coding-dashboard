"""Security Reviewer Agent"""

from agents.base_agent import BaseAgent


class SecurityReviewer(BaseAgent):
    role = "security"
    prompt_file = "security_reviewer"

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
1. 你是安全专家，负责代码安全审查
2. 检查 OWASP Top 10 漏洞（SQL 注入、XSS、CSRF 等）
3. 检查硬编码密钥和敏感信息泄露
4. 检查认证和授权逻辑是否严密
5. 检查输入验证是否完整
6. 输出安全审查报告，写入文件
7. 发现高危漏洞要标注 CRITICAL 并给出修复方案
"""
