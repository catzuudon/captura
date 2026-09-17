"""System tray icon and menu.

The public surface is a handful of Qt signals plus ``show`` /
``show_update_available`` / ``show_warning``. Behind it sit two backends:

- **macOS** — a native NSStatusItem owned by ``app/platform/macos_tray.py``.
  Qt ≤ 6.11.2's QSystemTrayIcon aborts the whole process on click under
  macOS 27 (``-[NSEvent clickCount]`` on a non-mouse event; fixed upstream but
  unreleased), and owning the item ourselves keeps Qt's crashing observer off
  it entirely, whatever Qt version ships.
- **Everywhere else** — QSystemTrayIcon, as before.
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from app import platform as platform_setup
from app.paths import ASSETS_DIR

_ICON_PATH = ASSETS_DIR / "icon.svg"
# macOS menu-bar icons are expected to be monochrome template images the system
# tints to match the bar — the blue glyph looks out of place there.
_MAC_ICON_PATH = ASSETS_DIR / "icon-tray-macos.svg"


class TrayIcon(QObject):
    capture_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    permissions_requested = pyqtSignal()
    update_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        from app import __version__

        tooltip = f"Captura {__version__}"
        actions = [
            ("Capture", self.capture_requested.emit),
            ("Settings", self.settings_requested.emit),
        ]
        if sys.platform == "darwin":  # only macOS has these privacy permissions
            actions.append(("Permissions…", self.permissions_requested.emit))
        actions.append(("Quit", self.quit_requested.emit))

        self._native = platform_setup.native_tray(
            str(_MAC_ICON_PATH), tooltip, actions, self.update_requested.emit
        )
        self._qt: _QtTray | None = None if self._native else _QtTray(actions, self.update_requested.emit)
        self._base_tooltip = tooltip  # "Captura <version>" — restored when a transient note clears
        if self._qt:
            self._qt.setToolTip(tooltip)

    def _set_tooltip(self, text: str | None) -> None:
        tip = text or self._base_tooltip
        if self._native:
            self._native.set_tooltip(tip)
        else:
            self._qt.setToolTip(tip)

    def show(self) -> None:
        (self._native or self._qt).show()

    def isVisible(self) -> bool:  # noqa: N802 — mirrors QSystemTrayIcon for callers/tests
        return self._native.is_visible() if self._native else self._qt.isVisible()

    def show_update_available(self, version: str) -> None:
        """Reveal a quiet 'Update available' menu item linking to the release."""
        label = f"Update available ({version}) →"
        (self._native or self._qt).set_update(label)
        self._set_tooltip(f"{self._base_tooltip} — update {version} available")

    def show_warning(self, text: str | None) -> None:
        """A disabled status line at the top of the menu (None hides it).

        This is how a system condition that silences the hotkey — macOS Secure
        Keyboard Entry — gets surfaced without a popup: the menu the user opens
        to find out why nothing happens says why."""
        (self._native or self._qt).set_warning(text)
        self._set_tooltip(f"Captura — {text}" if text else None)


class _QtTray(QSystemTrayIcon):
    """QSystemTrayIcon backend for Windows and Linux."""

    def __init__(self, actions, update_callback) -> None:
        super().__init__(QIcon(str(_ICON_PATH)))
        self.setToolTip("Captura")
        menu = QMenu()
        self._warning = menu.addAction("")
        self._warning.setEnabled(False)
        self._warning.setVisible(False)
        self._warning_sep = menu.addSeparator()
        self._warning_sep.setVisible(False)
        for index, (label, callback) in enumerate(actions):
            if index == len(actions) - 1:
                # Hidden until an opt-in update check finds a newer release.
                self._update_sep = menu.addSeparator()
                self._update_sep.setVisible(False)
                self._update = menu.addAction("", update_callback)
                self._update.setVisible(False)
            menu.addAction(label, callback)
        self.setContextMenu(menu)
        self._menu = menu  # the tray icon does not take ownership of its menu

    def set_update(self, label: str) -> None:
        self._update.setText(label)
        self._update_sep.setVisible(True)
        self._update.setVisible(True)

    def set_warning(self, text: str | None) -> None:
        self._warning.setText(text or "")
        self._warning.setVisible(bool(text))
        self._warning_sep.setVisible(bool(text))
