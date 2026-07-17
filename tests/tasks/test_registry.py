"""Task registry lifecycle tests."""

from __future__ import annotations

import pytest

from english_player.tasks import (
    CancellationCapability,
    DuplicateTaskError,
    ErrorCategory,
    InvalidTaskTransitionError,
    TaskId,
    TaskProgress,
    TaskRegistry,
    TaskResult,
    TaskStatus,
    TaskType,
    UnknownTaskError,
    UserError,
)


def test_registry_tracks_successful_task_lifecycle() -> None:
    registry = TaskRegistry()
    task_id = TaskId("refresh-1")

    queued = registry.register(
        task_id,
        TaskType.PLAYLIST_REFRESH,
        CancellationCapability.CANCELLABLE,
    )
    running = registry.transition(task_id, TaskStatus.RUNNING)
    updated = registry.update_progress(task_id, TaskProgress(1, 2, "已获取元数据"))
    completed = registry.complete(task_id, TaskResult.succeeded({"songs": 3}))

    assert queued.status is TaskStatus.QUEUED
    assert running.status is TaskStatus.RUNNING
    assert updated.progress == TaskProgress(1, 2, "已获取元数据")
    assert completed.status is TaskStatus.SUCCEEDED
    assert completed.result == TaskResult.succeeded({"songs": 3})
    assert registry.get(task_id) == completed


def test_registry_tracks_failure_and_cancellation_lifecycles() -> None:
    registry = TaskRegistry()
    failure_id = TaskId("ai-1")
    cancel_id = TaskId("backup-1")
    error = UserError(
        category=ErrorCategory.INVALID_RESPONSE,
        code="ai.invalid_response",
        what_happened="AI 返回格式无效。",
        data_impact="旧解析未被覆盖。",
        next_action="请重新生成。",
        retryable=False,
    )
    registry.register(failure_id, TaskType.AI_ANALYSIS, CancellationCapability.CANCELLABLE)
    registry.register(cancel_id, TaskType.BACKUP, CancellationCapability.CANCELLABLE)

    registry.transition(failure_id, TaskStatus.RUNNING)
    failed = registry.complete(failure_id, TaskResult.failed(error))
    registry.transition(cancel_id, TaskStatus.RUNNING)
    registry.transition(cancel_id, TaskStatus.CANCELLING)
    cancelled = registry.transition(cancel_id, TaskStatus.CANCELLED)

    assert failed.status is TaskStatus.FAILED
    assert failed.error == error
    assert cancelled.status is TaskStatus.CANCELLED


def test_registry_rejects_duplicate_unknown_and_illegal_transitions() -> None:
    registry = TaskRegistry()
    task_id = TaskId("task-1")
    registry.register(task_id, TaskType.VALIDATION, CancellationCapability.NOT_CANCELLABLE)

    with pytest.raises(DuplicateTaskError):
        registry.register(task_id, TaskType.VALIDATION, CancellationCapability.NOT_CANCELLABLE)
    with pytest.raises(UnknownTaskError):
        registry.get(TaskId("missing"))
    with pytest.raises(InvalidTaskTransitionError):
        registry.transition(task_id, TaskStatus.SUCCEEDED)


def test_registry_rejects_progress_regression_or_terminal_updates() -> None:
    registry = TaskRegistry()
    task_id = TaskId("task-1")
    registry.register(task_id, TaskType.VALIDATION, CancellationCapability.CANCELLABLE)
    registry.transition(task_id, TaskStatus.RUNNING)
    registry.update_progress(task_id, TaskProgress(2, 3))

    with pytest.raises(ValueError):
        registry.update_progress(task_id, TaskProgress(1, 3))

    registry.complete(task_id, TaskResult.succeeded(None))
    with pytest.raises(InvalidTaskTransitionError):
        registry.update_progress(task_id, TaskProgress(3, 3))


def test_registry_returns_an_immutable_snapshot_of_all_tasks() -> None:
    registry = TaskRegistry()
    first = TaskId("task-1")
    second = TaskId("task-2")
    registry.register(first, TaskType.BACKUP, CancellationCapability.CANCELLABLE)
    registry.register(second, TaskType.RESTORE, CancellationCapability.NOT_CANCELLABLE)

    snapshot = registry.list_all()

    assert tuple(item.task_id for item in snapshot) == (first, second)
    assert isinstance(snapshot, tuple)
