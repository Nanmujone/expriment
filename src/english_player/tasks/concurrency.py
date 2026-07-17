"""Resource-specific limits that keep background work from starving playback."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from .models import TaskType

P = ParamSpec("P")
T = TypeVar("T")

_AI_TASK_TYPES = {
    TaskType.AI_ANALYSIS,
    TaskType.AI_QUESTION,
    TaskType.PHRASE_EXPLANATION,
}


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class TaskConcurrencyLimits:
    """Apply independent limits for refresh, per-song AI, and file work."""

    def __init__(self, *, playlist_refreshes: int = 2, file_workers: int = 2) -> None:
        if playlist_refreshes <= 0 or file_workers <= 0:
            raise ValueError("concurrency limits must be positive")
        self._playlist_refreshes = asyncio.Semaphore(playlist_refreshes)
        self._file_workers = asyncio.Semaphore(file_workers)
        self._ai_locks: dict[tuple[str, TaskType], _LockEntry] = {}

    async def run_playlist_refresh(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run a playlist read under the dedicated small-concurrency semaphore."""

        async with self._playlist_refreshes:
            return await operation()

    async def run_ai(
        self,
        song_id: str,
        task_type: TaskType,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Serialize only AI work sharing both a song and operation kind."""

        if task_type not in _AI_TASK_TYPES:
            raise ValueError("run_ai requires an AI task type")
        if not song_id:
            raise ValueError("song_id must be non-empty")

        key = (song_id, task_type)
        entry = self._ai_locks.get(key)
        if entry is None:
            entry = _LockEntry(asyncio.Lock())
            self._ai_locks[key] = entry
        entry.users += 1
        try:
            async with entry.lock:
                return await operation()
        finally:
            entry.users -= 1
            if entry.users == 0 and self._ai_locks.get(key) is entry:
                del self._ai_locks[key]

    async def run_file(self, operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        """Run blocking validation or file work in a bounded worker allocation."""

        async with self._file_workers:
            return await asyncio.to_thread(operation, *args, **kwargs)

