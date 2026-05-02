"""临时启动脚本 - 用于端到端验证"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pathlib import Path as P
from dashboard.event_bus import EventBus
from dashboard.state_repository import ProjectStateRepository
from dashboard.api.routes import create_dashboard_app
from dashboard.coordinator import PMCoordinator
from core.project_manager import ProjectManager

import uvicorn

BACKEND_PORT = 18753

project_dir = P(__file__).parent / "project"
project_dir.mkdir(parents=True, exist_ok=True)
state_dir = project_dir / "data" / "dashboard"
state_dir.mkdir(parents=True, exist_ok=True)
event_log = state_dir / "events.jsonl"

event_bus = EventBus(log_file=event_log)
repository = ProjectStateRepository(
    base_dir=state_dir,
    project_id="test-e2e",
    run_id="e2e-verification",
)

pm = ProjectManager(project_dir) if project_dir.exists() else None
coordinator = PMCoordinator(pm, repository, event_bus) if pm and pm._initialized else None

app = create_dashboard_app(event_bus, repository, coordinator)

print(f"Dashboard 启动在 http://localhost:{BACKEND_PORT}")
print(f"项目目录: {project_dir}")
print(f"执行控制: {'PMCoordinator 已配置' if coordinator else 'standalone 模式'}")

uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT, log_level="info")
