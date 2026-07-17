from __future__ import annotations

from bisect import bisect_right

from english_player.lyrics.models import (
    LyricLine,
    LyricsCapability,
    LyricsDocument,
    ReplayBoundary,
)


class LyricsTimeline:
    def __init__(self, document: LyricsDocument, user_offset_ms: int = 0) -> None:
        self.document = document
        self.user_offset_ms = user_offset_ms
        self._starts = tuple(line.start_ms for line in document.lines)
        self._lines_by_id = {line.line_id: line for line in document.lines}

    @property
    def total_offset_ms(self) -> int:
        return self.document.source_offset_ms + self.user_offset_ms

    def line_at(self, playback_ms: int) -> LyricLine | None:
        if self.document.capability is LyricsCapability.PLAIN_TEXT:
            return None
        lyric_ms = playback_ms - self.total_offset_ms
        index = bisect_right(self._starts, lyric_ms) - 1
        return self.document.lines[index] if index >= 0 else None

    def replay_boundary(self, line_id: str) -> ReplayBoundary | None:
        line = self._lines_by_id.get(line_id)
        if line is None or self.document.capability is LyricsCapability.PLAIN_TEXT:
            return None

        if self.document.capability is LyricsCapability.WORD_SYNCED and line.words:
            end_ms = line.words[-1].end_ms
            if end_ms is None:
                return None
        else:
            try:
                index = self.document.lines.index(line)
                end_ms = self.document.lines[index + 1].start_ms
            except (ValueError, IndexError):
                return None

        offset = self.total_offset_ms
        return ReplayBoundary(line.start_ms + offset, end_ms + offset)
