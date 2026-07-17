"""Cancellation propagation and late-result protection tests."""

from __future__ import annotations

import asyncio

import pytest

from english_player.tasks import (
    CancellationCapability,
    CancellationToken,
    ErrorCategory,
    TaskExecutionError,
    TaskExecutor,
    TaskRegistry,
    TaskStatus,
    TaskType,
    UserError,
)


@pytest.mark.asyncio
async def test_executor_passes_token_and_commits_a_successful_result() -> None:
    registry = TaskRegistry()
    executor = TaskExecutor(registry)
    seen: list[CancellationToken] = []
    committed: list[object] = []

    async def operation(token: CancellationToken) -> object:
        seen.append(token)
        return {"playlist": "cached"}

    task_id = executor.submit(
        TaskType.PLAYLIST_REFRESH,
        operation,
        cancellation=CancellationCapability.CANCELLABLE,
        on_success=committed.append,
    )

    record = await executor.wait(task_id)

    assert len(seen) == 1
    assert not seen[0].is_cancelled
    assert committed == [{"playlist": "cached"}]
    assert record.status is TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_cancelled_late_result_is_discarded_before_commit() -> None:
    registry = TaskRegistry()
    executor = TaskExecutor(registry)
    started = asyncio.Event()
    release_late_result = asyncio.Event()
    seen: list[CancellationToken] = []
    committed: list[object] = []

    async def cancellation_ignoring_adapter(token: CancellationToken) -> object:
        seen.append(token)
        started.set()
        await release_late_result.wait()
        return "late sensitive response"

    task_id = executor.submit(
        TaskType.AI_ANALYSIS,
        cancellation_ignoring_adapter,
        cancellation=CancellationCapability.CANCELLABLE,
        on_success=committed.append,
    )
    await started.wait()

    assert executor.cancel(task_id)
    assert seen[0].is_cancelled
    assert registry.get(task_id).status is TaskStatus.CANCELLING
    release_late_result.set()
    record = await executor.wait(task_id)

    assert record.status is TaskStatus.CANCELLED
    assert committed == []
    assert record.result is None


@pytest.mark.asyncio
async def test_adapter_can_cooperatively_wait_for_cancellation() -> None:
    registry = TaskRegistry()
    executor = TaskExecutor(registry)
    started = asyncio.Event()

    async def operation(token: CancellationToken) -> object:
        started.set()
        await token.wait()
        token.raise_if_cancelled()
        return "unreachable"

    task_id = executor.submit(
        TaskType.BACKUP,
        operation,
        cancellation=CancellationCapability.CANCELLABLE,
    )
    await started.wait()
    executor.cancel(task_id)

    record = await executor.wait(task_id)

    assert record.status is TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_non_cancellable_task_rejects_cancel_request() -> None:
    registry = TaskRegistry()
    executor = TaskExecutor(registry)
    release = asyncio.Event()

    async def operation(token: CancellationToken) -> object:
        del token
        await release.wait()
        return None

    task_id = executor.submit(
        TaskType.RESTORE,
        operation,
        cancellation=CancellationCapability.NOT_CANCELLABLE,
    )
    await asyncio.sleep(0)

    assert not executor.cancel(task_id)
    assert registry.get(task_id).status is TaskStatus.RUNNING
    release.set()
    assert (await executor.wait(task_id)).status is TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_expected_failure_records_only_the_safe_user_error() -> None:
    registry = TaskRegistry()
    executor = TaskExecutor(registry)
    error = UserError(
        category=ErrorCategory.STORAGE,
        code="storage.disk_full",
        what_happened="保存失败, 磁盘空间不足。",
        data_impact="已有数据未受影响。",
        next_action="请清理缓存后重试。",
        retryable=False,
    )

    async def operation(token: CancellationToken) -> object:
        del token
        raise TaskExecutionError(error)

    task_id = executor.submit(
        TaskType.BACKUP,
        operation,
        cancellation=CancellationCapability.CANCELLABLE,
    )

    record = await executor.wait(task_id)

    assert record.status is TaskStatus.FAILED
    assert record.error == error
