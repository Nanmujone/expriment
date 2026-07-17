from __future__ import annotations

from typing import Protocol

from english_player.player.models import AudioSource


class AudioSourceProvider(Protocol):
    def resolve(self, song_id: str) -> AudioSource: ...


class MediaFileProvider(Protocol):
    def resolve_local(self, song_id: str) -> AudioSource | None: ...


class PlaybackEngine(Protocol):
    def load(self, source: AudioSource) -> None: ...

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def seek(self, position_ms: int) -> None: ...

    def set_volume(self, volume: float) -> None: ...
