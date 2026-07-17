from __future__ import annotations

import re

from english_player.lyrics.models import LyricLine, LyricsCapability, LyricsDocument

_TIME_TAG = re.compile(
    r"\[(?P<minutes>\d{1,3}):(?P<seconds>\d{1,2})(?:[.:](?P<fraction>\d{1,3}))?\]"
)
_OFFSET_TAG = re.compile(r"^\[offset:(?P<offset>[+-]?\d+)\]$", re.IGNORECASE)


def _milliseconds(minutes: str, seconds: str, fraction: str | None) -> int | None:
    second_value = int(seconds)
    if second_value >= 60:
        return None
    fraction_value = 0
    if fraction:
        fraction_value = int(fraction.ljust(3, "0")[:3])
    return (int(minutes) * 60 + second_value) * 1000 + fraction_value


def parse_lrc(content: str) -> LyricsDocument:
    source_offset_ms = 0
    timed_rows: list[tuple[int, int, str]] = []
    plain_rows: list[str] = []

    for source_index, raw_row in enumerate(content.splitlines()):
        row = raw_row.strip("\ufeff\r")
        offset_match = _OFFSET_TAG.fullmatch(row.strip())
        if offset_match:
            source_offset_ms = int(offset_match.group("offset"))
            continue

        matches = list(_TIME_TAG.finditer(row))
        if matches:
            text = _TIME_TAG.sub("", row).strip()
            if not text:
                continue
            for match in matches:
                start_ms = _milliseconds(
                    match.group("minutes"), match.group("seconds"), match.group("fraction")
                )
                if start_ms is not None:
                    timed_rows.append((start_ms, source_index, text))
        elif row and not row.startswith("["):
            plain_rows.append(row)

    if not timed_rows:
        return LyricsDocument(
            capability=LyricsCapability.PLAIN_TEXT,
            plain_text="\n".join(plain_rows),
            lines=(),
            source_offset_ms=source_offset_ms,
        )

    timed_rows.sort(key=lambda item: (item[0], item[1]))
    lines = tuple(
        LyricLine(line_id=f"line-{start_ms}-{index}", start_ms=start_ms, text=text)
        for index, (start_ms, _source_index, text) in enumerate(timed_rows)
    )
    return LyricsDocument(
        capability=LyricsCapability.LINE_SYNCED,
        plain_text="\n".join(line.text for line in lines),
        lines=lines,
        source_offset_ms=source_offset_ms,
    )
