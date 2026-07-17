from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from english_player.application import DesktopController
from english_player.lyrics import LyricsDocument
from english_player.player import PlaybackState


class MainWindowShell(QMainWindow):
    def __init__(self, controller: DesktopController) -> None:
        super().__init__()
        self.controller = controller
        self._line_rows: dict[str, int] = {}
        self.setWindowTitle("English Song Learning Player")
        self.resize(1050, 680)

        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        sidebar = QVBoxLayout()
        self.pages = QStackedWidget()
        self.pages.setObjectName("mainPages")

        routes = (
            ("歌单", "libraryButton", self._create_library_page()),
            ("正在播放", "nowPlayingButton", self._create_now_playing_page()),
            ("词句收藏", "favoritesButton", self._placeholder("词句收藏", "收藏功能即将接入")),
            ("设置", "settingsButton", self._create_settings_page()),
        )
        for index, (label, object_name, page) in enumerate(routes):
            button = QPushButton(label)
            button.setObjectName(object_name)
            button.setCheckable(True)
            button.setAccessibleName(label)
            button.clicked.connect(lambda _checked=False, route=index: self._navigate(route))
            sidebar.addWidget(button)
            self.pages.addWidget(page)
        sidebar.addStretch()
        root_layout.addLayout(sidebar, 0)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self.controller.title_changed.connect(self.title_label.setText)
        self.controller.lyrics_changed.connect(self._show_lyrics)
        self.controller.current_line_changed.connect(self._highlight_line)
        self.controller.position_changed.connect(self.position_slider.setValue)
        self.controller.duration_changed.connect(self.position_slider.setMaximum)
        self.controller.state_changed.connect(self._show_state)
        self.controller.status_message.connect(self._show_status)
        self.controller.analysis_changed.connect(self.analysis_view.setPlainText)
        self.controller.analysis_busy_changed.connect(self._show_analysis_busy)
        self.controller.library_changed.connect(self._show_library)
        self._show_library(self.controller.saved_songs)

    def _create_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel("本地曲库")
        heading.setStyleSheet("font-size: 24px; font-weight: 600")
        banner = QLabel(
            "精简首版: 网易云在线入口暂不可用。请选择你有权用于个人学习的本地 MP3; "
            "同名 LRC 会自动载入。"
        )
        banner.setWordWrap(True)
        banner.setStyleSheet("padding: 12px; background: #fff4ce; border-radius: 6px")
        open_button = QPushButton("选择本地 MP3")
        open_button.setObjectName("openLocalButton")
        open_button.setAccessibleName("选择本地 MP3")
        open_button.clicked.connect(self._choose_local_media)
        self.library_list = QListWidget()
        self.library_list.setObjectName("localLibraryList")
        self.library_list.setAccessibleName("本地歌单")
        self.library_list.itemDoubleClicked.connect(self._play_library_item)
        self.status_label = QLabel("尚未选择歌曲")
        self.status_label.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(banner)
        layout.addWidget(open_button)
        layout.addWidget(QLabel("已保存歌曲 (双击播放)"))
        layout.addWidget(self.library_list, 1)
        layout.addWidget(self.status_label)
        return page

    def _create_now_playing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.title_label = QLabel("未播放")
        self.title_label.setObjectName("trackTitle")
        self.title_label.setStyleSheet("font-size: 22px; font-weight: 600")
        self.lyrics_list = QListWidget()
        self.lyrics_list.setObjectName("lyricsList")
        self.lyrics_list.setAccessibleName("歌词")
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setObjectName("positionSlider")
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.controller.seek)
        self.analysis_view = QPlainTextEdit()
        self.analysis_view.setObjectName("analysisView")
        self.analysis_view.setReadOnly(True)
        self.analysis_view.setPlaceholderText("AI 解析会显示在这里")
        controls = QHBoxLayout()
        self.play_button = QPushButton("播放/暂停")
        self.play_button.setObjectName("playPauseButton")
        self.play_button.clicked.connect(self.controller.toggle_playback)
        self.analyze_button = QPushButton("AI 解析歌词")
        self.analyze_button.setObjectName("analyzeButton")
        self.analyze_button.clicked.connect(self._confirm_ai_analysis)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setObjectName("volumeSlider")
        volume.setRange(0, 100)
        volume.setValue(70)
        volume.valueChanged.connect(self.controller.set_volume_percent)
        controls.addWidget(self.play_button)
        controls.addWidget(self.analyze_button)
        controls.addWidget(QLabel("音量"))
        controls.addWidget(volume)
        layout.addWidget(self.title_label)
        layout.addWidget(self.lyrics_list, 1)
        layout.addWidget(self.analysis_view, 1)
        layout.addWidget(self.position_slider)
        layout.addLayout(controls)
        return page

    def _create_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel("AI 设置")
        heading.setStyleSheet("font-size: 24px; font-weight: 600")
        privacy = QLabel("API 密钥只写入 Windows 凭据库, 不保存到项目、数据库、日志或备份。")
        privacy.setWordWrap(True)
        form = QFormLayout()
        self.ai_provider = QComboBox()
        self.ai_provider.addItem("DeepSeek", "deepseek")
        self.ai_provider.addItem("OpenAI 兼容服务", "openai")
        config = self.controller.ai_config
        provider_index = self.ai_provider.findData(config.provider)
        self.ai_provider.setCurrentIndex(max(0, provider_index))
        self.ai_provider.currentIndexChanged.connect(self._provider_changed)
        self.ai_endpoint = QLineEdit(config.endpoint)
        self.ai_model = QLineEdit(config.model)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key.setPlaceholderText("保存后不会回显")
        form.addRow("服务商", self.ai_provider)
        form.addRow("服务地址", self.ai_endpoint)
        form.addRow("模型", self.ai_model)
        form.addRow("API 密钥", self.ai_key)
        save_button = QPushButton("保存 AI 设置")
        save_button.clicked.connect(self._save_ai_settings)
        api_key_button = QPushButton("打开 DeepSeek API 密钥页面")
        api_key_button.setObjectName("deepSeekApiKeysButton")
        api_key_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://platform.deepseek.com/api_keys"))
        )
        top_up_button = QPushButton("打开 DeepSeek 充值页面")
        top_up_button.setObjectName("deepSeekTopUpButton")
        top_up_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://platform.deepseek.com/top_up"))
        )
        deepseek_hint = QLabel(
            "DeepSeek 推荐配置: 地址 https://api.deepseek.com, 模型 deepseek-v4-flash。"
            "先在密钥页面创建密钥, 再充值少量余额即可测试。"
        )
        deepseek_hint.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(privacy)
        layout.addLayout(form)
        layout.addWidget(save_button)
        layout.addWidget(api_key_button)
        layout.addWidget(top_up_button)
        layout.addWidget(deepseek_hint)
        layout.addStretch()
        return page

    @staticmethod
    def _placeholder(title: str, detail: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 24px; font-weight: 600")
        layout.addWidget(heading)
        layout.addWidget(QLabel(detail))
        layout.addStretch()
        return page

    def _navigate(self, route: int) -> None:
        self.pages.setCurrentIndex(route)

    def _choose_local_media(self) -> None:
        answer = QMessageBox.question(
            self,
            "关联本地媒体",
            "文件只会被只读引用, 不会复制、上传或删除。请确认你有权将其用于个人学习。",
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        filename, _filter = QFileDialog.getOpenFileName(
            self, "选择本地 MP3", "", "MP3 音频 (*.mp3)"
        )
        if filename and self.controller.open_media(Path(filename)):
            self.pages.setCurrentIndex(1)

    def _save_ai_settings(self) -> None:
        try:
            self.controller.configure_ai(
                str(self.ai_provider.currentData()),
                self.ai_endpoint.text(),
                self.ai_model.text(),
                self.ai_key.text(),
            )
        except ValueError as error:
            self.status_label.setText(str(error))
            return
        self.ai_key.clear()

    def _provider_changed(self, _index: int) -> None:
        if self.ai_provider.currentData() == "deepseek":
            self.ai_endpoint.setText("https://api.deepseek.com")
            self.ai_model.setText("deepseek-v4-flash")
        else:
            self.ai_endpoint.setText("https://api.openai.com/v1")
            self.ai_model.setText("gpt-5.6-terra")

    def _show_library(self, songs: object) -> None:
        self.library_list.clear()
        if not isinstance(songs, tuple):
            return
        for song in songs:
            audio_path = Path(song.audio_path)
            suffix = "" if audio_path.is_file() else " (文件已移动或删除)"
            item = QListWidgetItem(f"{song.title}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, song.audio_path)
            item.setData(Qt.ItemDataRole.UserRole + 1, song.lyrics_path)
            self.library_list.addItem(item)

    def _play_library_item(self, item: QListWidgetItem) -> None:
        audio_path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        lyrics_value = item.data(Qt.ItemDataRole.UserRole + 1)
        lyrics_path = Path(str(lyrics_value)) if lyrics_value else None
        if self.controller.open_media(audio_path, lyrics_path):
            self.pages.setCurrentIndex(1)

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.statusBar().showMessage(message)

    def _show_analysis_busy(self, busy: bool) -> None:
        self.analyze_button.setEnabled(not busy)
        self.analyze_button.setText("AI 正在解析…" if busy else "AI 解析歌词")

    def _confirm_ai_analysis(self) -> None:
        answer = QMessageBox.question(
            self,
            "发送歌词到 AI",
            "将把当前歌词发送到你配置的 AI 服务用于解析。是否继续?",
        )
        if answer is QMessageBox.StandardButton.Yes:
            self.controller.analyze_current_lyrics()

    def _show_lyrics(self, value: object) -> None:
        self.lyrics_list.clear()
        self._line_rows.clear()
        if not isinstance(value, LyricsDocument):
            self.lyrics_list.addItem("未找到可用歌词; 可继续播放音频")
            return
        if value.lines:
            for index, line in enumerate(value.lines):
                self._line_rows[line.line_id] = index
                self.lyrics_list.addItem(line.text)
        else:
            for row in value.plain_text.splitlines() or ["歌词为空"]:
                self.lyrics_list.addItem(row)

    def _highlight_line(self, line_id: str) -> None:
        row = self._line_rows.get(line_id)
        if row is not None:
            self.lyrics_list.setCurrentRow(row)
            self.lyrics_list.scrollToItem(self.lyrics_list.item(row))

    def _show_state(self, state: str) -> None:
        if state == PlaybackState.PLAYING.value:
            self.play_button.setText("暂停")
        elif state == PlaybackState.PAUSED_BY_USER.value:
            self.play_button.setText("继续")
        else:
            self.play_button.setText("播放/暂停")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.controller.stop()
        event.accept()
