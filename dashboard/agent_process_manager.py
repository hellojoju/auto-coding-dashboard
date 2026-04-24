"""Agent 子进程管理器：管理 Agent 生命周期（启动/消息注入/中断/恢复）。"""

from __future__ import annotations

import logging
import signal
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AgentProcess:
    """Agent 进程信息。"""
    agent_id: str
    role: str
    command: list[str]
    process: subprocess.Popen | None = None
    working_dir: str | None = None


class AgentProcessManager:
    """管理 Agent 子进程生命周期。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentProcess] = {}

    def register_agent(
        self,
        agent_id: str,
        role: str,
        command: list[str],
        working_dir: str | None = None,
    ) -> None:
        """注册 Agent 到管理器。"""
        self._agents[agent_id] = AgentProcess(
            agent_id=agent_id,
            role=role,
            command=command,
            working_dir=working_dir,
        )

    def update_process(self, agent_id: str, process: subprocess.Popen) -> None:
        """更新 Agent 的进程引用。"""
        if agent_id in self._agents:
            self._agents[agent_id].process = process

    def send_message_to_agent(self, agent_id: str, message: str) -> bool:
        """通过 stdin 向运行中的 Agent 注入消息。返回是否成功。"""
        agent = self._agents.get(agent_id)
        if not agent or not agent.process or not agent.process.stdin or agent.process.stdin.closed:
            logger.warning("无法向 Agent %s 发送消息：进程不可用", agent_id)
            return False
        try:
            prompt = (
                f"\n--- System Message from PM: {message} ---\n"
                "请报告你当前的工作状态、正在执行的任务、以及是否遇到任何阻塞。"
                "如果正在等待某项操作完成，请说明预期完成时间。\n"
            )
            agent.process.stdin.write(prompt)
            agent.process.stdin.flush()
            logger.info("已向 Agent %s 注入消息", agent_id)
            return True
        except (BrokenPipeError, OSError) as e:
            logger.error("向 Agent %s 发送消息失败: %s", agent_id, e)
            return False

    def graceful_interrupt(self, agent_id: str) -> bool:
        """发送 SIGINT 信号，让 Agent 优雅中断。"""
        agent = self._agents.get(agent_id)
        if not agent or not agent.process:
            logger.warning("无法中断 Agent %s：进程不存在", agent_id)
            return False
        try:
            agent.process.send_signal(signal.SIGINT)
            agent.process.wait(timeout=10)
            logger.info("Agent %s 已优雅中断", agent_id)
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Agent %s SIGINT 超时，可能需要强制终止", agent_id)
            return False
        except (ProcessLookupError, OSError) as e:
            logger.error("中断 Agent %s 失败: %s", agent_id, e)
            return False

    def force_kill(self, agent_id: str) -> bool:
        """强制终止 Agent 进程。"""
        agent = self._agents.get(agent_id)
        if not agent or not agent.process:
            return False
        try:
            agent.process.kill()
            agent.process.wait(timeout=5)
            logger.info("Agent %s 已强制终止", agent_id)
            return True
        except (ProcessLookupError, OSError) as e:
            logger.error("强制终止 Agent %s 失败: %s", agent_id, e)
            return False

    def get_agent_status(self, agent_id: str) -> dict:
        """获取 Agent 进程状态。"""
        agent = self._agents.get(agent_id)
        if not agent:
            return {"exists": False}
        if not agent.process:
            return {"exists": True, "running": False}
        poll_result = agent.process.poll()
        return {
            "exists": True,
            "running": poll_result is None,
            "exit_code": poll_result,
            "pid": agent.process.pid,
        }

    def remove_agent(self, agent_id: str) -> None:
        """从管理器移除 Agent。"""
        self._agents.pop(agent_id, None)

    def get_all_agents(self) -> dict[str, dict]:
        """返回所有 Agent 的进程状态概览。"""
        result = {}
        for agent_id, agent in self._agents.items():
            status = self.get_agent_status(agent_id)
            result[agent_id] = {
                "role": agent.role,
                "status": status.get("running") and "running" or "stopped",
                "pid": status.get("pid"),
                "exit_code": status.get("exit_code"),
            }
        return result

    def list_agents(self) -> dict[str, AgentProcess]:
        """返回所有注册的 Agent。"""
        return dict(self._agents)
