"""User-facing error catalog tests."""

from __future__ import annotations

import pytest

from english_player.tasks import ErrorCategory, user_error_for


@pytest.mark.parametrize("category", list(ErrorCategory))
def test_every_error_category_has_a_complete_user_message(category: ErrorCategory) -> None:
    error = user_error_for(category, f"task.{category.value}")

    assert error.category is category
    assert error.what_happened.strip()
    assert error.data_impact.strip()
    assert error.next_action.strip()
    assert error.what_happened in error.user_message
    assert error.data_impact in error.user_message
    assert error.next_action in error.user_message


def test_high_risk_failures_explain_safe_data_and_specific_next_action() -> None:
    storage = user_error_for(ErrorCategory.STORAGE, "storage.disk_full")
    incompatible = user_error_for(ErrorCategory.INCOMPATIBLE, "backup.incompatible")
    authentication = user_error_for(ErrorCategory.AUTHENTICATION, "ai.authentication")
    copyright_error = user_error_for(ErrorCategory.COPYRIGHT, "audio.copyright")

    assert "已有数据未受影响" in storage.data_impact
    assert "缓存" in storage.next_action
    assert "现有数据保持不变" in incompatible.data_impact
    assert "兼容" in incompatible.next_action
    assert "API" in authentication.next_action
    assert "本地" in copyright_error.next_action
    assert not storage.retryable
    assert not incompatible.retryable
    assert not authentication.retryable
    assert not copyright_error.retryable


def test_transient_network_error_offers_a_manual_retry() -> None:
    error = user_error_for(ErrorCategory.NETWORK, "network.unreachable")

    assert error.retryable
    assert "重试" in error.next_action


@pytest.mark.parametrize(
    "unsafe_code",
    ["", "contains spaces", "raw: upstream failure", "../path", "x" * 101],
)
def test_error_code_rejects_raw_or_unbounded_technical_text(unsafe_code: str) -> None:
    with pytest.raises(ValueError, match="stable machine identifier"):
        user_error_for(ErrorCategory.INTERNAL, unsafe_code)
