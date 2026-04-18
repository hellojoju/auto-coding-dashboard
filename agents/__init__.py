"""Agents包 - 各角色AI工程师"""

from agents.base_agent import BaseAgent
from agents.backend_dev import BackendDeveloper
from agents.frontend_dev import FrontendDeveloper
from agents.qa_tester import QATester
from agents.product_manager import ProductManager
from agents.ui_designer import UIDesigner
from agents.database_expert import DatabaseExpert
from agents.security_reviewer import SecurityReviewer
from agents.docs_writer import DocsWriter
from agents.architect import Architect

# 角色 -> Agent类 映射
AGENT_REGISTRY = {
    "backend": BackendDeveloper,
    "frontend": FrontendDeveloper,
    "qa": QATester,
    "product": ProductManager,
    "ui_designer": UIDesigner,
    "database": DatabaseExpert,
    "security": SecurityReviewer,
    "docs": DocsWriter,
    "architect": Architect,
}

# 角色中文名映射
AGENT_ROLES = {
    "backend": "后端开发工程师",
    "frontend": "前端开发工程师",
    "database": "数据库专家",
    "qa": "QA测试工程师",
    "product": "产品经理",
    "ui_designer": "UI/UX设计师",
    "security": "安全工程师",
    "docs": "技术文档工程师",
    "architect": "系统架构师",
}


def get_agent(role: str, project_dir):
    """根据角色获取对应的Agent实例"""
    agent_cls = AGENT_REGISTRY.get(role)
    if agent_cls is None:
        raise ValueError(f"未知的Agent角色: {role}")
    return agent_cls(project_dir)


from agents.pool import AgentPool, AgentInstance

__all__ = [
    "BaseAgent",
    "BackendDeveloper",
    "FrontendDeveloper",
    "QATester",
    "ProductManager",
    "UIDesigner",
    "DatabaseExpert",
    "SecurityReviewer",
    "DocsWriter",
    "Architect",
    "AGENT_REGISTRY",
    "AGENT_ROLES",
    "get_agent",
    "AgentPool",
    "AgentInstance",
]
