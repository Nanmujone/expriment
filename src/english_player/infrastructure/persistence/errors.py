"""Stable persistence error classification for application-layer handling."""

from __future__ import annotations

import errno
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError

DEFAULT_REQUIRED_FREE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PersistenceError(RuntimeError):
    """A safe, typed storage failure that contains no database content."""

    code: str
    user_message: str
    retryable: bool
    suggested_action: str
    required_bytes: int | None = None
    cleanup_action: str | None = None

    def __str__(self) -> str:
        return self.user_message


def classify_persistence_error(error: BaseException) -> PersistenceError | None:
    """Map SQLite/OS failures while leaving unrelated programming errors untouched."""

    original: BaseException = error
    if isinstance(error, DBAPIError) and isinstance(error.orig, BaseException):
        original = error.orig
    message = str(original).casefold()
    error_number = getattr(original, "errno", None)

    if "database is locked" in message or "database table is locked" in message:
        return PersistenceError(
            code="database_locked",
            user_message="数据库正被占用。已有数据未受影响。请稍后重试。",
            retryable=True,
            suggested_action="retry_later",
        )
    if error_number == errno.ENOSPC or "disk is full" in message or "no space left" in message:
        return PersistenceError(
            code="disk_full",
            user_message="磁盘空间不足。当前写入已停止并回滚。请清理缓存后重试。",
            retryable=False,
            suggested_action="free_space",
            required_bytes=DEFAULT_REQUIRED_FREE_BYTES,
            cleanup_action="open_cache_cleanup",
        )
    return None
