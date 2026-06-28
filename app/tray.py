"""System tray icon and menu."""
from __future__ import annotations

import sys

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from app.paths import ASSETS_DIR

_ICON_PATH = ASSETS_DIR / "icon.svg"


def _tray_icon() -> QIcon:
    # macOS menu-bar icons are expected to be monochrome template images that
    # the system tints to match the bar — the blue glyph looks out of place
    # there. Use a white template glyph and mark it as a mask so macOS renders
    # it black/white automatically. Every other platform keeps the blue glyph.
    if sys.platform == "darwin":
        icon = QIcon(str(ASSETS_DIR / "icon-tray-macos.svg"))
        icon.setIsMask(True)
        return icon
    return QIcon(str(_ICON_PATH))


class TrayIcon(QSystemTrayIcon):
    capture_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    permissions_requested = pyqtSignal()
    update_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(_tray_icon())
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
