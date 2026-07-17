"""Bounded retry policy for external idempotent reads."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from .models import ErrorCategory


class OperationKind(StrEnum):
    """Whether repeating an operation is safe without user confirmation."""

    IDEMPOTENT_READ = "idempotent_read"
    MUTATING_WRITE = "mutating_write"


@dataclass(frozen=True, slots=True)
class TimeoutSettings:
    """Connection and whole-attempt timeout values passed to adapters."""

    connect_timeout: float
    total_timeout: float


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Finite exponential-backoff settings with bounded symmetric jitter."""

    max_attempts: int = 3
    connect_timeout: float = 5.0
    total_timeout: float = 30.0
    base_delay: float = 0.25
    max_delay: float = 4.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.connect_timeout <= 0 or self.total_timeout <= 0:
            raise ValueError("timeouts must be positive")
        if self.connect_timeout > self.total_timeout:
            raise ValueError("connect timeout cannot exceed total timeout")
        if self.base_delay < 0 or self.max_delay < 0:
            raise ValueError("retry delays cannot be negative")
        if self.base_delay > self.max_delay:
            raise ValueError("base delay cannot exceed maximum delay")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter ratio must be between zero and one")

    @property
    def timeouts(self) -> TimeoutSettings:
        """Return the immutable timeout values an adapter should apply."""

        return TimeoutSettings(self.connect_timeout, self.total_timeout)


class OperationError(RuntimeError):
    """Classified adapter error used solely for retry decisions."""

    def __init__(self, category: ErrorCategory, code: str, *, transient: bool) -> None:
        super().__init__(code)
        self.category = category
        self.code = code
        self.transient = transient


class RetryExhaustedError(RuntimeError):
    """Raised after all permitted attempts fail with a retryable error."""

    def __init__(self, attempts: int, last_error: OperationError) -> None:
        super().__init__(f"retry attempts exhausted: {last_error.code}")
        self.attempts = attempts
        self.last_error = last_error


_TRANSIENT_READ_CATEGORIES = frozenset(
    {
        ErrorCategory.NETWORK,
        ErrorCategory.TIMEOUT,
        ErrorCategory.UNAVAILABLE,
    }
)


def is_retryable(operation_kind: OperationKind, error: OperationError) -> bool:
    """Allow retries only for idempotent reads and transient network conditions."""

    return (
        operation_kind is OperationKind.IDEMPOTENT_READ
        and error.transient
        and error.category in _TRANSIENT_READ_CATEGORIES
    )


def _retry_delay(policy: RetryPolicy, failed_attempt: int, random_value: float) -> float:
    delay = min(policy.max_delay, policy.base_delay * (2.0 ** (failed_attempt - 1)))
    bounded_random = min(1.0, max(0.0, random_value))
    jitter_factor = 1 + ((bounded_random * 2) - 1) * policy.jitter_ratio
    return delay * jitter_factor


async def run_with_retry[T](
    operation: Callable[[TimeoutSettings], Awaitable[T]],
    *,
    operation_kind: OperationKind,
    policy: RetryPolicy,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    """Run an operation with per-attempt total timeout and finite retry delays."""

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await asyncio.wait_for(operation(policy.timeouts), policy.total_timeout)
        except TimeoutError:
            error = OperationError(
                ErrorCategory.TIMEOUT,
                "operation.total_timeout",
                transient=True,
            )
        except OperationError as exc:
            error = exc

        if not is_retryable(operation_kind, error):
            raise error
        if attempt == policy.max_attempts:
            raise RetryExhaustedError(attempt, error)
        await sleep(_retry_delay(policy, attempt, random_value()))

    raise AssertionError("retry loop must return or raise")
