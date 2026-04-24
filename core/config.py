"""系统配置"""

from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# 运行时文件
FEATURES_FILE = DATA_DIR / "features.json"
PROGRESS_FILE = DATA_DIR / "claude-progress.txt"
PROJECT_STATE_FILE = DATA_DIR / "project-state.json"
TASK_DB = DATA_DIR / "tasks.db"
PRD_FILE = DATA_DIR / "prd.md"

# Prompts目录
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# Git配置
GIT_AUTHOR_NAME = "AI Developer"
GIT_AUTHOR_EMAIL = "ai-dev@localhost"

# Agent配置
MAX_RETRY_COUNT = 3
FEATURE_BATCH_SIZE = 1  # 每次只做一个feature

# 执行台账 / 执行计划审计文件
EXECUTION_LEDGER_FILE = DATA_DIR / "execution-plan.json"

# Playwright配置
PLAYWRIGHT_TIMEOUT = 30000  # 30秒
PLAYWRIGHT_HEADLESS = True

# PMCoordinator 静默检测阈值（秒）
SILENCE_WARNING_THRESHOLD = 30      # 30秒无活动 → WARNING
SILENCE_NOTIFY_THRESHOLD = 120      # 2分钟无活动 → NOTIFY
SILENCE_INTERVENTION_THRESHOLD = 600  # 10分钟无活动 → INTERVENTION
AGENT_POLL_INTERVAL = 2.0           # Agent状态轮询间隔（秒）
