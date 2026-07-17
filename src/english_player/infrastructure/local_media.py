from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from english_player.lyrics import LyricsDocument, parse_lrc
from english_player.player import AudioSource


class LocalMediaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LocalMediaSelection:
    audio: AudioSource
    display_name: str
    fingerprint: str
    lyrics: LyricsDocument | None
    lyrics_path: Path | None
    lyrics_warning: str | None = None


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _decode_lyrics(path: Path) -> str:
    content = path.read_bytes()
    if not content:
        raise LocalMediaError("歌词文件为空")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise LocalMediaError("歌词文件编码无法识别, 请转换为 UTF-8 或 GB18030")


class LocalMediaAdapter:
    def open(self, mp3_path: Path, lrc_path: Path | None = None) -> LocalMediaSelection:
        resolved_mp3 = mp3_path.expanduser().resolve()
        if resolved_mp3.suffix.lower() != ".mp3":
            raise LocalMediaError("首版只支持 MP3 音频")
        if not resolved_mp3.is_file():
            raise LocalMediaError("MP3 文件不存在或不可读取")
        if resolved_mp3.stat().st_size == 0:
            raise LocalMediaError("MP3 文件为空")

        resolved_lrc = (lrc_path or resolved_mp3.with_suffix(".lrc")).expanduser().resolve()
        lyrics: LyricsDocument | None = None
        warning: str | None = None
        selected_lrc: Path | None = None
        if resolved_lrc.is_file():
            try:
                lyrics = parse_lrc(_decode_lyrics(resolved_lrc))
                selected_lrc = resolved_lrc
            except (OSError, LocalMediaError, ValueError) as error:
                warning = f"歌词未载入: {error}"
        elif lrc_path is not None:
            warning = "歌词文件不存在或不可读取"

        return LocalMediaSelection(
            audio=AudioSource.local(resolved_mp3),
            display_name=resolved_mp3.name,
            fingerprint=_fingerprint(resolved_mp3),
            lyrics=lyrics,
            lyrics_path=selected_lrc,
            lyrics_warning=warning,
        )
