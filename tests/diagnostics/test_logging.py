"""Rotating and pre-write-redacted logging tests."""

from __future__ import annotations

from pathlib import Path

from english_player.diagnostics import (
    SensitiveDataScanner,
    SensitiveKind,
    SensitiveValue,
    close_diagnostic_logger,
    configure_diagnostic_logger,
)


def _secret_values() -> dict[SensitiveKind, str]:
    return {
        SensitiveKind.API_KEY: "sk-" + ("K" * 24),
        SensitiveKind.COOKIE: "Cookie" + ": session=" + ("z" * 24),
        SensitiveKind.LYRICS: "An entire " + "lyric line that must stay private",
        SensitiveKind.QA: "A private " + "question answer transcript",
        SensitiveKind.TEMP_AUDIO_URL: "https://audio.invalid/a?" + "sign=" + ("q" * 24),
        SensitiveKind.MEDIA_PATH: "D:" + "\\Private\\recording.lrc",
    }


def _scanner() -> SensitiveDataScanner:
    return SensitiveDataScanner(
        SensitiveValue(value, kind) for kind, value in _secret_values().items()
    )


def _read_logs(log_path: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in log_path.parent.glob("app.log*"))


def test_logger_redacts_arguments_and_exception_details_before_disk_write(tmp_path: Path) -> None:
    values = _secret_values()
    scanner = _scanner()
    log_path = tmp_path / "app.log"
    logger = configure_diagnostic_logger(log_path, scanner, max_bytes=4096, backup_count=2)

    for kind, value in values.items():
        logger.warning("unsafe %s payload=%s", kind.value, value)
    try:
        raise RuntimeError(values[SensitiveKind.MEDIA_PATH])
    except RuntimeError:
        logger.exception("file validation failed")
    close_diagnostic_logger(logger)

    output = _read_logs(log_path)
    scanner.assert_clean(output, source="rotating logs")
    assert all(value not in output for value in values.values())
    assert "file validation failed" in output
    assert "exception details omitted" in output


def test_logger_rotates_and_keeps_only_the_configured_backups(tmp_path: Path) -> None:
    scanner = _scanner()
    log_path = tmp_path / "app.log"
    logger = configure_diagnostic_logger(log_path, scanner, max_bytes=180, backup_count=2)

    for sequence in range(40):
        logger.info("safe diagnostic event sequence=%s trace=%s", sequence, "x" * 24)
    close_diagnostic_logger(logger)

    log_files = sorted(log_path.parent.glob("app.log*"))
    assert log_path in log_files
    assert len(log_files) == 3
    scanner.assert_clean(_read_logs(log_path), source="rotated logs")
