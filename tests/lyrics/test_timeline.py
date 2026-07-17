from english_player.lyrics import (
    LyricLine,
    LyricsCapability,
    LyricsDocument,
    LyricsTimeline,
)


def _document() -> LyricsDocument:
    return LyricsDocument(
        capability=LyricsCapability.LINE_SYNCED,
        plain_text="one\ntwo\nthree",
        lines=(
            LyricLine("line-1", 1000, "one"),
            LyricLine("line-2", 2500, "two"),
            LyricLine("line-3", 5000, "three"),
        ),
    )


def test_locates_lines_across_boundaries_jumps_and_backwards_seek() -> None:
    timeline = LyricsTimeline(_document())

    assert timeline.line_at(999) is None
    assert timeline.line_at(1000).line_id == "line-1"  # type: ignore[union-attr]
    assert timeline.line_at(4999).line_id == "line-2"  # type: ignore[union-attr]
    assert timeline.line_at(1200).line_id == "line-1"  # type: ignore[union-attr]


def test_user_offset_changes_lookup_without_mutating_timestamps() -> None:
    timeline = LyricsTimeline(_document(), user_offset_ms=500)

    assert timeline.line_at(1499) is None
    assert timeline.line_at(1500).line_id == "line-1"  # type: ignore[union-attr]
    assert timeline.document.lines[0].start_ms == 1000


def test_line_replay_uses_next_line_and_last_line_has_no_guessed_end() -> None:
    timeline = LyricsTimeline(_document())

    boundary = timeline.replay_boundary("line-2")
    assert boundary is not None
    assert (boundary.start_ms, boundary.end_ms) == (2500, 5000)
    assert timeline.replay_boundary("line-3") is None


def test_plain_text_cannot_sync_or_replay() -> None:
    timeline = LyricsTimeline(LyricsDocument(LyricsCapability.PLAIN_TEXT, "only text", ()))

    assert timeline.line_at(1000) is None
    assert timeline.replay_boundary("missing") is None
