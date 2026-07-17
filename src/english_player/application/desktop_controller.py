from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from english_player.ai import AIConfig, CredentialStore, OpenAIChatClient, SongAnalysis
from english_player.application.state_store import AppStateStore, SavedAISettings, SavedSong
from english_player.infrastructure.local_media import LocalMediaAdapter, LocalMediaError
from english_player.infrastructure.persistence.paths import default_user_data_paths
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
    analysis_busy_changed = Signal(bool)
    library_changed = Signal(object)

    def __init__(
        self, parent: QObject | None = None, *, state_store: AppStateStore | None = None
    ) -> None:
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
        self._state_store = state_store or AppStateStore(
            default_user_data_paths().data_directory / "app_state.json"
        )
        saved_ai = self._state_store.load_ai_settings()
        self._ai_config: AIConfig | None = AIConfig(
            saved_ai.endpoint, saved_ai.model, provider=saved_ai.provider
        )
        self._credentials = {
            "openai": CredentialStore("openai"),
            "deepseek": CredentialStore("deepseek"),
        }
        self._analysis_workers: set[_AnalysisWorker] = set()

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self.duration_changed.emit)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_player_error)
        self._audio_output.setVolume(0.7)

    @property
    def state(self) -> PlaybackState:
        return self._coordinator.state

    @property
    def saved_songs(self) -> tuple[SavedSong, ...]:
        return self._state_store.load_songs()

    @property
    def ai_config(self) -> AIConfig:
        assert self._ai_config is not None
        return self._ai_config

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
        detected_lrc = lrc_path
        if detected_lrc is None and mp3_path.with_suffix(".lrc").is_file():
            detected_lrc = mp3_path.with_suffix(".lrc")
        try:
            songs = self._state_store.save_song(
                SavedSong(
                    audio_path=str(mp3_path.resolve()),
                    title=song.title,
                    lyrics_path=str(detected_lrc.resolve()) if detected_lrc else None,
                )
            )
        except OSError:
            self.status_message.emit("歌曲可以播放, 但未能保存到歌单")
        else:
            self.library_changed.emit(songs)
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

    def configure_ai(self, provider: str, endpoint: str, model: str, api_key: str) -> None:
        config = AIConfig(endpoint.strip(), model.strip(), provider=provider)
        credentials = self._credentials[provider]
        if api_key:
            credentials.save(api_key)
        elif credentials.load() is None:
            raise ValueError("请输入 API 密钥")
        self._ai_config = config
        self._state_store.save_ai_settings(
            SavedAISettings(provider=provider, endpoint=config.endpoint, model=config.model)
        )
        self.status_message.emit("AI 设置已保存; 密钥存放在 Windows 凭据库")

    def analyze_current_lyrics(self) -> None:
        if self._ai_config is None:
            self.status_message.emit("请先在设置中配置 AI 服务")
            return
        api_key = self._credentials[self._ai_config.provider].load()
        if not api_key:
            self.status_message.emit("AI API 密钥不存在; 请重新保存")
            return
        if not self._lyrics_text:
            self.status_message.emit("当前歌曲没有可解析的歌词")
            return
        config = self._ai_config
        self.status_message.emit("AI 正在解析歌词...")
        self.analysis_busy_changed.emit(True)
        worker = _AnalysisWorker(
            lambda: OpenAIChatClient(config).analyze(self._lyrics_text, api_key)
        )
        worker.setAutoDelete(False)
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.failed.connect(self.status_message.emit)
        worker.signals.completed.connect(lambda: self._finish_worker(worker))
        self._analysis_workers.add(worker)
        QThreadPool.globalInstance().start(worker)

    def _finish_worker(self, worker: _AnalysisWorker) -> None:
        self._analysis_workers.discard(worker)
        self.analysis_busy_changed.emit(False)

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
    completed = Signal()


class _AnalysisWorker(QRunnable):
    def __init__(self, operation: Callable[[], SongAnalysis]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = self.operation()
        except Exception as error:
            self.signals.failed.emit(str(error) or "AI 解析失败, 请检查网络和余额")
        else:
            self.signals.finished.emit(result)
        finally:
            self.signals.completed.emit()
