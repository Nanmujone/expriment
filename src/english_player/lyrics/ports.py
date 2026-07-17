from __future__ import annotations

from typing import Protocol

from english_player.lyrics.models import LyricsDocument


class LyricsProvider(Protocol):
    def load(self, song_id: str) -> LyricsDocument | None: ...


class LyricsRepository(Protocol):
    def get(self, song_id: str) -> LyricsDocument | None: ...

    def save(self, song_id: str, document: LyricsDocument) -> None: ...

    def get_user_offset_ms(self, song_id: str) -> int: ...

    def set_user_offset_ms(self, song_id: str, offset_ms: int) -> None: ...
