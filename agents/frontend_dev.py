"""Frontend Developer Agent"""

from agents.base_agent import BaseAgent


class FrontendDeveloper(BaseAgent):
    role = "frontend"
    prompt_file = "frontend_dev"

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
1. 你是前端开发工程师，负责页面、组件、交互
2. 遵循语义化 HTML，ARIA 属性确保无障碍
3. CSS 使用变量，不要硬编码颜色和尺寸
4. 组件化开发，高内聚低耦合
5. 写入实际文件，不要只输出到终端
6. 确保页面在不同浏览器下正常显示
7. 响应式设计，支持移动端和桌面端
"""
