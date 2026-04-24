"""Feature 验收服务 — 从 ProjectManager 拆分的验证逻辑"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.feature_tracker import Feature

logger = logging.getLogger(__name__)


class FeatureVerificationService:
    """负责单个 Feature 的验收流程：文件存在性 + 语法检查 + E2E 验证。"""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = Path(project_dir).resolve()

    def verify(self, feature: Feature, *, workspace_dir: Path | None = None) -> bool:
        """验收 Feature 产出。

        Args:
            feature: Feature 对象
            workspace_dir: Agent 隔离工作目录，不传则使用 project_dir

        Returns:
            True 表示验收通过，False 表示不通过
        """
        target_dir = workspace_dir or self._project_dir
        logger.info("开始验收 %s (目录: %s)", feature.id, target_dir)

        expected_files = self._infer_expected_files(feature, base_dir=target_dir)
        missing_files = [f for f in expected_files if not (target_dir / f).exists()]
        if missing_files:
            logger.warning("%s 验收失败：缺少文件 %s", feature.id, missing_files)
            return False

        syntax_errors = self._run_syntax_checks(expected_files, base_dir=target_dir)
        if syntax_errors:
            logger.warning("%s 验收失败：语法错误 %s", feature.id, syntax_errors)
            return False

        if getattr(feature, "test_steps", []):
            e2e_passed = self._run_e2e_validation(feature.id, feature.test_steps)
            if not e2e_passed:
                logger.warning("%s E2E 验证未通过", feature.id)
                return False

        logger.info("%s 验收通过", feature.id)
        return True

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
                    ["python", "-m", "py_compile", str(full_path)],
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

    def _run_e2e_validation(self, feature_id: str, test_steps: list[str]) -> bool:
        """运行 E2E 验证测试步骤。"""
        try:
            from testing.e2e_runner import E2ERunner
        except ImportError:
            logger.warning("testing.e2e_runner 不可用，跳过 E2E 验证")
            return True

        runner = E2ERunner(project_dir=self._project_dir)
        result = runner.run_test_steps(feature_id, test_steps)
        return result.get("passed", False)
