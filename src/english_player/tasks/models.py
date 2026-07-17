"""Stable task and user-error data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

TaskId = NewType("TaskId", str)


class TaskType(StrEnum):
    """Kinds of work coordinated by the background task subsystem."""

    PLAYLIST_REFRESH = "playlist_refresh"
    AI_ANALYSIS = "ai_analysis"
    AI_QUESTION = "ai_question"
    PHRASE_EXPLANATION = "phrase_explanation"
    BACKUP = "backup"
    RESTORE = "restore"
    CLEANUP = "cleanup"
    VALIDATION = "validation"


class TaskStatus(StrEnum):
    """Persistable lifecycle states for a background task."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Return whether no further state transition is legal."""

        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


class CancellationCapability(StrEnum):
    """Whether a task accepts a user or shutdown cancellation request."""

    CANCELLABLE = "cancellable"
    NOT_CANCELLABLE = "not_cancellable"


class ErrorCategory(StrEnum):
    """Stable categories shared by adapters, tasks, and user messages."""

    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    COPYRIGHT = "copyright"
    REGION = "region"
    MEMBERSHIP = "membership"
    AUTHENTICATION = "authentication"
    QUOTA = "quota"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    STORAGE = "storage"
    INCOMPATIBLE = "incompatible"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class TaskProgress:
    """Bounded progress with an optional non-sensitive status summary."""

    completed: int
    total: int
    message: str | None = None

    def __post_init__(self) -> None:
        if self.total <= 0:
            raise ValueError("progress total must be positive")
        if self.completed < 0 or self.completed > self.total:
            raise ValueError("progress completed must be between zero and total")

    @property
    def fraction(self) -> float:
        """Return progress as a value from zero through one."""

        return self.completed / self.total


@dataclass(frozen=True, slots=True)
class UserError:
    """A complete, non-technical error suitable for direct UI display."""

    category: ErrorCategory
    code: str
    what_happened: str
    data_impact: str
    next_action: str
    retryable: bool

    def __post_init__(self) -> None:
        values = (self.code, self.what_happened, self.data_impact, self.next_action)
        if any(not value.strip() for value in values):
            raise ValueError("all user error fields must be non-empty")

    @property
    def user_message(self) -> str:
        """Return the required what/impact/action structure as one message."""

        return " ".join((self.what_happened, self.data_impact, self.next_action))

    @property
    def data_safe(self) -> bool:
        """Return whether the message promises that existing data remains safe."""

        return "未受影响" in self.data_impact or "保持不变" in self.data_impact

    @property
    def suggested_action(self) -> str:
        """Compatibility alias used by the common application error contract."""

        return self.next_action


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Terminal result without an exception or sensitive request payload."""

    success: bool
    value: object | None
    error: UserError | None

    def __post_init__(self) -> None:
        if self.success and self.error is not None:
            raise ValueError("a successful result cannot contain an error")
        if not self.success and (self.error is None or self.value is not None):
            raise ValueError("a failed result requires only an error")

    @classmethod
    def succeeded(cls, value: object | None) -> TaskResult:
        """Construct a successful result."""

        return cls(success=True, value=value, error=None)

    @classmethod
    def failed(cls, error: UserError) -> TaskResult:
        """Construct a failed result."""

        return cls(success=False, value=None, error=error)

