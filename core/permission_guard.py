"""Permission Guard — 操作安全等级控制

文档依据：
- MVP 清单 §11 安全验收清单
- AI 协议 §11 阻塞机制
- PRD §8.8 权限和安全："允许安全无人值守，禁止危险无人值守"

安全等级：
- ALLOWED: 读取项目文件、修改范围内代码、创建文件、运行测试/lint/build → 自动放行
- PROTECTED: 删除单个项目文件 → 先备份再执行
- BLOCKED: 批量删除、越界修改、系统级危险操作 → 阻塞并记录
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    ALLOWED = "allowed"
    PROTECTED = "protected"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PermissionViolation:
    level: SafetyLevel
    operation: str
    detail: str
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PermissionCheckResult:
    allowed: bool
    violations: list[PermissionViolation] = field(default_factory=list)

    @property
    def blocked_violations(self) -> list[PermissionViolation]:
        return [v for v in self.violations if v.level == SafetyLevel.BLOCKED]

    @property
    def protected_violations(self) -> list[PermissionViolation]:
        return [v for v in self.violations if v.level == SafetyLevel.PROTECTED]


# 批量删除阈值
BULK_DELETE_THRESHOLD = 5

# 危险文件模式（对齐 MVP §11 "需要保护" 清单）
DANGEROUS_FILE_PATTERNS = [
    r"\.env",
    r"\.env\.",
    r"credentials",
    r"secret",
    r"\.pem$",
    r"\.key$",
    r"id_rsa",
    r"id_ed25519",
]

# 危险命令模式（对齐 MVP §11 "需要保护" 清单）
DANGEROUS_COMMAND_PATTERNS = [
    r"\bDROP\s+TABLE\b",
    r"\bDROP\s+DATABASE\b",
    r"\bTRUNCATE\b",
    r"\bDELETE\s+FROM\b.*\bWHERE\b.*1\s*=\s*1",
    r"\brm\s+-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bgit\s+push\s+.*--force\b",
    r"\bnpm\s+publish\b",
    r"\bpip\s+publish\b",
    r"\bdocker\s+push\b",
    r"\bkubectl\s+delete\b",
]

# 发布命令模式
DEPLOY_COMMAND_PATTERNS = [
    r"\bvercel\s+deploy\b",
    r"\bnetlify\s+deploy\b",
    r"\baws\s+deploy\b",
    r"\bgcloud\s+.*deploy\b",
    r"\bfly\s+deploy\b",
    r"\bheroku\s+",
]


class PermissionGuard:
    """操作安全等级检查器。

    在执行前和执行后两个时机检查：
    - 执行前：检查 prompt 中是否包含危险命令
    - 执行后：检查 git diff 是否有越界修改或批量删除
    """

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = Path(project_dir).resolve()

    def check_prompt(self, prompt: str) -> PermissionCheckResult:
        """执行前检查：扫描 prompt 中的危险命令。"""
        violations: list[PermissionViolation] = []

        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                violations.append(PermissionViolation(
                    level=SafetyLevel.BLOCKED,
                    operation="dangerous_command_in_prompt",
                    detail=f"prompt 中包含危险命令模式: {pattern}",
                ))

        for pattern in DEPLOY_COMMAND_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                violations.append(PermissionViolation(
                    level=SafetyLevel.BLOCKED,
                    operation="deploy_command_in_prompt",
                    detail=f"prompt 中包含发布命令: {pattern}",
                ))

        return PermissionCheckResult(
            allowed=not any(v.level == SafetyLevel.BLOCKED for v in violations),
            violations=violations,
        )

    def check_diff(self, workspace_dir: Path | None = None) -> PermissionCheckResult:
        """执行后检查：扫描 git diff 检测越界修改和批量删除。"""
        import subprocess

        target_dir = workspace_dir or self._project_dir
        violations: list[PermissionViolation] = []

        # 获取变更文件列表
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files = [f for f in result.stdout.strip().split("\n") if f]
        except subprocess.CalledProcessError:
            return PermissionCheckResult(allowed=True)

        if not changed_files:
            return PermissionCheckResult(allowed=True)

        # 检查批量删除（MVP §12 停止条件：发现大规模删除）
        deleted_files = self._detect_deleted_files(target_dir, changed_files)
        if len(deleted_files) >= BULK_DELETE_THRESHOLD:
            violations.append(PermissionViolation(
                level=SafetyLevel.BLOCKED,
                operation="bulk_delete",
                detail=f"批量删除 {len(deleted_files)} 个文件（阈值 {BULK_DELETE_THRESHOLD}）",
                files=deleted_files,
            ))

        # 检查单文件删除（MVP §11：需要保护）
        single_deletes = [f for f in deleted_files if f not in (
            deleted_files[:BULK_DELETE_THRESHOLD] if len(deleted_files) >= BULK_DELETE_THRESHOLD else []
        )]
        if single_deletes and len(deleted_files) < BULK_DELETE_THRESHOLD:
            for f in single_deletes:
                violations.append(PermissionViolation(
                    level=SafetyLevel.PROTECTED,
                    operation="single_file_delete",
                    detail=f"删除单个文件: {f}",
                    files=[f],
                ))

        # 检查越界修改（修改项目目录外的文件）
        for f in changed_files:
            full_path = (target_dir / f).resolve()
            if not str(full_path).startswith(str(self._project_dir)):
                violations.append(PermissionViolation(
                    level=SafetyLevel.BLOCKED,
                    operation="out_of_bounds_modify",
                    detail=f"修改项目目录外的文件: {f}",
                    files=[f],
                ))

        # 检查危险文件修改（MVP §11：修改密钥/环境变量）
        for f in changed_files:
            for pattern in DANGEROUS_FILE_PATTERNS:
                if re.search(pattern, f, re.IGNORECASE):
                    violations.append(PermissionViolation(
                        level=SafetyLevel.BLOCKED,
                        operation="dangerous_file_modify",
                        detail=f"修改敏感文件: {f}",
                        files=[f],
                    ))
                    break

        return PermissionCheckResult(
            allowed=not any(v.level == SafetyLevel.BLOCKED for v in violations),
            violations=violations,
        )

    def backup_file(self, file_path: Path, workspace_dir: Path | None = None) -> Path | None:
        """PROTECTED 操作：备份单个文件到 .ralph/backups/。"""
        target_dir = workspace_dir or self._project_dir
        backup_dir = target_dir / ".ralph" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        if not file_path.exists():
            return None

        backup_path = backup_dir / file_path.name
        # 避免覆盖已有备份
        counter = 1
        while backup_path.exists():
            backup_path = backup_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
            counter += 1

        shutil.copy2(file_path, backup_path)
        logger.info("已备份文件 %s -> %s", file_path, backup_path)
        return backup_path

    def _detect_deleted_files(self, workspace_dir: Path, changed_files: list[str]) -> list[str]:
        """检测被删除的文件。"""
        deleted = []
        for f in changed_files:
            full_path = workspace_dir / f
            if not full_path.exists():
                deleted.append(f)
        return deleted


# 注入到 prompt 的权限规则文本
PERMISSION_RULES_PROMPT = """
## 安全权限规则（系统强制）

以下操作是 **禁止** 的，不要执行：
- 批量删除文件（>=5个）
- 修改项目目录外的任何文件
- 修改 .env、credentials、密钥等敏感文件
- 执行数据库 DROP/TRUNCATE 操作
- 执行 git push --force
- 执行任何发布命令（npm publish、pip publish、vercel deploy 等）
- 执行 rm -rf 等不可逆删除

以下操作需要 **谨慎** 执行：
- 删除单个文件前，确保有备份或 git 可恢复
- 修改配置文件前，说明修改原因

以下操作是 **允许** 的：
- 创建、修改项目范围内的代码文件
- 运行测试、lint、typecheck、build
- 创建新文件和目录
- 读取任何项目文件
"""
