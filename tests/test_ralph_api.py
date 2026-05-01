"""Ralph API 端点测试。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from dashboard.api.routes import create_dashboard_app
from dashboard.event_bus import EventBus
from dashboard.state_repository import ProjectStateRepository
from ralph.repository import RalphRepository
from ralph.schema.blocker import Blocker
from ralph.schema.evidence import Evidence
from ralph.schema.review_result import CriterionResult, Issue, ReviewResult
from ralph.schema.work_unit import WorkUnit, WorkUnitStatus


@pytest.fixture
def event_bus(tmp_path: Path) -> EventBus:
    return EventBus(log_file=tmp_path / "events.log")


@pytest.fixture
def repo(tmp_path: Path) -> ProjectStateRepository:
    return ProjectStateRepository(
        base_dir=tmp_path,
        project_id="test_proj",
        run_id="run_001",
    )


@pytest.fixture
def ralph_repo(tmp_path: Path) -> RalphRepository:
    ralph_dir = tmp_path / ".ralph"
    return RalphRepository(ralph_dir)


@pytest.fixture
def app(event_bus: EventBus, repo: ProjectStateRepository, ralph_repo: RalphRepository):
    return create_dashboard_app(
        event_bus=event_bus,
        repository=repo,
        ralph_repository=ralph_repo,
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def test_client(app):
    return TestClient(app)


# --- GET /api/ralph/health ---


async def test_ralph_health(client):
    resp = await client.get("/api/ralph/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "work_units_count" in data
    assert "timestamp" in data


# --- GET /api/ralph/work-units ---


async def test_ralph_list_work_units_empty(client):
    resp = await client.get("/api/ralph/work-units")
    assert resp.status_code == 200
    data = resp.json()
    assert data["work_units"] == []
    assert data["total"] == 0


async def test_ralph_list_work_units_with_data(app, ralph_repo):
    # 创建测试 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
        status=WorkUnitStatus.READY,
    )
    ralph_repo.save_work_unit(unit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/work-units")
        data = resp.json()
        assert data["total"] == 1
        assert data["work_units"][0]["work_id"] == "W-001"
        assert data["work_units"][0]["status"] == "ready"


async def test_ralph_list_work_units_with_status_filter(app, ralph_repo):
    # 创建不同状态的 WorkUnit
    unit1 = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="任务1",
        status=WorkUnitStatus.ACCEPTED,
    )
    unit2 = WorkUnit(
        work_id="W-002",
        work_type="测试",
        producer_role="qa",
        reviewer_role="pm",
        expected_output="测试功能",
        title="任务2",
        status=WorkUnitStatus.BLOCKED,
    )
    ralph_repo.save_work_unit(unit1)
    ralph_repo.save_work_unit(unit2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 过滤 accepted
        resp = await client.get("/api/ralph/work-units", params={"status": "accepted"})
        data = resp.json()
        assert data["total"] == 1
        assert data["work_units"][0]["work_id"] == "W-001"

        # 过滤 blocked
        resp = await client.get("/api/ralph/work-units", params={"status": "blocked"})
        data = resp.json()
        assert data["total"] == 1
        assert data["work_units"][0]["work_id"] == "W-002"


async def test_ralph_list_work_units_invalid_status(client):
    resp = await client.get("/api/ralph/work-units", params={"status": "invalid_status"})
    assert resp.status_code == 400


# --- GET /api/ralph/work-units/{work_id} ---


async def test_ralph_get_work_unit_success(app, ralph_repo):
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
        status=WorkUnitStatus.READY,
    )
    ralph_repo.save_work_unit(unit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/work-units/W-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_id"] == "W-001"
        assert data["title"] == "测试任务"
        assert data["status"] == "ready"


async def test_ralph_get_work_unit_not_found(client):
    resp = await client.get("/api/ralph/work-units/NONEXISTENT")
    assert resp.status_code == 404


# --- GET /api/ralph/evidence/{work_id} ---


async def test_ralph_list_evidence_success(app, ralph_repo):
    # 先创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    # 创建证据
    evidence = Evidence(
        evidence_id="EV-001",
        work_id="W-001",
        evidence_type="diff",
        file_path="W-001/diff.txt",
        description="代码变更",
    )
    ralph_repo.save_evidence(evidence)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/evidence/W-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_id"] == "W-001"
        assert data["total"] == 1
        assert data["evidence"][0]["evidence_id"] == "EV-001"


async def test_ralph_list_evidence_work_unit_not_found(client):
    resp = await client.get("/api/ralph/evidence/NONEXISTENT")
    assert resp.status_code == 404


# --- GET /api/ralph/evidence/{work_id}/{file_path} ---


async def test_ralph_get_evidence_file_success(app, ralph_repo, tmp_path):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    # 创建证据文件
    evidence_file = ralph_repo._evidence_dir / "W-001" / "diff.txt"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("diff content here")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/evidence/W-001/W-001/diff.txt")
        assert resp.status_code == 200
        assert resp.text == "diff content here"
        assert resp.headers["X-Truncated"] == "false"


async def test_ralph_get_evidence_file_path_traversal(app, ralph_repo, tmp_path):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 尝试路径遍历 - 使用 %2E 编码来绕过 Starlette 的路径规范化
        # %2E = . 所以 %2E%2E = ..
        resp = await client.get("/api/ralph/evidence/W-001/%2E%2E/%2E%2E/%2E%2E/etc/passwd")
        assert resp.status_code == 403


async def test_ralph_get_evidence_file_not_found(app, ralph_repo):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/evidence/W-001/nonexistent.txt")
        assert resp.status_code == 404


async def test_ralph_get_evidence_file_truncation(app, ralph_repo):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    # 创建大文件 (>100KB)
    evidence_file = ralph_repo._evidence_dir / "W-001" / "large.txt"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    large_content = "x" * (100 * 1024 + 1000)  # 超过 100KB
    evidence_file.write_text(large_content)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/evidence/W-001/W-001/large.txt")
        assert resp.status_code == 200
        assert resp.headers["X-Truncated"] == "true"
        assert "TRUNCATED" in resp.text


async def test_ralph_get_evidence_file_redaction(app, ralph_repo):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    # 创建包含敏感信息的文件
    evidence_file = ralph_repo._evidence_dir / "W-001" / "config.txt"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text('api_key = "sk-1234567890abcdef"\npassword = "secret123"')

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/evidence/W-001/W-001/config.txt")
        assert resp.status_code == 200
        assert "***REDACTED***" in resp.text
        assert "sk-1234567890abcdef" not in resp.text
        assert "secret123" not in resp.text


# --- GET /api/ralph/reviews/{work_id} ---


async def test_ralph_list_reviews_success(app, ralph_repo):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    # 创建 Review
    review = ReviewResult(
        work_id="W-001",
        reviewer_context_id="reviewer-1",
        review_type="功能完整性",
        conclusion="通过",
        recommended_action="接受",
        criteria_results=[CriterionResult(criterion="功能完整", passed=True)],
    )
    ralph_repo.save_review(review)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/reviews/W-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_id"] == "W-001"
        assert data["total"] == 1
        assert data["reviews"][0]["conclusion"] == "通过"


async def test_ralph_list_reviews_work_unit_not_found(client):
    resp = await client.get("/api/ralph/reviews/NONEXISTENT")
    assert resp.status_code == 404


# --- GET /api/ralph/blockers ---


async def test_ralph_list_blockers(app, ralph_repo):
    # 创建 WorkUnit
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
    )
    ralph_repo.save_work_unit(unit)

    # 创建 Blocker
    blocker = Blocker(
        blocker_id="B-001",
        work_id="W-001",
        reason="依赖未完成",
        blocker_type="dependency",
        resolved=False,
    )
    ralph_repo.save_blocker(blocker)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 列出所有 blockers
        resp = await client.get("/api/ralph/blockers")
        data = resp.json()
        assert data["total"] == 1
        assert data["blockers"][0]["blocker_id"] == "B-001"

        # 按 work_id 过滤
        resp = await client.get("/api/ralph/blockers", params={"work_id": "W-001"})
        data = resp.json()
        assert data["total"] == 1

        # 按 resolved 过滤
        resp = await client.get("/api/ralph/blockers", params={"resolved": "false"})
        data = resp.json()
        assert data["total"] == 1


# --- GET /api/ralph/pending-actions ---


async def test_ralph_pending_actions(app, ralph_repo, repo):
    # 创建不同状态的 WorkUnit
    blocked_unit = WorkUnit(
        work_id="W-BLOCKED",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="阻塞任务",
        status=WorkUnitStatus.BLOCKED,
    )
    ralph_repo.save_work_unit(blocked_unit)

    # 创建 Blocker
    blocker = Blocker(
        blocker_id="B-001",
        work_id="W-BLOCKED",
        reason="权限不足",
        blocker_type="permission",
        resolved=False,
    )
    ralph_repo.save_blocker(blocker)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/pending-actions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["summary"]["blocked"] >= 1


# --- GET /api/ralph/transitions/{work_id} ---


async def test_ralph_get_transitions(app, ralph_repo):
    # 创建 WorkUnit 并进行状态转换
    unit = WorkUnit(
        work_id="W-001",
        work_type="开发",
        producer_role="backend",
        reviewer_role="qa",
        expected_output="实现功能",
        title="测试任务",
        status=WorkUnitStatus.DRAFT,
    )
    ralph_repo.save_work_unit(unit)

    # 执行状态转换
    ralph_repo.transition("W-001", WorkUnitStatus.READY, actor_role="scheduler", reason="准备就绪")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/transitions/W-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_id"] == "W-001"
        assert data["total"] >= 1


async def test_ralph_get_transitions_work_unit_not_found(client):
    resp = await client.get("/api/ralph/transitions/NONEXISTENT")
    assert resp.status_code == 404


# --- GET /api/ralph/summary ---


async def test_ralph_summary(app, ralph_repo):
    # 创建多个 WorkUnit
    for i, status in enumerate([WorkUnitStatus.ACCEPTED, WorkUnitStatus.ACCEPTED, WorkUnitStatus.FAILED]):
        unit = WorkUnit(
            work_id=f"W-{i:03d}",
            work_type="开发",
            producer_role="backend",
            reviewer_role="qa",
            expected_output="实现功能",
            title=f"任务{i}",
            status=status,
        )
        ralph_repo.save_work_unit(unit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/ralph/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_work_units"] == 3
        assert data["status_counts"]["accepted"] == 2
        assert data["status_counts"]["failed"] == 1
        assert "success_rate_percent" in data
        assert "timestamp" in data


# --- POST /api/ralph/commands ---


async def test_ralph_create_command_success(client):
    resp = await client.post(
        "/api/ralph/commands",
        json={"type": "start_run", "payload": {"test": True}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "command_id" in data
    assert data["status"] == "pending"
    assert data["was_duplicate"] is False


async def test_ralph_create_command_missing_type(client):
    resp = await client.post("/api/ralph/commands", json={"payload": {}})
    assert resp.status_code == 422


async def test_ralph_create_command_idempotent(client, repo):
    key = "test-idempotency-key-001"

    # 第一次创建
    resp1 = await client.post(
        "/api/ralph/commands",
        json={"type": "execute_work_unit", "work_id": "W-001", "idempotency_key": key},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["was_duplicate"] is False
    cmd_id = data1["command_id"]

    # 重复创建（相同 idempotency_key）
    resp2 = await client.post(
        "/api/ralph/commands",
        json={"type": "execute_work_unit", "work_id": "W-001", "idempotency_key": key},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["command_id"] == cmd_id
    assert data2["was_duplicate"] is True


# --- GET /api/ralph/commands/{command_id} ---


async def test_ralph_get_command_success(client):
    # 先创建 Command
    create_resp = await client.post(
        "/api/ralph/commands",
        json={"type": "test_command"},
    )
    cmd_id = create_resp.json()["command_id"]

    # 查询 Command
    resp = await client.get(f"/api/ralph/commands/{cmd_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["command_id"] == cmd_id
    assert data["type"] == "test_command"


async def test_ralph_get_command_not_found(client):
    resp = await client.get("/api/ralph/commands/NONEXISTENT")
    assert resp.status_code == 404


# --- POST /api/ralph/commands/{command_id}/cancel ---


async def test_ralph_cancel_command_success(client):
    # 先创建 Command
    create_resp = await client.post(
        "/api/ralph/commands",
        json={"type": "test_command"},
    )
    cmd_id = create_resp.json()["command_id"]

    # 取消 Command
    resp = await client.post(f"/api/ralph/commands/{cmd_id}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "cancelled"

    # 验证状态已更新
    get_resp = await client.get(f"/api/ralph/commands/{cmd_id}")
    assert get_resp.json()["status"] == "cancelled"


async def test_ralph_cancel_command_not_found(client):
    resp = await client.post("/api/ralph/commands/NONEXISTENT/cancel")
    assert resp.status_code == 404


async def test_ralph_cancel_command_wrong_status(client):
    # 先创建 Command
    create_resp = await client.post(
        "/api/ralph/commands",
        json={"type": "test_command"},
    )
    cmd_id = create_resp.json()["command_id"]

    # 手动修改状态为 applied
    # 注意：这里我们通过内部接口修改，实际测试中可能需要其他方式
    # 这里我们测试已经 cancelled 的 command 不能再取消
    await client.post(f"/api/ralph/commands/{cmd_id}/cancel")

    # 再次取消应该失败
    resp = await client.post(f"/api/ralph/commands/{cmd_id}/cancel")
    assert resp.status_code == 409
