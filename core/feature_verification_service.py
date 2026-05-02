"""Feature 验收服务 — 从 ProjectManager 拆分的验证逻辑"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from core.verification_result import VerificationResult

if TYPE_CHECKING:
    from core.feature_tracker import Feature

logger = logging.getLogger(__name__)


class FeatureVerificationService:
    """负责单个 Feature 的验收流程：文件存在性 + 语法检查 + E2E 验证。"""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = Path(project_dir).resolve()

    def verify(self, feature: Feature, *, workspace_dir: Path | None = None) -> VerificationResult:
        """验收 Feature 产出。

        返回 VerificationResult，实现 __bool__ 保持向后兼容：
            if service.verify(feature):  # 继续有效

        Args:
            feature: Feature 对象
            workspace_dir: Agent 隔离工作目录，不传则使用 project_dir

        Returns:
            VerificationResult 包含详细的验收信息
        """
        target_dir = workspace_dir or self._project_dir
        logger.info("开始验收 %s (目录: %s)", feature.id, target_dir)

        expected_files = self._infer_expected_files(feature, base_dir=target_dir)
        missing_files = [f for f in expected_files if not (target_dir / f).exists()]
        syntax_errors = self._run_syntax_checks(expected_files, base_dir=target_dir)

        # 收集 diff 摘要
        diff_summary = self._collect_diff_summary(target_dir)

        # E2E 验证：runner 不可用时返回 None（不默认通过）
        e2e_result: bool | None = None
        if getattr(feature, "test_steps", []):
            e2e_result = self._run_e2e_validation(feature.id, feature.test_steps)

        # 判定：文件缺失、语法错误、E2E 失败 → 不通过
        # 有 test_steps 但 E2E runner 不可用（None）→ 不通过（不静默放行）
        has_test_steps = bool(getattr(feature, "test_steps", []))
        passed = (
            not missing_files
            and not syntax_errors
            and e2e_result is not False
            and not (e2e_result is None and has_test_steps)
        )

        if passed:
            logger.info("%s 验收通过", feature.id)
        else:
            reasons = []
            if missing_files:
                reasons.append(f"缺少文件: {missing_files}")
            if syntax_errors:
                reasons.append(f"语法错误: {syntax_errors}")
            if e2e_result is None and getattr(feature, "test_steps", []):
                reasons.append("E2E runner 不可用")
            elif e2e_result is False:
                reasons.append("E2E 验证未通过")
            logger.warning("%s 验收失败：%s", feature.id, reasons)

        return VerificationResult(
            passed=passed,
            files_checked=expected_files,
            syntax_errors=syntax_errors,
            e2e_result=e2e_result,
            diff_summary=diff_summary,
        )

    def _infer_expected_files(self, feature: Feature, *, base_dir: Path | None = None) -> list[str]:
        """根据 feature 的类别推断应该产出的文件。"""
        target = base_dir or self._project_dir
        category_file_map: dict[str, list[str]] = {
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

        expected: list[str] = []
        for dir_name in dirs_to_check:
            full_dir = target / dir_name
            if full_dir.is_dir():
                for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.md", "*.sql", "*.json"):
                    expected.extend([
                        str(p.relative_to(target))
                        for p in full_dir.rglob(ext)
                    ])

        for root_file in ("main.py", "app.py", "package.json", "requirements.txt", "pyproject.toml"):
            if (target / root_file).exists():
                expected.append(root_file)

        return expected

    def _run_syntax_checks(self, files: list[str], *, base_dir: Path | None = None) -> list[str]:
        """对文件运行语法检查。"""
        target = base_dir or self._project_dir
        errors: list[str] = []

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
                content = full_path.read_text(encoding="utf-8").strip()
                if not content:
                    errors.append(f"{file_path}: 文件为空")

        return errors

    def _collect_diff_summary(self, target_dir: Path) -> str:
        """收集 git diff --stat 作为验收证据。"""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _run_e2e_validation(self, feature_id: str, test_steps: list[str]) -> bool | None:
        """运行 E2E 验证测试步骤。

        Returns:
            True = 通过, False = 未通过, None = runner 不可用
        """
        try:
            from testing.e2e_runner import E2ERunner
        except ImportError:
            logger.warning("testing.e2e_runner 不可用，E2E 验证无法执行")
            return None

        runner = E2ERunner(project_dir=self._project_dir)
        result = runner.run_test_steps(feature_id, test_steps)
        return result.get("passed", False)
