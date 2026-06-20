"""System tray icon and menu."""
from __future__ import annotations

import sys

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from app.paths import ASSETS_DIR

_ICON_PATH = ASSETS_DIR / "icon.svg"


class TrayIcon(QSystemTrayIcon):
    capture_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    permissions_requested = pyqtSignal()
    update_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(QIcon(str(_ICON_PATH)))
        self.setToolTip("Captura")
        menu = QMenu()
        menu.addAction("Capture", self.capture_requested.emit)
        menu.addAction("Settings", self.settings_requested.emit)
        if sys.platform == "darwin":  # only macOS has these privacy permissions
            menu.addAction("Permissions…", self.permissions_requested.emit)
        # Hidden until an opt-in update check finds a newer release.
        self._update_separator = menu.addSeparator()
        self._update_separator.setVisible(False)
        self._update_action = menu.addAction("", self.update_requested.emit)
        self._update_action.setVisible(False)
        menu.addAction("Quit", self.quit_requested.emit)
        self.setContextMenu(menu)
        self._menu = menu  # the tray icon does not take ownership of its menu

    def show_update_available(self, version: str) -> None:
        """Reveal a quiet 'Update available' menu item linking to the release."""
        self._update_action.setText(f"Update available ({version}) →")
        self._update_separator.setVisible(True)
        self._update_action.setVisible(True)
        self.setToolTip(f"Captura — update {version} available")
