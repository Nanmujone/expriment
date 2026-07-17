from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from english_player.application import DesktopController
from english_player.ui.main_window import MainWindowShell


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("English Song Learning Player")
    controller = DesktopController()
    window = MainWindowShell(controller)
    window.show()
    return application.exec()
