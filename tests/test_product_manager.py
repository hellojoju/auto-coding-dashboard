"""Tests for ProductManager agent."""

from dataclasses import dataclass

from agents.product_manager import ProductManager


@dataclass
class FakeMessage:
    role: str
    content: str


class TestSummarizeHistory:
    """测试 _summarize_history 方法。"""

    def test_short_conversation_no_summarization(self, tmp_path):
        """消息数 <= 5 时不压缩。"""
        pm = ProductManager(tmp_path)
        messages = [FakeMessage("user", f"msg{i}") for i in range(5)]
        result = pm._summarize_history(messages)
        assert result == ""

    def test_empty_conversation_no_summarization(self, tmp_path):
        """空消息列表不压缩。"""
        pm = ProductManager(tmp_path)
        result = pm._summarize_history([])
        assert result == ""

    def test_long_conversation_calls_llm(self, tmp_path):
        """消息数 > 5 时调用压缩。"""
        pm = ProductManager(tmp_path)
        messages = [FakeMessage("user", f"msg{i}") for i in range(10)]
        # mock _run_with_claude
        pm._run_with_claude = lambda *a, **k: {"success": True, "stdout": "摘要内容"}
        result = pm._summarize_history(messages)
        assert result == "摘要内容"

    def test_summarization_failure_returns_empty(self, tmp_path):
        """LLM 调用失败时返回空字符串。"""
        pm = ProductManager(tmp_path)
        messages = [FakeMessage("user", f"msg{i}") for i in range(10)]
        pm._run_with_claude = lambda *a, **k: {"success": False, "stdout": ""}
        result = pm._summarize_history(messages)
        assert result == ""

    def test_exactly_five_messages_no_summarization(self, tmp_path):
        """恰好 5 条消息不压缩。"""
        pm = ProductManager(tmp_path)
        messages = [FakeMessage("user", f"msg{i}") for i in range(5)]
        pm._run_with_claude = lambda *a, **k: {"success": True, "stdout": "不应被调用"}
        result = pm._summarize_history(messages)
        assert result == ""

    def test_six_messages_triggers_summarization(self, tmp_path):
        """6 条消息触发压缩（保留最近 5 条，压缩 1 条）。"""
        pm = ProductManager(tmp_path)
        messages = [FakeMessage("user", f"msg{i}") for i in range(6)]
        pm._run_with_claude = lambda *a, **k: {"success": True, "stdout": "压缩结果"}
        result = pm._summarize_history(messages)
        assert result == "压缩结果"


class FakeAgentInstance:
    def __init__(self, id: str, role: str, status: str):
        self.id = id
        self.role = role
        self.status = status


class FakeFeature:
    def __init__(self, id: str, description: str, status: str):
        self.id = id
        self.description = description
        self.status = status


class FakeSnapshot:
    def __init__(self, agents=None, features=None):
        self.agents = agents or []
        self.features = features or []


class FakeRepository:
    def __init__(self, snapshot=None):
        self._snapshot = snapshot or FakeSnapshot(
            agents=[FakeAgentInstance("dev-1", "frontend", "busy")],
            features=[FakeFeature("feat-1", "实现登录页面", "in_progress")],
        )

    def load_snapshot(self):
        return self._snapshot


class TestChatResponse:
    """测试 chat_response 方法。"""

    def test_basic_chat_response(self, tmp_path):
        """基本对话返回清理后的文本。"""
        pm = ProductManager(tmp_path)
        history = [FakeMessage("user", "我们下一步做什么？")]
        pm._run_with_claude = lambda *a, **k: {"success": True, "stdout": "先完成登录页面"}
        result = pm.chat_response("我们下一步做什么？", history)
        assert result == "先完成登录页面"

    def test_chat_response_with_repository_context(self, tmp_path):
        """带 Repository 时，project_context 包含 feature.description 而非 title。"""
        pm = ProductManager(tmp_path)
        repo = FakeRepository()
        pm._run_with_claude = lambda prompt, **k: {
            "success": True,
            "stdout": "继续做登录页面",
            "_captured_prompt": prompt,  # 方便调试
        }
        result = pm.chat_response("继续", [FakeMessage("user", "继续")], repository=repo)
        assert result == "继续做登录页面"

    def test_chat_response_without_repository(self, tmp_path):
        """不带 Repository 时正常生成回复。"""
        pm = ProductManager(tmp_path)
        history = [FakeMessage("user", "你好")]
        pm._run_with_claude = lambda *a, **k: {"success": True, "stdout": "你好，我是 PM"}
        result = pm.chat_response("你好", history)
        assert result == "你好，我是 PM"

    def test_chat_response_failure_returns_none(self, tmp_path):
        """LLM 调用失败返回 None。"""
        pm = ProductManager(tmp_path)
        history = [FakeMessage("user", "你好")]
        pm._run_with_claude = lambda *a, **k: {"success": False, "stdout": ""}
        result = pm.chat_response("你好", history)
        assert result is None

    def test_chat_response_strips_thinking_tags(self, tmp_path):
        """清理输出中的 thinking 和 tool_use 标签。"""
        pm = ProductManager(tmp_path)
        history = [FakeMessage("user", "你好")]
        pm._run_with_claude = lambda *a, **k: {
            "success": True,
            "stdout": "<thinking>内部思考</thinking>先做A再做B"
        }
        result = pm.chat_response("你好", history)
        assert "thinking" not in result
        assert "先做A再做B" in result

    def test_chat_response_strips_tool_use_tags(self, tmp_path):
        """清理输出中的 tool_use 标签。"""
        pm = ProductManager(tmp_path)
        history = [FakeMessage("user", "你好")]
        pm._run_with_claude = lambda *a, **k: {
            "success": True,
            "stdout": "<tool_use>some_tool</tool_use>开始执行"
        }
        result = pm.chat_response("你好", history)
        assert "tool_use" not in result
        assert "开始执行" in result

    def test_chat_response_returns_none_when_empty(self, tmp_path):
        """LLM 返回空字符串时返回 None 而非空串。"""
        pm = ProductManager(tmp_path)
        history = [FakeMessage("user", "你好")]
        pm._run_with_claude = lambda *a, **k: {"success": True, "stdout": "   "}
        result = pm.chat_response("你好", history)
        assert result is None

    def test_chat_response_prompt_contains_expected_sections(self, tmp_path):
        """校验传给 _run_with_claude 的 prompt 包含预期的 section。"""
        pm = ProductManager(tmp_path)
        repo = FakeRepository(
            snapshot=FakeSnapshot(
                agents=[FakeAgentInstance("dev-1", "frontend", "busy")],
                features=[FakeFeature("F001", "实现登录页面", "in_progress")],
            ),
        )
        captured = {}

        def fake_run(prompt, **k):
            captured["prompt"] = prompt
            return {"success": True, "stdout": "好的"}

        pm._run_with_claude = fake_run
        pm.chat_response("下一步做什么？", [FakeMessage("user", "下一步做什么？")], repository=repo)

        prompt = captured["prompt"]
        # 1. 包含 chat_system_prompt 的关键词
        assert "产品经理" in prompt
        assert "Team Leader" in prompt
        assert "回复风格" in prompt
        # 2. 包含项目状态 section
        assert "当前项目状态" in prompt
        assert "在线 Agent" in prompt
        assert "功能特性" in prompt
        # 3. 包含 feature.description（而非 title）
        assert "实现登录页面" in prompt
        assert "in_progress" in prompt
        # 4. 包含 agent 信息
        assert "dev-1" in prompt
        assert "frontend" in prompt
        # 5. 包含对话历史 section
        assert "当前对话" in prompt or "最近对话" in prompt
        # 6. 包含任务指令 section
        assert "你的任务" in prompt
        assert "分析用户最新消息的意图" in prompt
