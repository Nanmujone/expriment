"""Public background-task contracts."""

from .cancellation import CancellationToken
from .executor import TaskExecutionError, TaskExecutor, TaskSubmissionClosedError
from .models import (
    CancellationCapability,
    ErrorCategory,
    TaskId,
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskType,
    UserError,
)
from .registry import (
    DuplicateTaskError,
    InvalidTaskTransitionError,
    TaskRecord,
    TaskRegistry,
    TaskRegistryError,
    UnknownTaskError,
)

__all__ = [
    "CancellationCapability",
    "CancellationToken",
    "DuplicateTaskError",
    "ErrorCategory",
    "InvalidTaskTransitionError",
    "TaskExecutionError",
    "TaskExecutor",
    "TaskId",
    "TaskProgress",
    "TaskRecord",
    "TaskRegistry",
    "TaskRegistryError",
    "TaskResult",
    "TaskStatus",
    "TaskSubmissionClosedError",
    "TaskType",
    "UnknownTaskError",
    "UserError",
]
