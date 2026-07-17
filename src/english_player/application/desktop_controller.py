from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from english_player.ai import AIConfig, CredentialStore, OpenAIChatClient, SongAnalysis
from english_player.infrastructure.local_media import LocalMediaAdapter, LocalMediaError
from english_player.lyrics import LyricsTimeline
from english_player.player import (
    PlaybackCoordinator,
    PlaybackQueue,
    PlaybackState,
    SongRef,
)
from english_player.player.qt_engine import QtPlaybackEngine


class DesktopController(QObject):
    title_changed = Signal(str)
    lyrics_changed = Signal(object)
    current_line_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(str)
    status_message = Signal(str)
    analysis_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._engine = QtPlaybackEngine(self._player, self._audio_output)
        self._coordinator = PlaybackCoordinator(self._engine)
        self._local_media = LocalMediaAdapter()
        self._timeline: LyricsTimeline | None = None
        self._lyrics_text = ""
        self._current_line_id: str | None = None
        self._ai_config: AIConfig | None = None
        self._credentials = CredentialStore()

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self.duration_changed.emit)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_player_error)
        self._audio_output.setVolume(0.7)

    @property
    def state(self) -> PlaybackState:
        return self._coordinator.state

    def open_media(self, mp3_path: Path, lrc_path: Path | None = None) -> bool:
        try:
            selection = self._local_media.open(mp3_path, lrc_path)
        except (LocalMediaError, OSError) as error:
            self.status_message.emit(str(error))
            return False

        song = SongRef(selection.fingerprint, Path(selection.audio.value).stem)
        self._coordinator.set_queue(PlaybackQueue((song,), 0))
        self._timeline = LyricsTimeline(selection.lyrics) if selection.lyrics else None
        self._lyrics_text = selection.lyrics.plain_text if selection.lyrics else ""
        self._current_line_id = None
        self.title_changed.emit(song.title)
        self.lyrics_changed.emit(selection.lyrics)
        if selection.lyrics_warning:
            self.status_message.emit(selection.lyrics_warning)
        self._coordinator.load_and_play(selection.audio)
        self.state_changed.emit(self._coordinator.state.value)
        return True

    def toggle_playback(self) -> None:
        if self._coordinator.state is PlaybackState.PLAYING:
            self._coordinator.pause()
        elif self._coordinator.state is PlaybackState.PAUSED_BY_USER:
            self._coordinator.resume()
        else:
            self.status_message.emit("请先选择本地 MP3")
            return
        self.state_changed.emit(self._coordinator.state.value)

    def seek(self, position_ms: int) -> None:
        if position_ms >= 0:
            self._engine.seek(position_ms)

    def set_volume_percent(self, percent: int) -> None:
        self._coordinator.set_volume(max(0, min(100, percent)) / 100)

    def stop(self) -> None:
        self._coordinator.stop()
        self.state_changed.emit(self._coordinator.state.value)

    def configure_ai(self, endpoint: str, model: str, api_key: str) -> None:
        config = AIConfig(endpoint.strip(), model.strip())
        if api_key:
            self._credentials.save(api_key)
        elif self._credentials.load() is None:
            raise ValueError("请输入 API 密钥")
        self._ai_config = config
        self.status_message.emit("AI 设置已保存; 密钥存放在 Windows 凭据库")

    def analyze_current_lyrics(self) -> None:
        if self._ai_config is None:
            self.status_message.emit("请先在设置中配置 AI 服务")
            return
        api_key = self._credentials.load()
        if not api_key:
            self.status_message.emit("AI API 密钥不存在; 请重新保存")
            return
        if not self._lyrics_text:
            self.status_message.emit("当前歌曲没有可解析的歌词")
            return
        config = self._ai_config
        self.status_message.emit("AI 正在解析歌词...")
        worker = _AnalysisWorker(
            lambda: OpenAIChatClient(config).analyze(self._lyrics_text, api_key)
        )
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.failed.connect(self.status_message.emit)
        QThreadPool.globalInstance().start(worker)

    def _on_analysis_finished(self, analysis: SongAnalysis) -> None:
        self.analysis_changed.emit(analysis.to_plain_text())
        self.status_message.emit("AI 解析完成")

    def _on_position_changed(self, position_ms: int) -> None:
        self._coordinator.on_position_changed(position_ms)
        self.position_changed.emit(position_ms)
        if self._timeline is None:
            return
        line = self._timeline.line_at(position_ms)
        line_id = line.line_id if line else None
        if line_id != self._current_line_id:
            self._current_line_id = line_id
            self.current_line_changed.emit(line_id or "")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status is QMediaPlayer.MediaStatus.EndOfMedia:
            self._coordinator.on_media_ended()
            self.state_changed.emit(self._coordinator.state.value)

    def _on_player_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if message:
            self.status_message.emit(f"音频播放失败: {message}")


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _AnalysisWorker(QRunnable):
    def __init__(self, operation: Callable[[], SongAnalysis]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = self.operation()
        except (ValueError, OSError) as error:
            self.signals.failed.emit(str(error))
            return
        self.signals.finished.emit(result)
