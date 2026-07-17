"""Async task execution with cancellation and late-result protection."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from .cancellation import CancellationToken
from .models import (
    CancellationCapability,
    ErrorCategory,
    TaskId,
    TaskResult,
    TaskStatus,
    TaskType,
    UserError,
)
from .registry import InvalidTaskTransitionError, TaskRecord, TaskRegistry

T = TypeVar("T")


class TaskExecutionError(RuntimeError):
    """Expected operation failure carrying only a UI-safe error object."""

    def __init__(self, error: UserError) -> None:
        super().__init__(error.code)
        self.error = error


class TaskSubmissionClosedError(RuntimeError):
    """Raised when shutdown has stopped new task submission."""


class TaskExecutor:
    """Run registered async work without allowing cancelled results to commit."""

    def __init__(
        self,
        registry: TaskRegistry,
        *,
        task_id_factory: Callable[[], TaskId] | None = None,
    ) -> None:
        self._registry = registry
        self._task_id_factory = task_id_factory or (lambda: TaskId(str(uuid4())))
        self._tokens: dict[TaskId, CancellationToken] = {}
        self._tasks: dict[TaskId, asyncio.Task[None]] = {}
        self._must_finish_on_shutdown: set[TaskId] = set()
        self._accepting = True

    @property
    def accepting(self) -> bool:
        """Return whether new tasks may be submitted."""

        return self._accepting

    @property
    def registry(self) -> TaskRegistry:
        """Expose the query-only task state source to coordinators."""

        return self._registry

    def submit(
        self,
        task_type: TaskType,
        operation: Callable[[CancellationToken], Awaitable[T]],
        *,
        cancellation: CancellationCapability,
        on_success: Callable[[T], None] | None = None,
        safe_result: object | None = None,
        must_finish_on_shutdown: bool = False,
    ) -> TaskId:
        """Register and schedule work on the current event loop."""

        if not self._accepting:
            raise TaskSubmissionClosedError("background task submission is closed")

        task_id = self._task_id_factory()
        token = CancellationToken()
        self._registry.register(task_id, task_type, cancellation)
        self._tokens[task_id] = token
        if must_finish_on_shutdown:
            self._must_finish_on_shutdown.add(task_id)
        self._tasks[task_id] = asyncio.create_task(
            self._run(task_id, token, operation, on_success, safe_result),
            name=f"background:{task_type.value}:{task_id}",
        )
        return task_id

    async def _run(
        self,
        task_id: TaskId,
        token: CancellationToken,
        operation: Callable[[CancellationToken], Awaitable[T]],
        on_success: Callable[[T], None] | None,
        safe_result: object | None,
    ) -> None:
        current = self._registry.get(task_id)
        if current.status.is_terminal:
            return
        self._registry.transition(task_id, TaskStatus.RUNNING)
        try:
            value = await operation(token)
            token.raise_if_cancelled()
            if on_success is not None:
                on_success(value)
            self._registry.complete(task_id, TaskResult.succeeded(safe_result))
        except asyncio.CancelledError:
            self._finish_cancelled(task_id)
        except TaskExecutionError as exc:
            self._registry.complete(task_id, TaskResult.failed(exc.error))
        except Exception:
            error = UserError(
                category=ErrorCategory.INTERNAL,
                code="task.unexpected_failure",
                what_happened="后台任务未能完成。",
                data_impact="已有数据未受影响。",
                next_action="请重试; 若问题持续, 请生成诊断包。",
                retryable=False,
            )
            self._registry.complete(task_id, TaskResult.failed(error))

    def _finish_cancelled(self, task_id: TaskId) -> None:
        current = self._registry.get(task_id)
        if current.status in {TaskStatus.RUNNING, TaskStatus.CANCELLING}:
            self._registry.transition(task_id, TaskStatus.CANCELLED)

    def cancel(self, task_id: TaskId) -> bool:
        """Request cancellation without force-killing a possibly writing adapter."""

        record = self._registry.get(task_id)
        if (
            record.cancellation is CancellationCapability.NOT_CANCELLABLE
            or record.status.is_terminal
            or record.status is TaskStatus.CANCELLING
        ):
            return False
        self._tokens[task_id].cancel()
        if record.status is TaskStatus.QUEUED:
            self._registry.transition(task_id, TaskStatus.CANCELLED)
        elif record.status is TaskStatus.RUNNING:
            self._registry.transition(task_id, TaskStatus.CANCELLING)
        return True

    async def wait(self, task_id: TaskId) -> TaskRecord:
        """Wait for an operation runner while shielding it from caller cancellation."""

        await asyncio.shield(self._tasks[task_id])
        return self._registry.get(task_id)

    def stop_accepting(self) -> None:
        """Permanently stop new task submission for application shutdown."""

        self._accepting = False

    def active_records(self) -> tuple[TaskRecord, ...]:
        """Return every non-terminal task snapshot."""

        return tuple(
            record for record in self._registry.list_all() if not record.status.is_terminal
        )

    def essential_task_ids(self) -> tuple[TaskId, ...]:
        """Return active task IDs whose writes must be awaited during shutdown."""

        return tuple(
            task_id
            for task_id in self._must_finish_on_shutdown
            if not self._registry.get(task_id).status.is_terminal
        )

    def force_cancel_runner(self, task_id: TaskId) -> None:
        """Cancel an internal runner during teardown after its result is already unusable."""

        task = self._tasks.get(task_id)
        if task is not None and not task.done():
            task.cancel()

    def mark_cancelled_if_possible(self, task_id: TaskId) -> None:
        """Best-effort terminal transition used after forced teardown."""

        try:
            self._finish_cancelled(task_id)
        except InvalidTaskTransitionError:
            return
