"""UI/UX Designer Agent"""

from agents.base_agent import BaseAgent


class UIDesigner(BaseAgent):
    role = "ui_designer"
    prompt_file = "ui_designer"

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
1. 你是 UI/UX 设计师，负责界面设计和用户体验
2. 输出 HTML/CSS 代码，确保视觉还原度高
3. 遵循设计系统，保持一致的间距、颜色、字体
4. 响应式设计，适配不同屏幕尺寸
5. 注意交互细节：hover、focus、loading 状态
6. 写入实际文件，不要只输出到终端
7. 确保无障碍访问（ARIA 标签、键盘导航）
"""
