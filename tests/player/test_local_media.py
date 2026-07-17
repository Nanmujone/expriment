from pathlib import Path

import pytest

from english_player.infrastructure.local_media import LocalMediaAdapter, LocalMediaError
from english_player.lyrics import LyricsCapability


def test_local_media_is_referenced_read_only_and_sidecar_lrc_is_loaded(tmp_path: Path) -> None:
    mp3 = tmp_path / "lesson.mp3"
    lrc = tmp_path / "lesson.lrc"
    mp3.write_bytes(b"ID3original")
    lrc.write_text("[00:01.00]Hello", encoding="utf-8")

    selection = LocalMediaAdapter().open(mp3)

    assert selection.audio.value == str(mp3.resolve())
    assert selection.lyrics is not None
    assert selection.lyrics.capability is LyricsCapability.LINE_SYNCED
    assert mp3.read_bytes() == b"ID3original"


def test_missing_empty_or_non_mp3_files_are_rejected(tmp_path: Path) -> None:
    adapter = LocalMediaAdapter()

    with pytest.raises(LocalMediaError):
        adapter.open(tmp_path / "missing.mp3")
    empty = tmp_path / "empty.mp3"
    empty.touch()
    with pytest.raises(LocalMediaError):
        adapter.open(empty)
    text = tmp_path / "notes.txt"
    text.write_text("not audio", encoding="utf-8")
    with pytest.raises(LocalMediaError):
        adapter.open(text)


def test_explicit_lrc_can_be_gb18030_and_never_blocks_audio(tmp_path: Path) -> None:
    mp3 = tmp_path / "lesson.mp3"
    lrc = tmp_path / "captions.lrc"
    mp3.write_bytes(b"ID3audio")
    lrc.write_bytes("[00:00.50]中文".encode("gb18030"))

    selection = LocalMediaAdapter().open(mp3, lrc)

    assert selection.lyrics is not None
    assert selection.lyrics.lines[0].text == "中文"


def test_invalid_lrc_degrades_to_audio_only(tmp_path: Path) -> None:
    mp3 = tmp_path / "lesson.mp3"
    lrc = tmp_path / "lesson.lrc"
    mp3.write_bytes(b"ID3audio")
    lrc.write_bytes(b"\xff\xfe\x00")

    selection = LocalMediaAdapter().open(mp3)

    assert selection.lyrics is None
    assert selection.lyrics_warning is not None
