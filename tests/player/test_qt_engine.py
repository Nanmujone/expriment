from pathlib import Path

from PySide6.QtCore import QUrl

from english_player.player import AudioSource
from english_player.player.qt_engine import QtPlaybackEngine


class FakePlayer:
    def __init__(self) -> None:
        self.source: QUrl | None = None
        self.commands: list[tuple[str, int | None]] = []

    def setSource(self, source: QUrl) -> None:
        self.source = source

    def play(self) -> None:
        self.commands.append(("play", None))

    def pause(self) -> None:
        self.commands.append(("pause", None))

    def stop(self) -> None:
        self.commands.append(("stop", None))

    def setPosition(self, position: int) -> None:
        self.commands.append(("seek", position))


class FakeAudioOutput:
    def __init__(self) -> None:
        self.volume = 0.0

    def setVolume(self, volume: float) -> None:
        self.volume = volume


def test_qt_engine_maps_local_source_and_commands(tmp_path: Path) -> None:
    player = FakePlayer()
    output = FakeAudioOutput()
    engine = QtPlaybackEngine(player, output)
    path = (tmp_path / "song.mp3").resolve()

    engine.load(AudioSource.local(path))
    engine.play()
    engine.seek(1234)
    engine.pause()
    engine.stop()
    engine.set_volume(0.25)

    assert player.source is not None and player.source.isLocalFile()
    assert Path(player.source.toLocalFile()) == path
    assert player.commands == [
        ("play", None),
        ("seek", 1234),
        ("pause", None),
        ("stop", None),
    ]
    assert output.volume == 0.25
