"""Task data transfer object tests."""

from __future__ import annotations

import pytest

from english_player.tasks import (
    CancellationCapability,
    ErrorCategory,
    TaskId,
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskType,
    UserError,
)


def test_progress_accepts_a_bounded_fraction() -> None:
    progress = TaskProgress(completed=2, total=4, message="正在验证")

    assert progress.fraction == 0.5


@pytest.mark.parametrize(
    ("completed", "total"),
    [(-1, 1), (2, 1), (0, 0)],
)
def test_progress_rejects_invalid_bounds(completed: int, total: int) -> None:
    with pytest.raises(ValueError):
        TaskProgress(completed=completed, total=total)


def test_task_result_requires_exactly_one_success_payload_shape() -> None:
    error = UserError(
        category=ErrorCategory.NETWORK,
        code="network.unreachable",
        what_happened="网络暂时不可用。",
        data_impact="已有数据未受影响。",
        next_action="请检查网络后重试。",
        retryable=True,
    )

    assert TaskResult.succeeded("ok").value == "ok"
    assert TaskResult.failed(error).error == error
    with pytest.raises(ValueError):
        TaskResult(success=True, value=None, error=error)
    with pytest.raises(ValueError):
        TaskResult(success=False, value=None, error=None)


def test_task_dto_enums_cover_required_contract() -> None:
    assert TaskId("task-1") == "task-1"
    assert TaskType.PLAYLIST_REFRESH.value == "playlist_refresh"
    assert TaskStatus.CANCELLING.value == "cancelling"
    assert CancellationCapability.CANCELLABLE.value == "cancellable"

