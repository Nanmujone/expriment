"""Public background-task contracts."""

from .cancellation import CancellationToken
from .concurrency import TaskConcurrencyLimits
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
from .retry import (
    OperationError,
    OperationKind,
    RetryExhaustedError,
    RetryPolicy,
    TimeoutSettings,
    is_retryable,
    run_with_retry,
)

__all__ = [
    "CancellationCapability",
    "CancellationToken",
    "DuplicateTaskError",
    "ErrorCategory",
    "InvalidTaskTransitionError",
    "OperationError",
    "OperationKind",
    "RetryExhaustedError",
    "RetryPolicy",
    "TaskConcurrencyLimits",
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
    "TimeoutSettings",
    "UnknownTaskError",
    "UserError",
    "is_retryable",
    "run_with_retry",
]
