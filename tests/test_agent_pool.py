"""AgentPool 和 FileLockTable 测试"""

from dashboard.agent_pool import AgentPool, FileLockTable


def test_get_idle_instance():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    instance = pool.get_idle_instance("backend")
    assert instance is not None
    assert instance.id == "backend-1"


def test_no_idle_returns_none():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    pool.set_instance_busy("backend-1", "F001")
    instance = pool.get_idle_instance("backend")
    assert instance is None


def test_file_lock_no_conflict():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/api/users.py")
    conflict = locks.check_conflict("backend-2", "src/api/orders.py")
    assert conflict is None


def test_file_lock_has_conflict():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/api/users.py")
    conflict = locks.check_conflict("backend-2", "src/api/users.py")
    assert conflict == "backend-1"


def test_file_lock_release():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/api/users.py")
    locks.release("backend-1", "src/api/users.py")
    conflict = locks.check_conflict("backend-2", "src/api/users.py")
    assert conflict is None


def test_max_instances_backend():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    pool.add_instance("backend", 2)
    pool.add_instance("backend", 3)
    pool.add_instance("backend", 4)
    assert len([i for i in pool.instances if i.role == "backend"]) == 3


def test_max_instances_frontend():
    pool = AgentPool()
    pool.add_instance("frontend", 1)
    pool.add_instance("frontend", 2)
    pool.add_instance("frontend", 3)
    pool.add_instance("frontend", 4)
    assert len([i for i in pool.instances if i.role == "frontend"]) == 3


def test_other_roles_single_instance():
    pool = AgentPool()
    pool.add_instance("database", 1)
    pool.add_instance("database", 2)
    assert len([i for i in pool.instances if i.role == "database"]) == 1


def test_set_instance_idle():
    pool = AgentPool()
    pool.add_instance("backend", 1)
    pool.set_instance_busy("backend-1", "F001")
    pool.set_instance_idle("backend-1")
    inst = pool.get_idle_instance("backend")
    assert inst is not None
    assert inst.id == "backend-1"


def test_file_lock_release_all():
    locks = FileLockTable()
    locks.acquire("backend-1", "src/a.py")
    locks.acquire("backend-1", "src/b.py")
    locks.acquire("backend-2", "src/c.py")
    locks.release_all("backend-1")
    assert locks.check_conflict("backend-3", "src/a.py") is None
    assert locks.check_conflict("backend-3", "src/b.py") is None
    assert locks.check_conflict("backend-3", "src/c.py") == "backend-2"
