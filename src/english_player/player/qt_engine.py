from __future__ import annotations

from typing import Protocol, cast

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from english_player.player.models import AudioSource, AudioSourceKind


class _Player(Protocol):
    def setSource(self, source: QUrl) -> None: ...

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def setPosition(self, position: int) -> None: ...


class _AudioOutput(Protocol):
    def setVolume(self, volume: float) -> None: ...


class QtPlaybackEngine:
    def __init__(
        self, player: _Player | None = None, audio_output: _AudioOutput | None = None
    ) -> None:
        if player is None:
            qt_player = QMediaPlayer()
            qt_output = QAudioOutput()
            qt_player.setAudioOutput(qt_output)
            self.player = cast(_Player, qt_player)
            self.audio_output = cast(_AudioOutput, qt_output)
        else:
            if audio_output is None:
                raise ValueError("audio output is required with a custom player")
            self.player = player
            self.audio_output = audio_output

    def load(self, source: AudioSource) -> None:
        if source.kind is AudioSourceKind.LOCAL:
            url = QUrl.fromLocalFile(source.value)
        else:
            url = QUrl(source.value)
            if url.scheme().lower() != "https":
                raise ValueError("online audio must use HTTPS")
        self.player.setSource(url)

    def play(self) -> None:
        self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def stop(self) -> None:
        self.player.stop()

    def seek(self, position_ms: int) -> None:
        if position_ms < 0:
            raise ValueError("position cannot be negative")
        self.player.setPosition(position_ms)

    def set_volume(self, volume: float) -> None:
        if not 0.0 <= volume <= 1.0:
            raise ValueError("volume must be between zero and one")
        self.audio_output.setVolume(volume)
