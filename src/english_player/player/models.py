from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path


class PlaybackMode(StrEnum):
    SEQUENTIAL = "sequential"
    REPEAT_LIST = "repeat_list"


class PlaybackState(StrEnum):
    STOPPED = "stopped"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED_BY_USER = "paused_by_user"
    SEGMENT_COMPLETED = "segment_completed"
    ERROR = "error"


class AudioSourceKind(StrEnum):
    LOCAL = "local"
    TRANSIENT_ONLINE = "transient_online"


@dataclass(frozen=True, slots=True)
class SongRef:
    song_id: str
    title: str

    def __post_init__(self) -> None:
        if not self.song_id or not self.title:
            raise ValueError("song id and title are required")


@dataclass(frozen=True, slots=True)
class AudioSource:
    kind: AudioSourceKind
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("audio source value is required")

    @classmethod
    def local(cls, path: Path) -> AudioSource:
        return cls(AudioSourceKind.LOCAL, str(path))

    @classmethod
    def transient_online(cls, url: str) -> AudioSource:
        return cls(AudioSourceKind.TRANSIENT_ONLINE, url)


@dataclass(frozen=True, slots=True)
class PlaybackQueue:
    songs: tuple[SongRef, ...]
    current_index: int | None = None
    mode: PlaybackMode = PlaybackMode.SEQUENTIAL

    def __post_init__(self) -> None:
        if not self.songs:
            if self.current_index is not None:
                raise ValueError("empty queue cannot have a current index")
            return
        if self.current_index is None or not 0 <= self.current_index < len(self.songs):
            raise ValueError("current index is outside the queue")

    @property
    def current(self) -> SongRef | None:
        if self.current_index is None:
            return None
        return self.songs[self.current_index]

    def with_index(self, index: int) -> PlaybackQueue:
        return replace(self, current_index=index)

    def next_index(self) -> int | None:
        if self.current_index is None:
            return None
        candidate = self.current_index + 1
        if candidate < len(self.songs):
            return candidate
        return 0 if self.mode is PlaybackMode.REPEAT_LIST else None

    def previous_index(self) -> int | None:
        if self.current_index is None:
            return None
        candidate = self.current_index - 1
        if candidate >= 0:
            return candidate
        return len(self.songs) - 1 if self.mode is PlaybackMode.REPEAT_LIST else None
