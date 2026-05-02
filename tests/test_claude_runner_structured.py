"""Claude Runner 结构化输出测试

验证 execute() 返回的 dict 可被包装为 ExecutionResult。
"""

from core.verification_result import ExecutionResult


class TestExecutionResultCompatibility:
    def test_from_agent_dict(self) -> None:
        """Agent 返回的 dict 可包装为 ExecutionResult。"""
        agent_result = {
            "success": True,
            "files_changed": ["src/app.py", "tests/test_app.py"],
            "error": "",
            "needs_review": True,
        }
        # 从 dict 构造 ExecutionResult
        result = ExecutionResult(
            work_id="feat-1",
            status="completed" if agent_result["success"] else "failed",
            files_modified=agent_result["files_changed"],
            error=agent_result.get("error", ""),
        )
        assert result.success is True
        assert "src/app.py" in result.files_modified

    def test_from_execution_service_dict(self) -> None:
        """FeatureExecutionService 返回的 dict 可包装为 ExecutionResult。"""
        service_result = {
            "success": True,
            "files_changed": ["src/api.py"],
            "error": "",
            "diff_stat": "src/api.py | 5 +++--",
            "status": "completed",
            "work_id": "feat-1",
        }
        result = ExecutionResult(
            work_id=service_result["work_id"],
            status=service_result["status"],
            files_modified=service_result["files_changed"],
            error=service_result.get("error", ""),
        )
        assert result.success is True
        assert result.work_id == "feat-1"

    def test_failed_execution(self) -> None:
        """失败执行的结构化输出。"""
        service_result = {
            "success": False,
            "files_changed": [],
            "error": "权限检查阻塞: ['prompt 中包含危险命令模式']",
            "status": "blocked",
            "work_id": "feat-1",
        }
        result = ExecutionResult(
            work_id=service_result["work_id"],
            status=service_result["status"],
            error=service_result["error"],
        )
        assert result.success is False
        assert result.status == "blocked"
        assert "权限检查" in result.error
