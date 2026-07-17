from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LyricsCapability(StrEnum):
    PLAIN_TEXT = "plain_text"
    LINE_SYNCED = "line_synced"
    WORD_SYNCED = "word_synced"


@dataclass(frozen=True, slots=True)
class LyricWord:
    start_ms: int
    end_ms: int | None
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0:
            raise ValueError("word start must be non-negative")
        if self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("word end must be after word start")
        if not self.text:
            raise ValueError("word text must not be empty")


@dataclass(frozen=True, slots=True)
class LyricLine:
    line_id: str
    start_ms: int
    text: str
    translation: str | None = None
    words: tuple[LyricWord, ...] = ()

    def __post_init__(self) -> None:
        if not self.line_id:
            raise ValueError("line id must not be empty")
        if self.start_ms < 0:
            raise ValueError("line start must be non-negative")
        if any(word.start_ms < self.start_ms for word in self.words):
            raise ValueError("word cannot start before its line")


@dataclass(frozen=True, slots=True)
class LyricsDocument:
    capability: LyricsCapability
    plain_text: str
    lines: tuple[LyricLine, ...]
    source_offset_ms: int = 0

    def __post_init__(self) -> None:
        if self.capability is LyricsCapability.PLAIN_TEXT and self.lines:
            raise ValueError("plain text lyrics cannot contain timed lines")
        if self.capability is not LyricsCapability.PLAIN_TEXT and not self.lines:
            raise ValueError("synced lyrics require timed lines")
        if tuple(sorted(self.lines, key=lambda line: line.start_ms)) != self.lines:
            raise ValueError("lyric lines must be sorted")


@dataclass(frozen=True, slots=True)
class ReplayBoundary:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("invalid replay boundary")
