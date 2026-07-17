"""Central redaction and fixed sensitive-data scan primitives."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from english_player.tasks import TaskRecord


class SensitiveKind(StrEnum):
    """Sensitive categories forbidden from status, logs, and diagnostic bundles."""

    API_KEY = "api_key"
    COOKIE = "cookie"
    LYRICS = "lyrics"
    QA = "qa"
    TEMP_AUDIO_URL = "temp_audio_url"
    MEDIA_PATH = "media_path"


@dataclass(frozen=True, slots=True)
class SensitiveValue:
    """Runtime-known sensitive value and its redaction category."""

    value: str
    kind: SensitiveKind

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("sensitive values must be non-empty")


@dataclass(frozen=True, slots=True)
class SensitiveFinding:
    """A finding that deliberately omits the matched secret."""

    kind: SensitiveKind
    start: int
    end: int


class SensitiveDataFoundError(AssertionError):
    """Raised when a fixed security scan finds prohibited content."""

    def __init__(self, source: str, kinds: frozenset[SensitiveKind]) -> None:
        labels = ", ".join(sorted(kind.value for kind in kinds))
        super().__init__(f"sensitive data found in {source}: {labels}")
        self.source = source
        self.kinds = kinds


_PATTERNS: tuple[tuple[SensitiveKind, re.Pattern[str]], ...] = (
    (SensitiveKind.API_KEY, re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")),
    (
        SensitiveKind.API_KEY,
        re.compile(r"(?i)\b(?:api[_-]?key|authorization)\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"),
    ),
    (
        SensitiveKind.COOKIE,
        re.compile(r"(?im)\b(?:cookie|set-cookie)\s*:\s*[^\r\n]+"),
    ),
    (
        SensitiveKind.COOKIE,
        re.compile(r"(?i)\b(?:music_u|__csrf|session(?:id)?)=[^;\s]+"),
    ),
    (
        SensitiveKind.TEMP_AUDIO_URL,
        re.compile(r"(?i)https?://[^\s]+[?&](?:token|sign|signature|expires|auth|key)=[^\s]+"),
    ),
    (
        SensitiveKind.MEDIA_PATH,
        re.compile(r"(?i)(?:[A-Z]:\\|\\\\)[^\r\n\"']+\.(?:mp3|lrc|wav|flac|m4a)\b"),
    ),
)


class SensitiveDataScanner:
    """Redact runtime values and detect required secret patterns."""

    def __init__(self, sensitive_values: Iterable[SensitiveValue] = ()) -> None:
        self._values = tuple(sensitive_values)

    def findings(self, text: str) -> tuple[SensitiveFinding, ...]:
        """Return secret-free finding metadata for the supplied text."""

        findings: list[SensitiveFinding] = []
        for sensitive in self._values:
            start = 0
            while True:
                position = text.find(sensitive.value, start)
                if position < 0:
                    break
                end = position + len(sensitive.value)
                findings.append(SensitiveFinding(sensitive.kind, position, end))
                start = end
        for kind, pattern in _PATTERNS:
            findings.extend(
                SensitiveFinding(kind, match.start(), match.end())
                for match in pattern.finditer(text)
            )
        return tuple(sorted(findings, key=lambda item: (item.start, item.end, item.kind.value)))

    def assert_clean(self, text: str, *, source: str = "output") -> None:
        """Fail closed when any prohibited category remains."""

        findings = self.findings(text)
        if findings:
            raise SensitiveDataFoundError(source, frozenset(item.kind for item in findings))

    def redact(self, text: str) -> str:
        """Replace known and pattern-recognized values with category placeholders."""

        redacted = text
        for sensitive in sorted(self._values, key=lambda item: len(item.value), reverse=True):
            redacted = redacted.replace(sensitive.value, _placeholder(sensitive.kind))
        for kind, pattern in _PATTERNS:
            redacted = pattern.sub(_placeholder(kind), redacted)
        return redacted


def _placeholder(kind: SensitiveKind) -> str:
    return f"[REDACTED_{kind.value.upper()}]"


def serialize_task_records(
    records: Iterable[TaskRecord],
    scanner: SensitiveDataScanner,
) -> str:
    """Serialize query state while excluding arbitrary operation result payloads."""

    payload: list[dict[str, object]] = []
    for record in records:
        error = record.error
        payload.append(
            {
                "task_id": str(record.task_id),
                "task_type": record.task_type.value,
                "status": record.status.value,
                "cancellation": record.cancellation.value,
                "progress": None
                if record.progress is None
                else {
                    "completed": record.progress.completed,
                    "total": record.progress.total,
                    "message": record.progress.message,
                },
                "error": None
                if error is None
                else {
                    "category": error.category.value,
                    "code": error.code,
                    "what_happened": error.what_happened,
                    "data_impact": error.data_impact,
                    "next_action": error.next_action,
                },
            }
        )
    serialized = scanner.redact(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    scanner.assert_clean(serialized, source="task status")
    return serialized
