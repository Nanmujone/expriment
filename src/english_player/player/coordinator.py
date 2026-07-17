from __future__ import annotations

from english_player.lyrics import ReplayBoundary
from english_player.player.models import (
    AudioSource,
    PlaybackQueue,
    PlaybackState,
    SongRef,
)
from english_player.player.ports import PlaybackEngine


class PlaybackCoordinator:
    def __init__(self, engine: PlaybackEngine, queue: PlaybackQueue | None = None) -> None:
        self.engine = engine
        self.queue = queue or PlaybackQueue(())
        self.state = PlaybackState.STOPPED
        self._active_segment: ReplayBoundary | None = None

    def set_queue(self, queue: PlaybackQueue) -> None:
        self.engine.stop()
        self.queue = queue
        self.state = PlaybackState.STOPPED
        self._active_segment = None

    def load_and_play(self, source: AudioSource) -> None:
        self.state = PlaybackState.LOADING
        self.engine.load(source)
        self.engine.play()
        self.state = PlaybackState.PLAYING
        self._active_segment = None

    def pause(self) -> None:
        if self.state is not PlaybackState.PLAYING:
            raise RuntimeError("pause is only valid while playing")
        self.engine.pause()
        self.state = PlaybackState.PAUSED_BY_USER

    def resume(self) -> None:
        if self.state is not PlaybackState.PAUSED_BY_USER:
            raise RuntimeError("resume is only valid after a user pause")
        self.engine.play()
        self.state = PlaybackState.PLAYING

    def stop(self) -> None:
        self.engine.stop()
        self.state = PlaybackState.STOPPED
        self._active_segment = None

    def set_volume(self, volume: float) -> None:
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between zero and one")
        self.engine.set_volume(volume)

    def move_next(self) -> SongRef | None:
        index = self.queue.next_index()
        if index is None:
            return None
        self.queue = self.queue.with_index(index)
        return self.queue.current

    def move_previous(self) -> SongRef | None:
        index = self.queue.previous_index()
        if index is None:
            return None
        self.queue = self.queue.with_index(index)
        return self.queue.current

    def on_media_ended(self) -> SongRef | None:
        next_song = self.move_next()
        if next_song is None:
            self.stop()
        return next_song

    def replay_segment(self, boundary: ReplayBoundary) -> None:
        if self.state not in {PlaybackState.PLAYING, PlaybackState.PAUSED_BY_USER}:
            raise RuntimeError("segment replay requires loaded media")
        self._active_segment = boundary
        self.engine.seek(boundary.start_ms)
        self.engine.play()
        self.state = PlaybackState.PLAYING

    def on_position_changed(self, position_ms: int) -> None:
        if self._active_segment is None or position_ms < self._active_segment.end_ms:
            return
        self.engine.pause()
        self.state = PlaybackState.SEGMENT_COMPLETED

    def continue_after_segment(self) -> None:
        if self.state is not PlaybackState.SEGMENT_COMPLETED or self._active_segment is None:
            raise RuntimeError("no completed segment to continue")
        self.engine.seek(self._active_segment.start_ms)
        self.engine.play()
        self.state = PlaybackState.PLAYING
        self._active_segment = None
