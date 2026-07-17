"""Sensitive-data redaction and fixed-scan tests."""

from __future__ import annotations

from english_player.diagnostics import (
    SensitiveDataFoundError,
    SensitiveDataScanner,
    SensitiveKind,
    SensitiveValue,
    serialize_task_records,
)
from english_player.tasks import (
    CancellationCapability,
    TaskId,
    TaskProgress,
    TaskRegistry,
    TaskStatus,
    TaskType,
)


def _sensitive_fixture() -> dict[SensitiveKind, str]:
    return {
        SensitiveKind.API_KEY: "sk-" + ("A" * 24),
        SensitiveKind.COOKIE: "MUSIC" + "_U=" + ("c" * 24),
        SensitiveKind.LYRICS: "Complete " + "lyrics body only for runtime scan",
        SensitiveKind.QA: "Complete " + "question and answer body for runtime scan",
        SensitiveKind.TEMP_AUDIO_URL: ("https://audio.invalid/song.mp3?" + "token=" + ("t" * 24)),
        SensitiveKind.MEDIA_PATH: "C:" + "\\Users\\listener\\Music\\private-song.mp3",
    }


def _scanner() -> SensitiveDataScanner:
    return SensitiveDataScanner(
        SensitiveValue(value, kind) for kind, value in _sensitive_fixture().items()
    )


def test_scanner_finds_every_required_sensitive_category_without_echoing_values() -> None:
    values = _sensitive_fixture()
    scanner = _scanner()
    unsafe = "\n".join(values.values())

    findings = scanner.findings(unsafe)

    assert {finding.kind for finding in findings} == set(SensitiveKind)
    try:
        scanner.assert_clean(unsafe, source="diagnostic output")
    except SensitiveDataFoundError as exc:
        error_text = str(exc)
    else:
        raise AssertionError("fixed scanner should reject sensitive output")
    assert "diagnostic output" in error_text
    assert all(value not in error_text for value in values.values())


def test_redactor_removes_known_values_and_pattern_detected_secrets() -> None:
    values = _sensitive_fixture()
    scanner = _scanner()
    unsafe = "\n".join(
        [
            *values.values(),
            "Authorization" + ": Bearer " + ("B" * 24),
            "Cookie" + ": sessionid=" + ("s" * 24),
        ]
    )

    redacted = scanner.redact(unsafe)

    scanner.assert_clean(redacted, source="redacted text")
    assert all(value not in redacted for value in values.values())
    assert "[REDACTED_API_KEY]" in redacted
    assert "[REDACTED_MEDIA_PATH]" in redacted
    assert "[REDACTED_LYRICS]" in redacted


def test_scanner_preserves_safe_identifiers_and_non_sensitive_urls() -> None:
    scanner = _scanner()
    safe = "task_id=refresh-123 trace_id=trace-456 endpoint=https://example.invalid/v1/health"

    assert scanner.redact(safe) == safe
    scanner.assert_clean(safe)


def test_task_status_serialization_redacts_progress_and_omits_result_payload() -> None:
    values = _sensitive_fixture()
    scanner = _scanner()
    registry = TaskRegistry()
    task_id = TaskId("task-safe-id")
    registry.register(task_id, TaskType.AI_QUESTION, CancellationCapability.CANCELLABLE)
    registry.transition(task_id, TaskStatus.RUNNING)
    registry.update_progress(task_id, TaskProgress(1, 2, values[SensitiveKind.LYRICS]))

    serialized = serialize_task_records(registry.list_all(), scanner)

    scanner.assert_clean(serialized, source="task status")
    assert values[SensitiveKind.LYRICS] not in serialized
    assert "task-safe-id" in serialized
