from english_player.lyrics import LyricsCapability, parse_lrc


def test_parses_multiple_timestamps_translation_and_offset() -> None:
    document = parse_lrc("[offset:250]\n[00:01.00][00:02.50]Hello world\n[00:03.00]你好世界\n")

    assert document.capability is LyricsCapability.LINE_SYNCED
    assert [(line.start_ms, line.text) for line in document.lines] == [
        (1000, "Hello world"),
        (2500, "Hello world"),
        (3000, "你好世界"),
    ]
    assert document.source_offset_ms == 250


def test_damaged_timed_rows_are_ignored_without_blocking_valid_rows() -> None:
    document = parse_lrc("[broken]ignored\n[00:01.20]usable\n[00:99.00]bad\n")

    assert [(line.start_ms, line.text) for line in document.lines] == [(1200, "usable")]


def test_plain_text_degrades_without_inventing_timing() -> None:
    document = parse_lrc("First line\nSecond line")

    assert document.capability is LyricsCapability.PLAIN_TEXT
    assert document.plain_text == "First line\nSecond line"
    assert document.lines == ()
