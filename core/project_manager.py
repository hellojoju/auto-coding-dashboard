"""Project Manager Agent - 核心调度器

PM是整个系统的大脑：
1. 与用户头脑风暴，明确需求
2. 生成PRD和Feature List
3. 调度子Agent执行任务
4. 验收成果，处理异常
"""

import asyncio
import contextlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from agents import AGENT_ROLES, AgentPool
from core.blocking_tracker import BlockingIssueType, BlockingTracker
from core.config import (
    GIT_AUTHOR_EMAIL,
    GIT_AUTHOR_NAME,
    MAX_RETRY_COUNT,
)
from core.execution_ledger import ExecutionLedger, ExecutionStatus
from core.permission_guard import PERMISSION_RULES_PROMPT, PermissionGuard
from core.feature_execution_service import FeatureExecutionService
from core.feature_tracker import Feature, FeatureTracker
from core.feature_verification_service import FeatureVerificationService
from core.git_service import GitService
from core.progress_logger import progress

if TYPE_CHECKING:
    from dashboard.state_repository import ProjectStateRepository

# 各角色默认实例数
ROLE_INSTANCE_COUNTS = {
    "backend": 2,
    "frontend": 2,
    "database": 1,
    "qa": 1,
    "ui_designer": 1,
    "security": 1,
    "docs": 1,
    "architect": 1,
    "product": 1,
}


class ProjectManager:
    """PM Agent - 全自动开发系统的核心"""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.permission_guard = PermissionGuard(self.project_dir)
        self._configure_project_paths()
        self.repository = self._create_repository()
        self.feature_tracker = FeatureTracker(
            repository=self.repository,
        )
        self.pool = AgentPool(base_workspace=project_dir / "workspaces")
        self._initialized = False
        self.feature_execution = FeatureExecutionService(self, self.pool, self.feature_tracker)
        self.feature_verification = FeatureVerificationService(self.project_dir)
        self.git_service = GitService(self.project_dir)
        self.execution_ledger = ExecutionLedger(self.project_dir / "data" / "execution-plan.json")
        self.blocking_tracker = BlockingTracker(self.repository)
        self._ensure_all_roles()
        self._restore_state()

    def _configure_project_paths(self) -> None:
        """将模块级运行时文件路径绑定到当前项目目录。"""
        import core.progress_logger
        core.progress_logger.PROGRESS_FILE = self.project_dir / "data" / "claude-progress.txt"

    def _create_repository(self) -> "ProjectStateRepository":
        from dashboard.state_repository import ProjectStateRepository

        state_dir = self.project_dir / "data" / "dashboard"
        state_dir.mkdir(parents=True, exist_ok=True)
        return ProjectStateRepository(
            base_dir=state_dir,
            project_id=str(self.project_dir.name),
            run_id="pm-local",
        )

    def _restore_state(self) -> None:
        """从 Repository 已有状态恢复（如果存在）。"""
        if self.repository.list_features():
            self._initialized = True

    def initialize_project(self, user_request: str) -> str:
        """
        Phase 1: 初始化项目
        - 与用户交互生成PRD（这里用单次生成，实际可多轮）
        - 分解features
        - 初始化git仓库
        - 创建项目骨架

        Args:
            user_request: 用户的原始需求描述

        Returns:
            PRD摘要
        """
        progress.log(f"项目启动: {user_request}")

        # 初始化git
        self._init_git()

        # 生成PRD和Features
        prd_summary, features = self._generate_prd_and_features(user_request)

        # 确保项目数据目录存在
        project_data = self.project_dir / "data"
        project_data.mkdir(parents=True, exist_ok=True)

        # 保存PRD
        prd_file = project_data / "prd.md"
        prd_file.write_text(prd_summary, encoding="utf-8")

        # 导入Features — 直接写入 Repository
        for f in features:
            self.repository.upsert_feature(f)

        progress.log(f"PRD生成完成，分解为 {len(features)} 个features")
        self._initialized = True

        return prd_summary

    def run_execution_loop(self) -> dict:
        """
        Phase 3: 循环执行所有features
        每次取一个ready的feature，分配给对应Agent，验证后标记完成
        """
        progress.log("开始执行循环")

        iteration = 0
        max_iterations = len(self.feature_tracker.all_features()) * MAX_RETRY_COUNT + 10

        while not self.feature_tracker.all_done():
            iteration += 1
            if iteration > max_iterations:
                progress.log(f"达到最大迭代次数 {max_iterations}，停止执行")
                break

            # 获取下一个可执行的feature
            feature = self.feature_tracker.get_next_ready()
            if not feature:
                # 没有ready的feature，检查是否有blocked的
                blocked = [f for f in self.feature_tracker.all_features() if f.status == "blocked"]
                if blocked:
                    progress.log(f"所有待执行的feature都被阻塞: {[f.id for f in blocked]}")
                    break
                # 全部完成
                break

            # 执行这个feature
            self._execute_feature(feature)

        # 最终报告
        return self.feature_tracker.summary()

    def _execute_feature(self, feature: Feature) -> None:
        """执行单个feature"""
        self.feature_tracker.mark_in_progress(feature.id)

        # 校验角色是否合法
        if feature.assigned_to not in AGENT_ROLES:
            self._mark_feature_blocked(
                feature,
                reason=f"未知角色: {feature.assigned_to}",
                issue_type=BlockingIssueType.CODE_ERROR,
                detected_by="coordinator",
                context={"assigned_to": feature.assigned_to},
            )
            self._log(f"{feature.id} 角色 '{feature.assigned_to}' 不在已知角色列表中，标记为 blocked")
            return

        # 从 AgentPool 获取可用实例（支持多实例并发）
        result_pair = self.pool.acquire(feature.assigned_to)
        if result_pair is None:
            self.feature_tracker.mark_blocked(
                feature.id,
                reason="无可用实例",
            )
            self._log(f"无可用 {feature.assigned_to} 实例，{feature.id} 待重试")
            return

        instance, agent = result_pair
        instance.current_task_id = feature.id
        self.feature_tracker.mark_in_progress(
            feature.id,
            instance_id=instance.instance_id,
            workspace_path=str(instance.workspace_path),
        )
        self._sync_agent_instance(instance, status="busy", current_feature=feature.id)
        self.execution_ledger.log_execution(
            feature_id=feature.id,
            status=ExecutionStatus.STARTED,
            agent_id=instance.instance_id,
        )
        self._log(
            f"调度 {AGENT_ROLES.get(feature.assigned_to, feature.assigned_to)}"
            f"[{instance.instance_id}] 执行 {feature.id}"
        )

        try:
            prd_summary = self._get_prd_summary()
            deps_context = self._get_deps_context(feature)
            ws_dir = instance.workspace_path if hasattr(instance, "workspace_path") else None
            result = asyncio.run(self.feature_execution.execute(
                feature,
                agent,
                prd_summary=prd_summary,
                dependencies_context=deps_context,
                workspace_dir=ws_dir,
            ))

            task_success = result.get("success", False)
            if task_success:
                # 验收 — 验证 workspace 中的文件，然后合并回项目根目录
                workspace_dir = instance.workspace_path if hasattr(instance, "workspace_path") else None
                if isinstance(workspace_dir, str):
                    workspace_dir = Path(workspace_dir)
                self.feature_tracker.mark_review(feature.id)
                passed = self.feature_verification.verify(feature, workspace_dir=workspace_dir)

                if passed:
                    # 验证通过，将 workspace 中的文件合并回项目根目录
                    workspace_dir_for_merge = instance.workspace_path if hasattr(instance, "workspace_path") else None
                    if isinstance(workspace_dir_for_merge, str):
                        workspace_dir_for_merge = Path(workspace_dir_for_merge)
                    if workspace_dir_for_merge and workspace_dir_for_merge.exists():
                        self._merge_workspace_to_project(workspace_dir_for_merge)

                    files_changed = result.get("files_changed") or []
                    self.feature_tracker.mark_done(feature.id, files_changed=files_changed)
                    self.execution_ledger.log_execution(
                        feature_id=feature.id,
                        status=ExecutionStatus.COMPLETED,
                        agent_id=instance.instance_id,
                        files_changed=files_changed,
                    )
                    self.git_service.commit(f"feat: {feature.id} - {feature.description}")
                else:
                    retry_count = len(feature.error_log)
                    if retry_count < MAX_RETRY_COUNT:
                        self.feature_tracker.add_error(feature.id, "验收不通过，退回重做")
                        # 通过 Repository 直接更新状态为 pending（重试）
                        existing = self.repository.get_feature(feature.id)
                        if existing:
                            existing.status = "pending"
                            self.repository.upsert_feature(existing, event_type="feature_updated")
                        self.execution_ledger.log_execution(
                            feature_id=feature.id,
                            status=ExecutionStatus.RETRYING,
                            agent_id=instance.instance_id,
                            error="验收不通过，退回重做",
                        )
                        self._log(f"{feature.id} 验收不通过，第{retry_count + 1}次退回")
                    else:
                        self._mark_feature_blocked(
                            feature,
                            reason=f"验收不通过，已重试{MAX_RETRY_COUNT}次",
                            issue_type=BlockingIssueType.CODE_ERROR,
                            detected_by="verification",
                            context={"stage": "verification"},
                            agent_id=instance.instance_id,
                        )
            else:
                error = result.get("error", "未知错误")
                self.feature_tracker.add_error(feature.id, error)
                retry_count = len(feature.error_log)
                if retry_count >= MAX_RETRY_COUNT:
                    self._mark_feature_blocked(
                        feature,
                        reason=f"执行失败{MAX_RETRY_COUNT}次: {error}",
                        issue_type=self._infer_blocking_issue_type(error),
                        detected_by="agent",
                        context={"error": error},
                        agent_id=instance.instance_id,
                    )
                else:
                    existing = self.repository.get_feature(feature.id)
                    if existing:
                        existing.status = "pending"
                        self.repository.upsert_feature(existing, event_type="feature_updated")
                    self.execution_ledger.log_execution(
                        feature_id=feature.id,
                        status=ExecutionStatus.RETRYING,
                        agent_id=instance.instance_id,
                        error=error,
                    )
                    self._log(f"{feature.id} 执行失败，第{retry_count}次重试")

            self.pool.release(instance.instance_id, task_success=task_success)
            released = self.pool.get_instance(instance.instance_id)
            if released is not None:
                self._sync_agent_instance(
                    released, status=released.status,
                    current_feature=released.current_task_id or None,
                )

        except Exception as e:
            self.feature_tracker.add_error(feature.id, str(e))
            self._log(f"{feature.id} 执行异常: {e}")
            self.execution_ledger.log_execution(
                feature_id=feature.id,
                status=ExecutionStatus.FAILED,
                agent_id=instance.instance_id,
                error=str(e),
            )
            self.pool.release(instance.instance_id, task_success=False)
            released = self.pool.get_instance(instance.instance_id)
            if released is not None:
                self._sync_agent_instance(
                    released, status=released.status,
                    current_feature=released.current_task_id or None,
                )

    def _get_prd_summary(self) -> str:
        """获取PRD摘要"""
        prd_file = self.project_dir / "data" / "prd.md"
        if prd_file.exists():
            return prd_file.read_text(encoding="utf-8")[:3000]
        return ""

    def _get_deps_context(self, feature: Feature) -> str:
        """获取依赖的已完成features上下文"""
        if not feature.dependencies:
            return "无依赖"
        deps = "\n"
        for dep_id in feature.dependencies:
            dep = self.feature_tracker.get(dep_id)
            if dep and dep.status == "done":
                deps += f"- {dep.id}: {dep.description}\n"
        return deps if deps.strip() else "依赖尚未完成"

    def _build_task_description(self, feature: Feature) -> str:
        """构建任务描述，包含上下文（保留用于日志和调试）"""
        return f"Feature {feature.id} ({feature.category}): {feature.description}"

    def _sync_agent_instance(
        self,
        instance,
        *,
        status: str,
        current_feature: str | None = None,
    ) -> None:
        from dashboard.models import AgentInstance as DashboardAgent

        live_instance = self.pool.get_instance(getattr(instance, "instance_id", ""))

        workspace_id = getattr(instance, "workspace_id", "") or ""
        if not isinstance(workspace_id, str) or workspace_id.startswith("<MagicMock"):
            workspace_id = ""
        if not workspace_id and live_instance is not None:
            workspace_id = live_instance.workspace_id

        workspace_path = getattr(instance, "workspace_path", "") or ""
        if not isinstance(workspace_path, (str, Path)):
            workspace_path = ""
        workspace_path = str(workspace_path)
        if workspace_path.startswith("<MagicMock"):
            workspace_path = ""
        if not workspace_path and live_instance is not None:
            workspace_path = str(live_instance.workspace_path)

        total_tasks_completed = getattr(instance, "total_tasks_completed", 0)
        if not isinstance(total_tasks_completed, int):
            total_tasks_completed = 0
        if total_tasks_completed == 0 and live_instance is not None:
            total_tasks_completed = live_instance.total_tasks_completed

        dashboard_agent = DashboardAgent(
            id=instance.instance_id,
            role=instance.role,
            instance_number=int(instance.instance_id.split("-")[-1]) if "-" in instance.instance_id else 1,
            status=status,
            current_feature=current_feature,
            workspace_id=workspace_id,
            workspace_path=workspace_path,
            total_tasks_completed=total_tasks_completed,
        )
        self.repository.upsert_agent(dashboard_agent)
        self.repository.append_event(
            type="agent_status_changed",
            agent_id=instance.instance_id,
            status=status,
            feature_id=current_feature or "",
        )

    def _merge_workspace_to_project(self, workspace_dir: Path) -> None:
        """将 workspace 中的变更合并回项目根目录。

        策略：逐个文件复制，覆盖已存在的文件，创建新文件。
        排除 .tasks/、__pycache__/、.git/ 等临时文件。
        """
        skip_dirs = {".tasks", "__pycache__", ".git", ".claude", "node_modules", ".venv"}
        skip_files = {".DS_Store"}

        merged_count = 0
        for src_path in workspace_dir.rglob("*"):
            if src_path.is_dir():
                if src_path.name in skip_dirs:
                    continue
                continue

            if src_path.name in skip_files:
                continue

            rel_path = src_path.relative_to(workspace_dir)
            dst_path = self.project_dir / rel_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_path), str(dst_path))
            merged_count += 1

        self._log(f"从 workspace 合并 {merged_count} 个文件到项目根目录")

    def _infer_blocking_issue_type(self, error: str) -> BlockingIssueType:
        lower = error.lower()
        if "api key" in lower or "credential" in lower or "token" in lower:
            return BlockingIssueType.MISSING_CREDENTIALS
        if "environment variable" in lower or "not found" in lower and "claude" in lower:
            return BlockingIssueType.MISSING_ENV
        return BlockingIssueType.CODE_ERROR

    def _mark_feature_blocked(
        self,
        feature: Feature,
        *,
        reason: str,
        issue_type: BlockingIssueType,
        detected_by: str,
        context: dict | None = None,
        agent_id: str = "",
    ) -> None:
        self.feature_tracker.mark_blocked(feature.id, reason)
        issue = self.blocking_tracker._create_issue(
            issue_type=issue_type,
            feature_id=feature.id,
            description=reason,
            context=context or {},
            detected_by=detected_by,
        )
        if issue.issue_id not in feature.blocking_issues:
            feature.blocking_issues.append(issue.issue_id)
        self.execution_ledger.log_execution(
            feature_id=feature.id,
            status=ExecutionStatus.BLOCKED,
            agent_id=agent_id,
            error=reason,
        )
        self.repository.append_event(
            type="blocking_issue_created",
            feature_id=feature.id,
            issue_id=issue.issue_id,
            issue_type=issue.issue_type,
            description=issue.description,
        )

    def _verify_feature(self, feature: Feature, *, workspace_dir: Path | None = None) -> bool:
        """真正的验收验证：文件存在性 + 语法检查 + E2E 测试步骤"""
        target_dir = workspace_dir or self.project_dir
        self._log(f"开始验收 {feature.id} (目录: {target_dir})")

        # 1. 检查 Agent 产出的文件是否存在
        expected_files = self._infer_expected_files(feature, base_dir=target_dir)
        missing_files = [f for f in expected_files if not (target_dir / f).exists()]
        if missing_files:
            self._log(f"{feature.id} 验收失败：缺少文件 {missing_files}")
            return False

        # 2. 语法检查
        syntax_errors = self._run_syntax_checks(expected_files, base_dir=target_dir)
        if syntax_errors:
            self._log(f"{feature.id} 验收失败：语法错误 {syntax_errors}")
            return False

        # 3. 如果有测试步骤，运行 E2E 验证
        if feature.test_steps:
            e2e_passed = self._run_e2e_validation(feature.id, feature.test_steps)
            if not e2e_passed:
                self._log(f"{feature.id} E2E 验证未通过")
                return False

        self._log(f"{feature.id} 验收通过")
        return True

    def _infer_expected_files(self, feature: Feature, *, base_dir: Path | None = None) -> list[str]:
        """根据 feature 的类别推断应该产出的文件"""
        target = base_dir or self.project_dir
        category_file_map = {
            "backend": ["src/api/", "src/models/", "src/services/"],
            "frontend": ["src/components/", "src/pages/", "src/views/"],
            "database": ["migrations/", "src/models/", "src/db/"],
            "qa": ["tests/", "test/"],
            "security": ["src/middleware/", "src/auth/", "src/validators/"],
            "ui": ["src/components/", "src/styles/", "public/"],
            "docs": ["docs/", "README.md", "CHANGELOG.md"],
            "pm": ["docs/", "PRD.md", "prd.md"],
            "architect": ["docs/", "architecture.md", "DESIGN.md"],
        }

        dirs_to_check = category_file_map.get(feature.category, ["src/"])

        # 扫描项目目录，找出匹配类别的文件
        expected = []
        for dir_name in dirs_to_check:
            full_dir = target / dir_name
            if full_dir.is_dir():
                for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.md", "*.sql", "*.json"):
                    expected.extend([
                        str(p.relative_to(target))
                        for p in full_dir.rglob(ext)
                    ])

        # 至少检查根目录的关键文件
        for root_file in ("main.py", "app.py", "package.json", "requirements.txt", "pyproject.toml"):
            if (target / root_file).exists():
                expected.append(root_file)

        return expected

    def _run_syntax_checks(self, files: list[str], *, base_dir: Path | None = None) -> list[str]:
        """对文件运行语法检查"""
        target = base_dir or self.project_dir
        errors = []

        for file_path in files:
            full_path = target / file_path
            if not full_path.exists():
                continue

            if file_path.endswith(".py"):
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(full_path)],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    stderr = result.stderr.decode("utf-8", errors="replace")
                    errors.append(f"{file_path}: {stderr[:200]}")

            elif file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
                result = subprocess.run(
                    ["node", "--check", str(full_path)],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    stderr = result.stderr.decode("utf-8", errors="replace")
                    errors.append(f"{file_path}: {stderr[:200]}")

            elif file_path.endswith(".sql"):
                # SQL 文件基本检查：不为空且有内容
                content = full_path.read_text(encoding="utf-8").strip()
                if not content:
                    errors.append(f"{file_path}: 文件为空")

        return errors

    def _run_e2e_validation(self, feature_id: str, test_steps: list[str]) -> bool:
        """运行 E2E 验证测试步骤"""
        from testing.e2e_runner import E2ERunner

        runner = E2ERunner(project_dir=self.project_dir)
        result = runner.run_test_steps(feature_id, test_steps)
        return result.get("passed", False)

    def _generate_prd_and_features(self, user_request: str) -> tuple[str, list[Feature]]:
        """用Claude CLI生成PRD和Feature分解"""
        project_data = self.project_dir / "data"
        project_data.mkdir(parents=True, exist_ok=True)
        output_file = project_data / "prd.json"

        prompt = f"""你是一个资深产品经理和技术架构师。请严格按以下要求完成任务。

**重要任务：你必须生成一个JSON文件并写入指定路径，不要输出任何其他文字。**

用户需求：{user_request}

请完成以下任务：

1. 写一份简洁的PRD（产品需求文档），包含：
   - 产品概述
   - 核心功能
   - 技术选型建议
   - 非功能需求（性能、安全、可扩展性）

2. 将功能分解为具体的features，每个feature要求：
   - 足够小，一个Agent能在一次会话内完成
   - 有明确的验收标准
   - 标注依赖关系
   - 标注优先级（P0-P3）
   - 指定负责的Agent角色（backend/frontend/database/qa/ui/security/docs）

**你必须将以下JSON内容写入文件：{output_file}**

JSON结构：
{{
  "prd_summary": "PRD内容字符串",
  "features": [
    {{
      "id": "F001",
      "category": "backend",
      "description": "用户可以注册账号",
      "priority": "P0",
      "assigned_to": "backend",
      "dependencies": [],
      "test_steps": ["访问注册页面", "填写表单", "提交成功"]
    }}
  ]
}}

确保features按合理的执行顺序排列，依赖关系正确。
**只执行一个操作：将JSON写入 {output_file}，不要输出任何其他内容。**"""

        # 执行前安全检查
        pre_check = self.permission_guard.check_prompt(prompt)
        if not pre_check.allowed:
            violations = [v.detail for v in pre_check.blocked_violations]
            raise RuntimeError(f"PRD generation blocked by permission guard: {violations}")

        full_prompt = prompt + "\n\n" + PERMISSION_RULES_PROMPT

        result = subprocess.run(
            ["claude", "-p", full_prompt, "--permission-mode", "acceptEdits"],
            capture_output=True,
            timeout=300,
            cwd=str(self.project_dir),
        )

        stderr_text = result.stderr.decode("utf-8", errors="replace")

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI PRD generation failed (rc={result.returncode}): {stderr_text}")

        # 等待文件写入完成（模型可能异步写入）
        import time
        max_wait = 30
        waited = 0
        while not output_file.exists() and waited < max_wait:
            time.sleep(1)
            waited += 1

        if not output_file.exists():
            raise RuntimeError(f"Claude CLI did not write JSON to {output_file}. stderr: {stderr_text[:500]}")

        json_str = output_file.read_text(encoding="utf-8")
        if not json_str.strip():
            raise RuntimeError(f"Claude CLI wrote empty JSON to {output_file}")

        data = json.loads(json_str)
        prd_summary = data["prd_summary"]
        features = [Feature(**f) for f in data["features"]]

        return prd_summary, features

    def _ensure_all_roles(self) -> None:
        """确保所有已知角色都有足够数量的 agent 实例。"""
        for role, count in ROLE_INSTANCE_COUNTS.items():
            if role in AGENT_ROLES:
                self.pool.ensure_instances(role, count)

    def _init_git(self) -> None:
        """初始化git仓库"""
        try:
            subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=self.project_dir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", GIT_AUTHOR_NAME],
                cwd=self.project_dir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", GIT_AUTHOR_EMAIL],
                cwd=self.project_dir,
                capture_output=True,
            )
            progress.log("git仓库初始化完成")
        except subprocess.CalledProcessError:
            # 可能已经初始化过了
            pass

    def _git_commit(self, message: str) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.project_dir,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", message, "--allow-empty"],
                cwd=self.project_dir,
                capture_output=True,
                check=True,
            )
            progress.log(f"git commit: {message}")
            return True
        except subprocess.CalledProcessError:
            return False

    def _log(self, message: str) -> None:
        progress.log(f"[PM] {message}")

    def get_status(self) -> dict:
        """获取当前项目状态"""
        return {
            "initialized": self._initialized,
            "features": self.feature_tracker.summary(),
            "progress": self.feature_tracker.summary(),
        }

    def chat_response(self, user_message: str, chat_history: list, repository) -> str:
        """处理用户对话消息，调用 Claude Code 生成 PM 回复。

        Args:
            user_message: 用户最新消息
            chat_history: 完整对话历史
            repository: 状态仓库，用于获取当前项目上下文

        Returns:
            PM 回复内容字符串
        """
        import os
        import subprocess
        import tempfile

        # 构建项目上下文
        status = self.get_status()
        features = self.feature_tracker.all_features()
        feature_summary = "\n".join(
            f"- {f.id} ({f.category}): {f.description} [{f.status}]"
            for f in features[:20]  # 最多取20个避免 prompt 过长
        )

        # 构建对话历史上下文
        history_lines = []
        for msg in chat_history[:-1]:  # 排除最新消息（即用户消息本身）
            role = "用户" if msg.role == "user" else "PM"
            history_lines.append(f"{role}: {msg.content}")
        history_text = "\n".join(history_lines) if history_lines else "（无历史对话）"

        prompt = f"""你是一个AI软件开发团队的项目经理（PM）。你的职责是：
1. 理解用户的需求和指令
2. 管理开发团队的进度和状态
3. 做出技术决策和任务分配
4. 回答关于项目状态的问题

## 当前项目状态

已初始化: {status['initialized']}
Features 总计: {status['features']['total']}
已完成: {status['features']['done']}
进行中: {status['features']['in_progress']}
待执行: {status['features']['pending']}
被阻塞: {status['features']['blocked']}

## Feature 列表

{feature_summary or "（暂无 Feature）"}

## 最近对话历史

{history_text}

## 用户最新消息

{user_message}

请根据当前项目状态和对话历史，用中文回复用户。回复要简洁、专业、有建设性。
如果用户提到了具体的开发需求，请说明你将如何安排团队执行。"""

        # 将 prompt 写入临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            result = subprocess.run(
                ["claude", "--print", "-p", prompt_file],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.project_dir),
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                error_detail = result.stderr.strip()[:200] if result.stderr else "未知错误"
                return f"PM 处理消息时出错: {error_detail}"
        except subprocess.TimeoutExpired:
            return "PM 处理消息超时，请稍后重试"
        except Exception as e:
            return f"PM 处理消息时出错: {e}"
        finally:
            with contextlib.suppress(OSError):
                os.unlink(prompt_file)
