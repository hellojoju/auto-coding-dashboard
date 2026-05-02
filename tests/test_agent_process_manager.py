"""AgentProcessManager 单元测试。"""

import signal
import subprocess
from unittest.mock import MagicMock

from dashboard.agent_process_manager import AgentProcessManager


def _make_manager() -> AgentProcessManager:
    return AgentProcessManager()


def _register(manager: AgentProcessManager, agent_id: str = "agent-1", role: str = "backend-dev") -> None:
    manager.register_agent(agent_id, role, ["claude", "-p"])


def test_register_agent():
    manager = _make_manager()
    _register(manager)
    assert "agent-1" in manager._agents
    assert manager._agents["agent-1"].role == "backend-dev"
    assert manager._agents["agent-1"].command == ["claude", "-p"]


def test_update_process():
    manager = _make_manager()
    _register(manager)
    mock_process = MagicMock(spec=subprocess.Popen)
    manager.update_process("agent-1", mock_process)
    assert manager._agents["agent-1"].process is mock_process


def test_send_message_to_agent():
    manager = _make_manager()
    mock_stdin = MagicMock()
    mock_stdin.closed = False
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.stdin = mock_stdin
    _register(manager)
    manager.update_process("agent-1", mock_process)
    result = manager.send_message_to_agent("agent-1", "报告状态")
    assert result is True
    mock_stdin.write.assert_called_once()
    mock_stdin.flush.assert_called_once()
    assert "报告状态" in mock_stdin.write.call_args[0][0]


def test_send_message_to_agent_without_process():
    manager = _make_manager()
    _register(manager)
    result = manager.send_message_to_agent("agent-1", "报告状态")
    assert result is False


def test_graceful_interrupt():
    manager = _make_manager()
    mock_process = MagicMock(spec=subprocess.Popen)
    _register(manager)
    manager.update_process("agent-1", mock_process)
    mock_process.poll.return_value = 0  # 模拟进程已退出
    result = manager.graceful_interrupt("agent-1")
    mock_process.send_signal.assert_called_once_with(signal.SIGINT)
    assert result is True


def test_remove_agent():
    manager = _make_manager()
    _register(manager)
    manager.remove_agent("agent-1")
    assert "agent-1" not in manager._agents
