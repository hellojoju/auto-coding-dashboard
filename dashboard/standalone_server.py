"""Dashboard 启动脚本 — 正确注入所有依赖后启动 uvicorn。"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.project_manager import ProjectManager  # noqa: E402
from dashboard.api.routes import create_dashboard_app  # noqa: E402
from dashboard.event_bus import EventBus  # noqa: E402
from dashboard.state_repository import ProjectStateRepository  # noqa: E402

PROJECT_DIR = project_root / "project"
STATE_DIR = PROJECT_DIR / "data" / "dashboard"
STATE_DIR.mkdir(parents=True, exist_ok=True)

event_bus = EventBus(log_file=STATE_DIR / "events.jsonl")
repository = ProjectStateRepository(
    base_dir=STATE_DIR,
    project_id=str(PROJECT_DIR.name),
    run_id="dashboard-standalone",
)
pm = ProjectManager(PROJECT_DIR) if PROJECT_DIR.exists() else None
coordinator = None
if pm and pm._initialized:
    from dashboard.coordinator import PMCoordinator
    coordinator = PMCoordinator(pm, repository, event_bus)

app = create_dashboard_app(event_bus, repository, coordinator, product_manager=pm)

if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Dashboard starting on port {port}")
    print(f"  - ProductManager: {'已配置' if pm else '未配置'}")
    print(f"  - PMCoordinator: {'已配置' if coordinator else 'standalone 模式'}")
    uvicorn.run(app, host="0.0.0.0", port=port)
