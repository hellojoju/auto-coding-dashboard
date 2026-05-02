"""agents/pool.py — 运行时 AgentPool 测试（带 workspace 隔离）"""

from pathlib import Path

import pytest

from agents.pool import AgentPool


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path / "ws"


@pytest.fixture
def pool(ws: Path) -> AgentPool:
    return AgentPool(base_workspace=ws)


class TestEnsureInstances:
    def test_single(self, pool):
        insts = pool.ensure_instances("backend", 1)
        assert len(insts) == 1
        assert insts[0].role == "backend"

    def test_multiple(self, pool):
        insts = pool.ensure_instances("frontend", 3)
        assert len(insts) == 3
        assert {i.instance_id for i in insts} == {"frontend-1", "frontend-2", "frontend-3"}

    def test_idempotent(self, pool):
        pool.ensure_instances("qa", 2)
        pool.ensure_instances("qa", 2)
        assert len(pool.list_all()) == 2

    def test_unknown_role(self, pool):
        with pytest.raises(ValueError):
            pool.ensure_instances("ghost", 1)

    def test_workspace_dirs_exist(self, pool, ws):
        pool.ensure_instances("database", 2)
        for inst in pool.list_by_role("database"):
            assert inst.workspace_path.exists()


class TestAcquireRelease:
    def test_acquire_returns_pair(self, pool):
        pool.ensure_instances("backend", 1)
        result = pool.acquire("backend")
        assert result is not None
        inst, agent = result
        assert inst.status == "busy"

    def test_acquire_none_when_all_busy(self, pool):
        pool.ensure_instances("security", 1)
        pool.acquire("security")
        assert pool.acquire("security") is None

    def test_release_makes_available(self, pool):
        pool.ensure_instances("docs", 1)
        inst, _ = pool.acquire("docs")
        pool.release(inst.instance_id)
        assert pool.acquire("docs") is not None

    def test_release_increments_completed(self, pool):
        pool.ensure_instances("backend", 1)
        inst, _ = pool.acquire("backend")
        pool.release(inst.instance_id, task_success=True)
        assert inst.total_tasks_completed == 1

    def test_release_no_increment_on_failure(self, pool):
        pool.ensure_instances("backend", 1)
        inst, _ = pool.acquire("backend")
        pool.release(inst.instance_id, task_success=False)
        assert inst.total_tasks_completed == 0


class TestQueries:
    def test_list_all(self, pool):
        pool.ensure_instances("backend", 2)
        pool.ensure_instances("frontend", 1)
        assert len(pool.list_all()) == 3

    def test_stats(self, pool):
        pool.ensure_instances("qa", 2)
        pool.acquire("qa")
        s = pool.stats()
        assert s["total_instances"] == 2
        assert s["by_role"]["qa"]["busy"] == 1
        assert s["by_role"]["qa"]["idle"] == 1

    def test_instance_to_dict(self, pool):
        pool.ensure_instances("ui_designer", 1)
        d = pool.get_instance("ui_designer-1").to_dict()
        assert "instance_id" in d
        assert d["role"] == "ui_designer"


class TestCleanup:
    def test_cleanup(self, pool):
        pool.ensure_instances("backend", 3)
        pool.cleanup()
        assert len(pool.list_all()) == 0
