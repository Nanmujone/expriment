"""Alembic schema and guarded migration tests."""

from __future__ import annotations

import errno
import hashlib
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from english_player.infrastructure.persistence.migrations import (
    BackupVerificationCredential,
    MigrationExecutor,
    MigrationPreflight,
)


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _credential(database_path: Path, backup_path: Path) -> BackupVerificationCredential:
    return BackupVerificationCredential(
        source_database=database_path.resolve(),
        source_sha256=_sha256(database_path),
        backup_path=backup_path.resolve(),
        backup_sha256=_sha256(backup_path),
        schema_version="base",
    )


def test_upgrade_empty_database_creates_all_tables_constraints_and_indexes(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.sqlite3"
    command.upgrade(_config(database_path), "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    expected_tables = {
        "playlist",
        "song",
        "playlist_song",
        "audio_source",
        "lyrics_document",
        "lyrics_line",
        "word_timing",
        "analysis_version",
        "line_analysis",
        "qa_message",
        "favorite",
        "playback_preference",
        "setting_reference",
        "background_task",
        "pending_cleanup",
        "alembic_version",
    }
    assert expected_tables == set(inspector.get_table_names())
    assert "uq_playlist_provider_remote_id" in {
        item["name"] for item in inspector.get_unique_constraints("playlist")
    }
    assert "ix_pending_cleanup_status_purge_after" in {
        item["name"] for item in inspector.get_indexes("pending_cleanup")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    engine.dispose()


def test_preflight_blocks_missing_invalid_backup_and_insufficient_space(tmp_path: Path) -> None:
    database_path = tmp_path / "current.sqlite3"
    database_path.write_bytes(b"database")
    backup_path = tmp_path / "backup.sqlite3"
    backup_path.write_bytes(b"backup")
    preflight = MigrationPreflight(database_path, available_bytes=lambda: 10**9)

    assert preflight.evaluate(None).allowed is False
    invalid = _credential(database_path, backup_path)
    database_path.write_bytes(b"changed")
    assert preflight.evaluate(invalid).error_code == "backup_source_mismatch"

    current = _credential(database_path, backup_path)
    result = MigrationPreflight(database_path, available_bytes=lambda: 0).evaluate(current)
    assert result.allowed is False
    assert result.error_code == "insufficient_space"
    assert result.required_bytes > 0
    assert result.cleanup_action == "open_cache_cleanup"


def test_migration_dry_run_and_failure_leave_original_database_readable(tmp_path: Path) -> None:
    database_path = tmp_path / "current.sqlite3"
    command.upgrade(_config(database_path), "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO song (provider, provider_song_id, title) VALUES ('local', '1', 'Old')")
        )
    engine.dispose()
    backup_path = tmp_path / "before.sqlite3"
    shutil.copy2(database_path, backup_path)
    credential = _credential(database_path, backup_path)

    executor = MigrationExecutor(_config(database_path), database_path)
    dry_run = executor.dry_run(credential)
    assert dry_run.allowed is True
    assert dry_run.integrity_check == "ok"

    def fail_before_replace(stage: str) -> None:
        if stage == "before_replace":
            raise RuntimeError("injected migration failure")

    failed = MigrationExecutor(
        _config(database_path), database_path, fault_injector=fail_before_replace
    ).execute(credential)
    assert failed.succeeded is False
    assert failed.error_code == "migration_failed"

    readable = create_engine(f"sqlite:///{database_path.as_posix()}")
    with readable.connect() as connection:
        assert connection.scalar(text("SELECT title FROM song WHERE provider_song_id = '1'")) == "Old"
    readable.dispose()


def test_restart_recovery_discards_incomplete_candidate(tmp_path: Path) -> None:
    database_path = tmp_path / "current.sqlite3"
    database_path.write_bytes(b"original")
    candidate = database_path.with_name(f".{database_path.name}.migrating")
    candidate.write_bytes(b"incomplete")

    recovered = MigrationExecutor(_config(database_path), database_path).recover_interrupted()
    assert recovered is True
    assert not candidate.exists()
    assert database_path.read_bytes() == b"original"


def test_migration_disk_full_is_not_retried_and_preserves_database(tmp_path: Path) -> None:
    database_path = tmp_path / "current.sqlite3"
    command.upgrade(_config(database_path), "head")
    backup_path = tmp_path / "before.sqlite3"
    shutil.copy2(database_path, backup_path)
    credential = _credential(database_path, backup_path)
    original = database_path.read_bytes()
    attempts = 0

    def disk_full(stage: str) -> None:
        nonlocal attempts
        if stage == "before_copy":
            attempts += 1
            raise OSError(errno.ENOSPC, "No space left on device")

    result = MigrationExecutor(
        _config(database_path), database_path, fault_injector=disk_full
    ).execute(credential)
    assert result.succeeded is False
    assert result.error_code == "disk_full"
    assert result.retryable is False
    assert result.cleanup_action == "open_cache_cleanup"
    assert result.required_bytes > 0
    assert attempts == 1
    assert database_path.read_bytes() == original
