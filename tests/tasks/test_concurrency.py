"""Resource-specific concurrency limit tests."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from english_player.tasks import TaskConcurrencyLimits, TaskType


@pytest.mark.asyncio
async def test_playlist_refresh_uses_a_small_concurrency_limit() -> None:
    limits = TaskConcurrencyLimits(playlist_refreshes=2, file_workers=1)
    active = 0
    peak = 0
    two_started = asyncio.Event()
    release = asyncio.Event()

    async def refresh() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            two_started.set()
        await release.wait()
        active -= 1

    running = [asyncio.create_task(limits.run_playlist_refresh(refresh)) for _ in range(5)]
    await asyncio.wait_for(two_started.wait(), timeout=1)

    assert peak == 2
    release.set()
    await asyncio.gather(*running)
    assert peak == 2


@pytest.mark.asyncio
async def test_same_song_and_ai_task_type_are_mutually_exclusive() -> None:
    limits = TaskConcurrencyLimits(playlist_refreshes=1, file_workers=1)
    entered: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> None:
        entered.append("first")
        first_started.set()
        await release_first.wait()

    async def second() -> None:
        entered.append("second")

    first_task = asyncio.create_task(limits.run_ai("song-1", TaskType.AI_ANALYSIS, first))
    await first_started.wait()
    second_task = asyncio.create_task(limits.run_ai("song-1", TaskType.AI_ANALYSIS, second))
    await asyncio.sleep(0)

    assert entered == ["first"]
    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert entered == ["first", "second"]


@pytest.mark.asyncio
async def test_ai_tasks_for_different_songs_can_run_together() -> None:
    limits = TaskConcurrencyLimits(playlist_refreshes=1, file_workers=1)
    active = 0
    peak = 0
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def work() -> None:
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        if active == 2:
            both_started.set()
        await release.wait()
        active -= 1

    first = asyncio.create_task(limits.run_ai("song-1", TaskType.AI_ANALYSIS, work))
    second = asyncio.create_task(limits.run_ai("song-2", TaskType.AI_ANALYSIS, work))
    await asyncio.wait_for(both_started.wait(), timeout=1)

    assert peak == 2
    release.set()
    await asyncio.gather(first, second)


@pytest.mark.asyncio
async def test_file_work_runs_off_event_loop_with_a_worker_limit() -> None:
    limits = TaskConcurrencyLimits(playlist_refreshes=1, file_workers=2)
    event_loop_thread = threading.get_ident()
    counter_lock = threading.Lock()
    active = 0
    peak = 0
    worker_threads: set[int] = set()

    def file_work() -> int:
        nonlocal active, peak
        with counter_lock:
            active += 1
            peak = max(active, peak)
            worker_threads.add(threading.get_ident())
        time.sleep(0.04)
        with counter_lock:
            active -= 1
        return 7

    results = await asyncio.gather(*(limits.run_file(file_work) for _ in range(6)))

    assert results == [7] * 6
    assert peak == 2
    assert event_loop_thread not in worker_threads


@pytest.mark.asyncio
async def test_failed_operation_releases_its_concurrency_permit() -> None:
    limits = TaskConcurrencyLimits(playlist_refreshes=1, file_workers=1)

    async def fail() -> None:
        raise RuntimeError("transient failure")

    with pytest.raises(RuntimeError, match="transient failure"):
        await limits.run_playlist_refresh(fail)

    async def succeed() -> str:
        return "ok"

    assert await limits.run_playlist_refresh(succeed) == "ok"


@pytest.mark.asyncio
async def test_ai_lock_rejects_a_non_ai_task_type() -> None:
    limits = TaskConcurrencyLimits(playlist_refreshes=1, file_workers=1)

    async def work() -> None:
        return None

    with pytest.raises(ValueError, match="AI task type"):
        await limits.run_ai("song-1", TaskType.BACKUP, work)


@pytest.mark.parametrize(
    ("playlist_refreshes", "file_workers"),
    [(0, 1), (1, 0), (-1, 1)],
)
def test_concurrency_limits_must_be_positive(
    playlist_refreshes: int,
    file_workers: int,
) -> None:
    with pytest.raises(ValueError):
        TaskConcurrencyLimits(
            playlist_refreshes=playlist_refreshes,
            file_workers=file_workers,
        )
