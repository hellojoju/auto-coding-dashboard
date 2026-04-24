"""PMCoordinator：在 ProjectManager 执行循环中插入审批闸门，实现 pause-and-wait-approval。

数据流：
  Agent 执行完成 → 写入 waiting_approval 状态到 Repository → EventBus 推送事件 → WebSocket → 前端
  用户在前端审批 → REST API → Command 写入 Repository → CommandConsumer 消费 → PMCoordinator 处理 → 继续/驳回
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from dashboard.event_bus import EventBus
from dashboard.models import Command
from dashboard.state_repository import ProjectStateRepository
from dashboard.silence_detector import SilenceDetector
from dashboard.agent_process_manager import AgentProcessManager
from core.blocking_tracker import BlockingIssueType
from core.blocking_tracker import BlockingTracker
from core.execution_ledger import ExecutionStatus

if TYPE_CHECKING:
    from agents.pool import AgentInstance
    from core.feature_tracker import Feature, FeatureTracker
    from core.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class PMCoordinator:
    """包装 ProjectManager 的执行流程，在每步之间插入审批闸门。

    职责：
    1. 代理 feature 执行（调用 ProjectManager._execute_feature 的子步骤）
    2. 执行完成后写入 waiting_approval 状态
    3. 等待用户审批（通过 Command 系统）
    4. 根据审批结果决定继续验收 or 驳回重做
    5. 同步模块分配状态到 Repository
    """

    def __init__(
        self,
        project_manager: "ProjectManager",
        repository: ProjectStateRepository,
        event_bus: EventBus,
        approval_timeout: float = 3600.0,  # 审批超时 1 小时
    ) -> None:
        self._pm = project_manager
        self._repo = repository
        self._event_bus = event_bus
        self._approval_timeout = approval_timeout
        self._exec_thread: Optional[threading.Thread] = None
        self._exec_status: str = "idle"
        self._stop_event = threading.Event()
        self._exec_error: Optional[str] = None

        # 统一 ProjectManager 与 Coordinator 的状态事实源
        self._pm.repository = repository
        self._pm.blocking_tracker = BlockingTracker(repository)

        # 静默检测：为每个 agent 角色创建检测器
        self._silence_detectors: dict[str, SilenceDetector] = {}
        self._setup_silence_detectors()

        # Agent 进程管理
        self._process_manager = AgentProcessManager()

    def _setup_silence_detectors(self) -> None:
        """为所有 agent 角色创建静默检测器。"""
        from agents import AGENT_ROLES
        from core.config import (
            SILENCE_WARNING_THRESHOLD,
            SILENCE_NOTIFY_THRESHOLD,
            SILENCE_INTERVENTION_THRESHOLD,
        )

        for role in AGENT_ROLES:
            detector = SilenceDetector(
                agent_id=role,
                warning_threshold=SILENCE_WARNING_THRESHOLD,
                notify_threshold=SILENCE_NOTIFY_THRESHOLD,
                intervention_threshold=SILENCE_INTERVENTION_THRESHOLD,
                on_warning=self._on_silence_warning,
                on_notify=self._on_silence_notify,
                on_intervention=self._on_silence_intervention,
            )
            self._silence_detectors[role] = detector

    def _on_silence_warning(self, agent_id: str, idle_seconds: float) -> None:
        """静默 warning 回调。"""
        self._event_bus.emit(
            "agent_silence_warning",
            agent_id=agent_id,
            idle_seconds=int(idle_seconds),
            message=f"{agent_id} 已静默 {int(idle_seconds)} 秒",
        )

    def _on_silence_notify(self, agent_id: str, idle_seconds: float) -> None:
        """静默 notify 回调。"""
        self._event_bus.emit(
            "agent_silence_notify",
            agent_id=agent_id,
            idle_seconds=int(idle_seconds),
            message=f"{agent_id} 已静默 {int(idle_seconds)} 秒，需要关注",
        )

    def _on_silence_intervention(self, agent_id: str, idle_seconds: float) -> None:
        """静默 intervention 回调。"""
        self._event_bus.emit(
            "agent_silence_intervention",
            agent_id=agent_id,
            idle_seconds=int(idle_seconds),
            message=f"{agent_id} 已静默 {int(idle_seconds)} 秒，需要 PM 干预",
        )

    def record_agent_activity(self, agent_id: str) -> None:
        """记录 agent 活动，重置静默计时器。"""
        detector = self._silence_detectors.get(agent_id)
        if detector:
            detector.record_activity()

    def get_all_silence_status(self) -> dict[str, dict]:
        """获取所有 agent 的静默检测状态。"""
        return {
            role: det.get_status()
            for role, det in self._silence_detectors.items()
        }

    def get_process_manager(self) -> AgentProcessManager:
        """返回 Agent 进程管理器。"""
        return self._process_manager

    # --- 执行循环入口 ---

    def run_coordinated_loop(self) -> dict:
        """带审批闸门的执行循环，替代 ProjectManager.run_execution_loop。"""
        from core.progress_logger import progress

        progress.log("开始带审批的执行循环")

        tracker = self._pm.feature_tracker
        iteration = 0
        from core.config import MAX_RETRY_COUNT

        max_iterations = len(tracker.all_features()) * MAX_RETRY_COUNT + 10

        while not tracker.all_done():
            if self._stop_event.is_set():
                progress.log("收到停止信号，终止执行循环")
                break

            iteration += 1
            if iteration > max_iterations:
                progress.log(f"达到最大迭代次数 {max_iterations}，停止执行")
                break

            feature = tracker.get_next_ready()
            if not feature:
                blocked = [f for f in tracker.all_features() if f.status == "blocked"]
                if blocked:
                    progress.log(f"所有待执行 feature 都被阻塞: {[f.id for f in blocked]}")
                    break
                break

            self._execute_with_approval(feature)
            self._sync_state_to_repository()

        return tracker.summary()

    # --- 带审批的单步执行 ---

    def _execute_with_approval(self, feature: "Feature") -> None:
        """执行单个 feature，完成后暂停等待审批。"""
        from agents import AGENT_ROLES
        from core.progress_logger import progress

        tracker = self._pm.feature_tracker
        tracker.mark_in_progress(feature.id, instance_id="", workspace_path="")
        self._pm._sync_feature_to_repository(feature, event_type="feature_updated")

        if feature.assigned_to not in AGENT_ROLES:
            self._pm._mark_feature_blocked(
                feature,
                reason=f"未知角色: {feature.assigned_to}",
                issue_type=BlockingIssueType.CODE_ERROR,
                detected_by="coordinator",
                context={"assigned_to": feature.assigned_to},
            )
            return

        pool = self._pm.pool
        result_pair = pool.acquire(feature.assigned_to)
        if result_pair is None:
            feature.status = "pending"
            tracker._save()
            return

        instance, agent = result_pair
        instance.current_task_id = feature.id
        tracker.mark_in_progress(feature.id, instance_id=instance.instance_id, workspace_path=str(instance.workspace_path))
        self._pm._sync_feature_to_repository(feature, event_type="feature_updated")
        self._pm._sync_agent_instance(instance, status="busy", current_feature=feature.id)
        self._pm.execution_ledger.log_execution(
            feature_id=feature.id,
            status=ExecutionStatus.STARTED,
            agent_id=instance.instance_id,
        )

        try:
            import asyncio

            result = asyncio.run(self._pm.feature_execution.execute(
                feature,
                agent,
                prd_summary=self._pm._get_prd_summary(),
                dependencies_context=self._pm._get_deps_context(feature),
            ))

            task_success = result.get("success", False)

            if task_success:
                # 执行成功 → 写入 waiting_approval 状态，暂停等待审批
                self._request_approval(instance, feature)
                approved = self._wait_for_approval(feature.id, instance.instance_id)

                if approved:
                    # 用户审批通过 → 验收
                    tracker.mark_review(feature.id)
                    self._pm._sync_feature_to_repository(feature, event_type="feature_updated")
                    passed = self._pm.feature_verification.verify(feature)
                    if passed:
                        files_changed = result.get("files_changed") or []
                        tracker.mark_done(feature.id, files_changed=files_changed)
                        self._pm._sync_feature_to_repository(feature, event_type="feature_updated")
                        self._pm.execution_ledger.log_execution(
                            feature_id=feature.id,
                            status=ExecutionStatus.COMPLETED,
                            agent_id=instance.instance_id,
                            files_changed=files_changed,
                        )
                        self._pm.git_service.commit(f"feat: {feature.id} - {feature.description}")
                        pool.release(instance.instance_id, task_success=True)
                        released = pool.get_instance(instance.instance_id)
                        if released is not None:
                            self._pm._sync_agent_instance(released, status=released.status, current_feature=None)
                        self._event_bus.emit("feature_done", feature_id=feature.id)
                    else:
                        retry_count = len(feature.error_log)
                        if retry_count < MAX_RETRY_COUNT:
                            tracker.add_error(feature.id, "验收不通过，退回重做")
                            feature.status = "pending"
                            tracker._save()
                            self._pm._sync_feature_to_repository(feature, event_type="feature_updated")
                            self._pm.execution_ledger.log_execution(
                                feature_id=feature.id,
                                status=ExecutionStatus.RETRYING,
                                agent_id=instance.instance_id,
                                error="验收不通过，退回重做",
                            )
                            pool.release(instance.instance_id, task_success=False)
                            released = pool.get_instance(instance.instance_id)
                            if released is not None:
                                self._pm._sync_agent_instance(released, status=released.status, current_feature=None)
                        else:
                            self._pm._mark_feature_blocked(
                                feature,
                                reason=f"验收不通过，已重试{MAX_RETRY_COUNT}次",
                                issue_type=BlockingIssueType.CODE_ERROR,
                                detected_by="verification",
                                context={"stage": "verification"},
                                agent_id=instance.instance_id,
                            )
                            pool.release(instance.instance_id, task_success=False)
                            released = pool.get_instance(instance.instance_id)
                            if released is not None:
                                self._pm._sync_agent_instance(released, status=released.status, current_feature=None)
                else:
                    # 用户驳回
                    tracker.add_error(feature.id, "PM 驳回：需求不符合预期")
                    feature.status = "pending"
                    tracker._save()
                    self._pm._sync_feature_to_repository(feature, event_type="feature_updated")
                    self._pm.execution_ledger.log_execution(
                        feature_id=feature.id,
                        status=ExecutionStatus.RETRYING,
                        agent_id=instance.instance_id,
                        error="PM 驳回：需求不符合预期",
                    )
                    pool.release(instance.instance_id, task_success=False)
                    released = pool.get_instance(instance.instance_id)
                    if released is not None:
                        self._pm._sync_agent_instance(released, status=released.status, current_feature=None)
                    self._event_bus.emit("feature_rejected", feature_id=feature.id)
            else:
                error = result.get("error", "未知错误")
                tracker.add_error(feature.id, error)
                retry_count = len(feature.error_log)
                if retry_count >= MAX_RETRY_COUNT:
                    self._pm._mark_feature_blocked(
                        feature,
                        reason=f"执行失败{MAX_RETRY_COUNT}次: {error}",
                        issue_type=self._pm._infer_blocking_issue_type(error),
                        detected_by="agent",
                        context={"error": error},
                        agent_id=instance.instance_id,
                    )
                else:
                    feature.status = "pending"
                    tracker._save()
                    self._pm._sync_feature_to_repository(feature, event_type="feature_updated")
                    self._pm.execution_ledger.log_execution(
                        feature_id=feature.id,
                        status=ExecutionStatus.RETRYING,
                        agent_id=instance.instance_id,
                        error=error,
                    )
                pool.release(instance.instance_id, task_success=False)
                released = pool.get_instance(instance.instance_id)
                if released is not None:
                    self._pm._sync_agent_instance(released, status=released.status, current_feature=None)

        except Exception as e:
            tracker.add_error(feature.id, str(e))
            pool.release(instance.instance_id, task_success=False)
            released = pool.get_instance(instance.instance_id)
            if released is not None:
                self._pm._sync_agent_instance(released, status=released.status, current_feature=None)
            raise

    # --- 审批闸门 ---

    def _request_approval(self, instance: "AgentInstance", feature: "Feature") -> None:
        """写入 waiting_approval 状态，通知前端。"""
        # 同步 Agent 状态到 Repository
        from dashboard.models import AgentInstance as DashboardAgent

        dashboard_agent = DashboardAgent(
            id=instance.instance_id,
            role=instance.role,
            instance_number=int(instance.instance_id.split("-")[-1]) if "-" in instance.instance_id else 1,
            status="waiting_approval",
            current_feature=feature.id,
            workspace_id=instance.workspace_id,
            workspace_path=str(instance.workspace_path),
            total_tasks_completed=instance.total_tasks_completed,
        )
        self._repo.upsert_agent(dashboard_agent)

        # 发送事件
        self._event_bus.emit(
            "waiting_approval",
            agent_id=instance.instance_id,
            feature_id=feature.id,
            message=f"{instance.instance_id} 完成了 {feature.id}，等待审批",
        )

    def _wait_for_approval(self, feature_id: str, agent_id: str) -> bool:
        """轮询 Repository 中的 Command，等待用户审批。

        返回 True 表示审批通过，False 表示驳回或超时。
        """
        start = time.monotonic()
        poll_interval = 0.5  # 500ms
        command_aliases = {
            "approve_decision": "approve",
            "reject_decision": "reject",
        }

        while time.monotonic() - start < self._approval_timeout:
            # 查找针对此 feature/agent 的审批命令
            for cmd in self._repo.list_commands_by_status("accepted", "rejected", "applied"):
                if cmd.target_id == feature_id or cmd.target_id == agent_id:
                    cmd_type = command_aliases.get(cmd.type, cmd.type)
                    if cmd_type == "approve" and cmd.status in ("accepted", "applied"):
                        return True
                    elif cmd_type == "reject" and cmd.status == "rejected":
                        return False

            time.sleep(poll_interval)

        # 超时默认驳回
        logger.warning(f"审批超时: feature={feature_id}, agent={agent_id}")
        return False

    # --- 状态同步 ---

    def _sync_state_to_repository(self) -> None:
        """将当前 pool 和 feature 状态同步到 Repository。"""
        pool_status = self._pm.pool.get_status()
        for agent_dict in pool_status.get("agents", []):
            from dashboard.models import AgentInstance as DashboardAgent

            dashboard_agent = DashboardAgent(
                id=agent_dict["instance_id"],
                role=agent_dict["role"],
                instance_number=int(agent_dict["instance_id"].split("-")[-1]) if "-" in agent_dict["instance_id"] else 1,
                status=agent_dict["status"],
                workspace_id=agent_dict["workspace_id"],
                workspace_path=agent_dict["workspace_path"],
                total_tasks_completed=agent_dict["total_tasks_completed"],
            )
            self._repo.upsert_agent(dashboard_agent)

    # --- 线程安全执行控制 ---

    def start_execution(self) -> dict:
        """在后台线程启动协调循环。非阻塞。"""
        if self._exec_status == "running":
            return {"success": False, "error": "执行已在运行中"}

        self._stop_event.clear()
        self._exec_status = "starting"
        self._exec_error = None

        self._exec_thread = threading.Thread(
            target=self._run_in_background,
            daemon=True,
            name="pm-coordinator",
        )
        self._exec_thread.start()

        return {"success": True, "status": "starting"}

    def _run_in_background(self) -> None:
        """后台线程入口，包装 run_coordinated_loop。"""
        try:
            self._exec_status = "running"
            self.run_coordinated_loop()
            if self._stop_event.is_set():
                self._exec_status = "idle"
            else:
                self._exec_status = "completed"
        except Exception as e:
            self._exec_error = str(e)
            self._exec_status = "error"
            logger.exception("PMCoordinator background thread error")

    def stop_execution(self) -> dict:
        """请求停止后台执行循环。"""
        if self._exec_status != "running":
            return {"success": False, "error": f"当前状态为 {self._exec_status}，无法停止"}

        self._stop_event.set()
        if self._exec_thread and self._exec_thread.is_alive():
            self._exec_thread.join(timeout=5.0)

        self._exec_status = "idle"
        return {"success": True, "status": "idle"}

    def get_execution_status(self) -> dict:
        """返回当前执行状态。"""
        return {
            "status": self._exec_status,
            "thread_alive": self._exec_thread.is_alive() if self._exec_thread else False,
            "error": self._exec_error,
        }
