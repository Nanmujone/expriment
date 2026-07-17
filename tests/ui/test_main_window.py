from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedWidget

from english_player.application.desktop_controller import DesktopController
from english_player.ui.main_window import MainWindowShell


def test_main_window_has_four_routes_and_one_content_area(qtbot) -> None:  # type: ignore[no-untyped-def]
    controller = DesktopController()
    window = MainWindowShell(controller)
    qtbot.addWidget(window)

    stack = window.findChild(QStackedWidget, "mainPages")
    assert stack is not None
    assert stack.count() == 4
    for name in ("libraryButton", "nowPlayingButton", "favoritesButton", "settingsButton"):
        assert window.findChild(object, name) is not None


def test_navigation_button_switches_the_single_content_area(qtbot) -> None:  # type: ignore[no-untyped-def]
    controller = DesktopController()
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
    controller = DesktopController()
    seen_titles: list[str] = []
    seen_lyrics: list[object] = []
    controller.title_changed.connect(seen_titles.append)
    controller.lyrics_changed.connect(seen_lyrics.append)

    assert controller.open_media(mp3)

    assert seen_titles == ["My Lesson"]
    assert len(seen_lyrics) == 1
    assert mp3.read_bytes() == b"ID3demo"
