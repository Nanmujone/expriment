"""Backup-gated, dry-run-first Alembic migration execution."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config

from alembic import command
from english_player.infrastructure.persistence.errors import DEFAULT_REQUIRED_FREE_BYTES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class BackupVerificationCredential:
    """Evidence produced by the application layer after a backup is verified."""

    source_database: Path
    source_sha256: str
    backup_path: Path
    backup_sha256: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class MigrationPreflightResult:
    allowed: bool
    error_code: str | None
    user_message: str
    required_bytes: int
    available_bytes: int
    cleanup_action: str | None = None


@dataclass(frozen=True, slots=True)
class MigrationDryRunResult:
    allowed: bool
    error_code: str | None
    user_message: str
    integrity_check: str | None
    required_bytes: int
    cleanup_action: str | None = None


@dataclass(frozen=True, slots=True)
class MigrationExecutionResult:
    succeeded: bool
    error_code: str | None
    user_message: str
    retryable: bool
    required_bytes: int
    cleanup_action: str | None = None


class MigrationPreflight:
    """Validate backup evidence and migration disk-space budget without modifying data."""

    def __init__(
        self,
        database_path: Path,
        *,
        available_bytes: Callable[[], int] | None = None,
    ) -> None:
        self._database_path = database_path.resolve()
        self._available_bytes = available_bytes or (
            lambda: shutil.disk_usage(self._database_path.parent).free
        )

    def required_bytes(self, backup_size: int = 0) -> int:
        source_size = self._database_path.stat().st_size if self._database_path.exists() else 0
        return max(DEFAULT_REQUIRED_FREE_BYTES, source_size * 3 + backup_size)

    def evaluate(self, credential: BackupVerificationCredential | None) -> MigrationPreflightResult:
        available = self._available_bytes()
        required = self.required_bytes(
            credential.backup_path.stat().st_size
            if credential is not None and credential.backup_path.is_file()
            else 0
        )
        if credential is None:
            return MigrationPreflightResult(
                False,
                "backup_credential_required",
                "升级前必须提供已验证备份凭据。现有数据库未被修改。",
                required,
                available,
            )
        if credential.source_database.resolve() != self._database_path:
            return MigrationPreflightResult(
                False,
                "backup_source_mismatch",
                "备份凭据不属于当前数据库。现有数据库未被修改。",
                required,
                available,
            )
        if not self._database_path.is_file() or not credential.backup_path.is_file():
            return MigrationPreflightResult(
                False,
                "backup_missing",
                "数据库或已验证备份不存在。现有数据库未被修改。",
                required,
                available,
            )
        if (
            credential.backup_path.resolve() == self._database_path
            or not credential.schema_version
            or _sha256(self._database_path) != credential.source_sha256
        ):
            return MigrationPreflightResult(
                False,
                "backup_source_mismatch",
                "数据库已在备份验证后发生变化。请重新创建并验证备份。",
                required,
                available,
            )
        if _sha256(credential.backup_path) != credential.backup_sha256:
            return MigrationPreflightResult(
                False,
                "backup_verification_failed",
                "备份完整性验证失败。现有数据库未被修改。",
                required,
                available,
            )
        if available < required:
            return MigrationPreflightResult(
                False,
                "insufficient_space",
                f"迁移至少需要 {required} 字节可用空间。请清理缓存后重试。",
                required,
                available,
                "open_cache_cleanup",
            )
        return MigrationPreflightResult(
            True,
            None,
            "迁移预检通过。",
            required,
            available,
        )


class MigrationExecutor:
    """Upgrade a candidate copy and atomically replace only after complete success."""

    def __init__(
        self,
        config: Config,
        database_path: Path,
        *,
        fault_injector: Callable[[str], None] | None = None,
        available_bytes: Callable[[], int] | None = None,
    ) -> None:
        self._config = config
        self._database_path = database_path.resolve()
        self._fault_injector = fault_injector
        self._preflight = MigrationPreflight(
            self._database_path,
            available_bytes=available_bytes,
        )

    def _candidate_path(self, suffix: str) -> Path:
        return self._database_path.with_name(f".{self._database_path.name}.{suffix}")

    def _inject(self, stage: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage)

    def _copy_database(self, destination: Path) -> None:
        destination.unlink(missing_ok=True)
        with (
            closing(sqlite3.connect(self._database_path)) as source,
            closing(sqlite3.connect(destination)) as target,
        ):
            source.backup(target)

    def _config_for(self, database_path: Path) -> Config:
        config = Config(self._config.config_file_name)
        script_location = self._config.get_main_option("script_location")
        if script_location:
            config.set_main_option("script_location", script_location)
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
        return config

    def _upgrade_candidate(self, candidate: Path) -> str:
        command.upgrade(self._config_for(candidate), "head")
        with closing(sqlite3.connect(candidate)) as connection:
            value = connection.execute("PRAGMA integrity_check").fetchone()
        integrity = str(value[0]) if value is not None else "missing"
        if integrity != "ok":
            raise RuntimeError("candidate database integrity check failed")
        return integrity

    def dry_run(self, credential: BackupVerificationCredential) -> MigrationDryRunResult:
        preflight = self._preflight.evaluate(credential)
        if not preflight.allowed:
            return MigrationDryRunResult(
                False,
                preflight.error_code,
                preflight.user_message,
                None,
                preflight.required_bytes,
                preflight.cleanup_action,
            )
        candidate = self._candidate_path("dry-run")
        try:
            self._copy_database(candidate)
            integrity = self._upgrade_candidate(candidate)
            return MigrationDryRunResult(
                True,
                None,
                "迁移 dry-run 通过。现有数据库未被修改。",
                integrity,
                preflight.required_bytes,
            )
        except BaseException:
            return MigrationDryRunResult(
                False,
                "migration_dry_run_failed",
                "迁移 dry-run 失败。现有数据库未被修改。",
                None,
                preflight.required_bytes,
            )
        finally:
            candidate.unlink(missing_ok=True)

    def execute(self, credential: BackupVerificationCredential) -> MigrationExecutionResult:
        preflight = self._preflight.evaluate(credential)
        if not preflight.allowed:
            return MigrationExecutionResult(
                False,
                preflight.error_code,
                preflight.user_message,
                False,
                preflight.required_bytes,
                preflight.cleanup_action,
            )
        dry_run = self.dry_run(credential)
        if not dry_run.allowed:
            return MigrationExecutionResult(
                False,
                dry_run.error_code,
                dry_run.user_message,
                False,
                dry_run.required_bytes,
                dry_run.cleanup_action,
            )

        candidate = self._candidate_path("migrating")
        try:
            self._inject("before_copy")
            self._copy_database(candidate)
            self._upgrade_candidate(candidate)
            self._inject("before_replace")
            os.replace(candidate, self._database_path)
            return MigrationExecutionResult(
                True,
                None,
                "数据库迁移成功。",
                False,
                preflight.required_bytes,
            )
        except OSError as error:
            if error.errno == errno.ENOSPC or "no space left" in str(error).casefold():
                return MigrationExecutionResult(
                    False,
                    "disk_full",
                    f"迁移至少需要 {preflight.required_bytes} 字节。请清理缓存后重试。",
                    False,
                    preflight.required_bytes,
                    "open_cache_cleanup",
                )
            return MigrationExecutionResult(
                False,
                "migration_failed",
                "迁移失败。现有数据库保持可用。",
                False,
                preflight.required_bytes,
            )
        except BaseException:
            return MigrationExecutionResult(
                False,
                "migration_failed",
                "迁移失败。现有数据库保持可用。",
                False,
                preflight.required_bytes,
            )
        finally:
            candidate.unlink(missing_ok=True)

    def recover_interrupted(self) -> bool:
        """Discard an uncommitted candidate left by a terminated process."""

        candidate = self._candidate_path("migrating")
        if not candidate.exists():
            return False
        candidate.unlink()
        return True
