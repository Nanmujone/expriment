"""Public background-task contracts."""

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
    "DuplicateTaskError",
    "ErrorCategory",
    "InvalidTaskTransitionError",
    "TaskId",
    "TaskProgress",
    "TaskRecord",
    "TaskRegistry",
    "TaskRegistryError",
    "TaskResult",
    "TaskStatus",
    "TaskType",
    "UnknownTaskError",
    "UserError",
]
