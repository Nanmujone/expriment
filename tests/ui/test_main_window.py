from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedWidget

from english_player.ai import AIConfig
from english_player.application.desktop_controller import DesktopController
from english_player.application.state_store import AppStateStore
from english_player.ui.main_window import MainWindowShell


def test_main_window_has_four_routes_and_one_content_area(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = DesktopController(state_store=AppStateStore(tmp_path / "state.json"))
    window = MainWindowShell(controller)
    qtbot.addWidget(window)

    stack = window.findChild(QStackedWidget, "mainPages")
    assert stack is not None
    assert stack.count() == 4
    for name in ("libraryButton", "nowPlayingButton", "favoritesButton", "settingsButton"):
        assert window.findChild(object, name) is not None


def test_navigation_button_switches_the_single_content_area(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = DesktopController(state_store=AppStateStore(tmp_path / "state.json"))
    window = MainWindowShell(controller)
    qtbot.addWidget(window)
    stack = window.findChild(QStackedWidget, "mainPages")
    button = window.findChild(object, "nowPlayingButton")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)  # type: ignore[arg-type]

    assert stack is not None and stack.currentIndex() == 1


def test_opening_local_media_updates_title_and_lyrics_without_copying(tmp_path: Path) -> None:
    mp3 = tmp_path / "My Lesson.mp3"
    lrc = tmp_path / "My Lesson.lrc"
    mp3.write_bytes(b"ID3demo")
    lrc.write_text("[00:00.10]First line\n[00:01.00]Second line", encoding="utf-8")
    store = AppStateStore(tmp_path / "state.json")
    controller = DesktopController(state_store=store)
    seen_titles: list[str] = []
    seen_lyrics: list[object] = []
    controller.title_changed.connect(seen_titles.append)
    controller.lyrics_changed.connect(seen_lyrics.append)

    assert controller.open_media(mp3)

    assert seen_titles == ["My Lesson"]
    assert len(seen_lyrics) == 1
    assert mp3.read_bytes() == b"ID3demo"
    assert store.load_songs()[0].audio_path == str(mp3.resolve())


def test_saved_song_is_visible_after_controller_restart(tmp_path: Path) -> None:
    mp3 = tmp_path / "Remember Me.mp3"
    mp3.write_bytes(b"ID3demo")
    store = AppStateStore(tmp_path / "state.json")
    first = DesktopController(state_store=store)
    assert first.open_media(mp3)

    restarted = DesktopController(state_store=store)

    assert [song.title for song in restarted.saved_songs] == ["Remember Me"]


def test_ai_worker_failure_recovers_without_leaving_busy_state(
    qtbot, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    class Credentials:
        @staticmethod
        def load() -> str:
            return "test-key"

    class FailingClient:
        def __init__(self, _config: AIConfig) -> None:
            pass

        @staticmethod
        def analyze(_lyrics: str, _api_key: str) -> None:
            raise ValueError("模拟服务失败")

    controller = DesktopController(state_store=AppStateStore(tmp_path / "state.json"))
    controller._credentials = {"deepseek": Credentials()}  # type: ignore[assignment]
    controller._lyrics_text = "Test lyrics"
    monkeypatch.setattr(
        "english_player.application.desktop_controller.OpenAIChatClient", FailingClient
    )
    busy: list[bool] = []
    messages: list[str] = []
    controller.analysis_busy_changed.connect(busy.append)
    controller.status_message.connect(messages.append)

    controller.analyze_current_lyrics()
    qtbot.waitUntil(lambda: busy == [True, False], timeout=3000)

    assert messages[-1] == "模拟服务失败"
    assert not controller._analysis_workers
