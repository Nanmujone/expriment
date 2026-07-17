"""Timeout, retry, backoff, and retry-classification tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from english_player.tasks import (
    ErrorCategory,
    OperationError,
    OperationKind,
    RetryExhaustedError,
    RetryPolicy,
    TimeoutSettings,
    is_retryable,
    run_with_retry,
)


@pytest.mark.asyncio
async def test_transient_idempotent_read_retries_with_exponential_backoff() -> None:
    attempts = 0
    observed_timeouts: list[TimeoutSettings] = []
    delays: list[float] = []
    policy = RetryPolicy(
        max_attempts=3,
        connect_timeout=0.2,
        total_timeout=1,
        base_delay=0.1,
        max_delay=1,
        jitter_ratio=0.2,
    )

    async def operation(timeouts: TimeoutSettings) -> str:
        nonlocal attempts
        attempts += 1
        observed_timeouts.append(timeouts)
        if attempts < 3:
            raise OperationError(
                ErrorCategory.NETWORK,
                "network.connection_reset",
                transient=True,
            )
        return "ok"

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    result = await run_with_retry(
        operation,
        operation_kind=OperationKind.IDEMPOTENT_READ,
        policy=policy,
        sleep=record_sleep,
        random_value=lambda: 0.5,
    )

    assert result == "ok"
    assert attempts == 3
    assert observed_timeouts == [TimeoutSettings(0.2, 1)] * 3
    assert delays == pytest.approx([0.1, 0.2])


@pytest.mark.asyncio
async def test_retry_count_is_bounded_and_reports_last_error() -> None:
    attempts = 0
    policy = RetryPolicy(max_attempts=2, base_delay=0, max_delay=0)

    async def operation(timeouts: TimeoutSettings) -> None:
        nonlocal attempts
        del timeouts
        attempts += 1
        raise OperationError(ErrorCategory.UNAVAILABLE, "upstream.busy", transient=True)

    with pytest.raises(RetryExhaustedError) as caught:
        await run_with_retry(
            operation,
            operation_kind=OperationKind.IDEMPOTENT_READ,
            policy=policy,
        )

    assert attempts == 2
    assert caught.value.attempts == 2
    assert caught.value.last_error.code == "upstream.busy"


@pytest.mark.asyncio
async def test_total_timeout_is_enforced_for_each_attempt() -> None:
    policy = RetryPolicy(
        max_attempts=1,
        connect_timeout=0.005,
        total_timeout=0.01,
        base_delay=0,
        max_delay=0,
    )

    async def operation(timeouts: TimeoutSettings) -> None:
        assert timeouts.connect_timeout == 0.005
        await asyncio.sleep(1)

    with pytest.raises(RetryExhaustedError) as caught:
        await run_with_retry(
            operation,
            operation_kind=OperationKind.IDEMPOTENT_READ,
            policy=policy,
        )

    assert caught.value.last_error.category is ErrorCategory.TIMEOUT


@pytest.mark.asyncio
async def test_mutating_operation_does_not_retry_transient_network_failure() -> None:
    attempts = 0

    async def operation(timeouts: TimeoutSettings) -> None:
        nonlocal attempts
        del timeouts
        attempts += 1
        raise OperationError(ErrorCategory.NETWORK, "network.reset", transient=True)

    with pytest.raises(OperationError, match=r"network\.reset"):
        await run_with_retry(
            operation,
            operation_kind=OperationKind.MUTATING_WRITE,
            policy=RetryPolicy(max_attempts=3, base_delay=0, max_delay=0),
        )

    assert attempts == 1


@pytest.mark.parametrize(
    "category",
    [
        ErrorCategory.AUTHENTICATION,
        ErrorCategory.PERMISSION,
        ErrorCategory.COPYRIGHT,
        ErrorCategory.REGION,
        ErrorCategory.MEMBERSHIP,
        ErrorCategory.QUOTA,
        ErrorCategory.INVALID_RESPONSE,
        ErrorCategory.STORAGE,
        ErrorCategory.INCOMPATIBLE,
        ErrorCategory.VALIDATION,
    ],
)
def test_permanent_categories_never_auto_retry(category: ErrorCategory) -> None:
    incorrectly_marked_transient = OperationError(category, "permanent.error", transient=True)

    assert not is_retryable(OperationKind.IDEMPOTENT_READ, incorrectly_marked_transient)


def test_only_transient_network_categories_are_retryable() -> None:
    for category in (ErrorCategory.NETWORK, ErrorCategory.TIMEOUT, ErrorCategory.UNAVAILABLE):
        assert is_retryable(
            OperationKind.IDEMPOTENT_READ,
            OperationError(category, "temporary.error", transient=True),
        )
        assert not is_retryable(
            OperationKind.IDEMPOTENT_READ,
            OperationError(category, "not.transient", transient=False),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RetryPolicy(max_attempts=0),
        lambda: RetryPolicy(connect_timeout=0),
        lambda: RetryPolicy(connect_timeout=2, total_timeout=1),
        lambda: RetryPolicy(base_delay=-1),
        lambda: RetryPolicy(base_delay=2, max_delay=1),
        lambda: RetryPolicy(jitter_ratio=1.1),
    ],
)
def test_invalid_retry_policy_is_rejected(factory: Callable[[], RetryPolicy]) -> None:
    with pytest.raises(ValueError):
        factory()


@pytest.mark.asyncio
async def test_cancellation_propagates_without_retry() -> None:
    attempts = 0

    async def operation(timeouts: TimeoutSettings) -> None:
        nonlocal attempts
        del timeouts
        attempts += 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_with_retry(
            operation,
            operation_kind=OperationKind.IDEMPOTENT_READ,
            policy=RetryPolicy(max_attempts=3, base_delay=0, max_delay=0),
        )

    assert attempts == 1
