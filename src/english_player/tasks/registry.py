"""In-memory task registry with explicit lifecycle rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock

from .models import (
    CancellationCapability,
    TaskId,
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskType,
    UserError,
)


class TaskRegistryError(RuntimeError):
    """Base class for task registry failures."""


class DuplicateTaskError(TaskRegistryError):
    """Raised when a task ID has already been registered."""


class UnknownTaskError(TaskRegistryError):
    """Raised when a task ID is not registered."""


class InvalidTaskTransitionError(TaskRegistryError):
    """Raised when a requested lifecycle transition is not legal."""


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Immutable, query-safe task state snapshot."""

    task_id: TaskId
    task_type: TaskType
    status: TaskStatus
    cancellation: CancellationCapability
    progress: TaskProgress | None
    result: TaskResult | None
    created_at: datetime
    updated_at: datetime

    @property
    def error(self) -> UserError | None:
        """Expose the terminal error without duplicating stored state."""

        return None if self.result is None else self.result.error


_LEGAL_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.CANCELLING: frozenset({TaskStatus.CANCELLED}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class TaskRegistry:
    """Register tasks and expose immutable state snapshots to other modules."""

    def __init__(self) -> None:
        self._records: dict[TaskId, TaskRecord] = {}
        self._lock = RLock()

    def register(
        self,
        task_id: TaskId,
        task_type: TaskType,
        cancellation: CancellationCapability,
    ) -> TaskRecord:
        """Add a new queued task, rejecting ID reuse."""

        now = datetime.now(UTC)
        record = TaskRecord(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.QUEUED,
            cancellation=cancellation,
            progress=None,
            result=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            if task_id in self._records:
                raise DuplicateTaskError(f"task is already registered: {task_id}")
            self._records[task_id] = record
        return record

    def get(self, task_id: TaskId) -> TaskRecord:
        """Return the latest immutable record for a task."""

        with self._lock:
            try:
                return self._records[task_id]
            except KeyError as exc:
                raise UnknownTaskError(f"unknown task: {task_id}") from exc

    def list_all(self) -> tuple[TaskRecord, ...]:
        """Return an immutable insertion-ordered snapshot."""

        with self._lock:
            return tuple(self._records.values())

    def transition(self, task_id: TaskId, status: TaskStatus) -> TaskRecord:
        """Move a task through the explicit lifecycle state machine."""

        with self._lock:
            current = self.get(task_id)
            if status not in _LEGAL_TRANSITIONS[current.status]:
                raise InvalidTaskTransitionError(
                    f"illegal task transition: {current.status.value} -> {status.value}"
                )
            updated = replace(current, status=status, updated_at=datetime.now(UTC))
            self._records[task_id] = updated
            return updated

    def update_progress(self, task_id: TaskId, progress: TaskProgress) -> TaskRecord:
        """Update monotonic progress for a queued or running task."""

        with self._lock:
            current = self.get(task_id)
            if current.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                raise InvalidTaskTransitionError(
                    f"cannot update progress for {current.status.value} task"
                )
            if current.progress is not None and progress.fraction < current.progress.fraction:
                raise ValueError("task progress cannot move backwards")
            updated = replace(current, progress=progress, updated_at=datetime.now(UTC))
            self._records[task_id] = updated
            return updated

    def complete(self, task_id: TaskId, result: TaskResult) -> TaskRecord:
        """Store a validated result and enter the matching terminal state."""

        terminal = TaskStatus.SUCCEEDED if result.success else TaskStatus.FAILED
        with self._lock:
            transitioned = self.transition(task_id, terminal)
            completed = replace(transitioned, result=result, updated_at=datetime.now(UTC))
            self._records[task_id] = completed
            return completed
