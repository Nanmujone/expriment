from pathlib import Path

import pytest

from english_player.lyrics import ReplayBoundary
from english_player.player import (
    AudioSource,
    PlaybackCoordinator,
    PlaybackMode,
    PlaybackQueue,
    PlaybackState,
    SongRef,
)


class FakeEngine:
    def __init__(self) -> None:
        self.commands: list[tuple[str, object | None]] = []

    def load(self, source: AudioSource) -> None:
        self.commands.append(("load", source))

    def play(self) -> None:
        self.commands.append(("play", None))

    def pause(self) -> None:
        self.commands.append(("pause", None))

    def stop(self) -> None:
        self.commands.append(("stop", None))

    def seek(self, position_ms: int) -> None:
        self.commands.append(("seek", position_ms))

    def set_volume(self, volume: float) -> None:
        self.commands.append(("volume", volume))


def _coordinator() -> tuple[PlaybackCoordinator, FakeEngine]:
    engine = FakeEngine()
    queue = PlaybackQueue(
        (SongRef("one", "One"), SongRef("two", "Two")),
        0,
        PlaybackMode.SEQUENTIAL,
    )
    return PlaybackCoordinator(engine, queue), engine


def test_load_play_pause_and_volume_commands_share_one_state_machine() -> None:
    coordinator, engine = _coordinator()
    source = AudioSource.local(Path("song.mp3"))

    coordinator.load_and_play(source)
    coordinator.pause()
    coordinator.resume()
    coordinator.set_volume(0.4)

    assert coordinator.state is PlaybackState.PLAYING
    assert [command[0] for command in engine.commands] == [
        "load",
        "play",
        "pause",
        "play",
        "volume",
    ]


def test_invalid_transition_is_rejected() -> None:
    coordinator, _engine = _coordinator()

    with pytest.raises(RuntimeError):
        coordinator.pause()


def test_segment_replay_pauses_at_real_boundary_and_continue_restarts_sentence() -> None:
    coordinator, engine = _coordinator()
    coordinator.load_and_play(AudioSource.local(Path("song.mp3")))
    coordinator.replay_segment(ReplayBoundary(1000, 2500))

    coordinator.on_position_changed(2499)
    assert coordinator.state is PlaybackState.PLAYING
    coordinator.on_position_changed(2500)
    assert coordinator.state is PlaybackState.SEGMENT_COMPLETED

    coordinator.continue_after_segment()
    assert coordinator.state is PlaybackState.PLAYING
    assert engine.commands[-2:] == [("seek", 1000), ("play", None)]


def test_natural_end_advances_or_stops() -> None:
    coordinator, _engine = _coordinator()

    assert coordinator.on_media_ended() == SongRef("two", "Two")
    assert coordinator.on_media_ended() is None
    assert coordinator.state is PlaybackState.STOPPED
