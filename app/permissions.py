"""macOS permissions status window, opened from the tray.

Gives visible feedback for each permission instead of silently firing native
prompts (which don't appear when macOS already knows the app). Each row shows
the live granted-state and a button that opens the relevant Settings pane and
triggers the native prompt.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import platform as platform_setup

# (name, description, required?)
_PERMISSIONS = [
    ("Screen Recording", "Capture the screen", True),
    ("Input Monitoring", "Use the global capture hotkey", True),
    ("Accessibility", "Stop the hotkey reaching other apps", False),
]

_STYLE = """
QWidget#permissions { background: #232323; }
QLabel { color: #c8c8c8; font-size: 12px; }
QLabel#title { color: #f0f0f0; font-size: 16px; font-weight: 600; }
QLabel#subtitle { color: #888; font-size: 11px; }
QLabel#desc { color: #888; font-size: 11px; }
QLabel#granted { color: #5fcf80; font-size: 12px; }
QLabel#missing { color: #e0a060; font-size: 12px; }
QFrame#sep { background: #383838; max-height: 1px; min-height: 1px; border: none; }
QPushButton {
    background: #333333; color: #ececec; border: 1px solid #4a4a4a;
    border-radius: 6px; padding: 5px 12px; font-size: 12px;
}
QPushButton:hover { background: #3c3c3c; border-color: #5a5a5a; }
"""


class PermissionsPanel(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("permissions")
        self.setStyleSheet(_STYLE)
        self.setWindowTitle("Captura Permissions")
        self.setFixedWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(4)

        title = QLabel("Permissions")
        title.setObjectName("title")
        subtitle = QLabel("macOS asks you to grant these in System Settings")
        subtitle.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        sep = QFrame()
        sep.setObjectName("sep")
        outer.addSpacing(12)
        outer.addWidget(sep)
        outer.addSpacing(8)

        self._rows: list[tuple[str, QLabel, QPushButton]] = []
        for name, desc, required in _PERMISSIONS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 8, 0, 8)
            text = QVBoxLayout()
            text.setSpacing(2)
            label = QLabel(name if required else f"{name} (optional)")
            description = QLabel(desc)
            description.setObjectName("desc")
            text.addWidget(label)
            text.addWidget(description)
            row.addLayout(text)
            row.addStretch(1)
            status = QLabel()
            row.addWidget(status)
            button = QPushButton("Open Settings")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, n=name: self._grant(n))
            row.addWidget(button)
            outer.addLayout(row)
            self._rows.append((name, status, button))

        # Not a permission, but it fails the same way one does — hotkey silent,
        # every grant present — so it belongs on this screen. macOS delivers
        # keystrokes to no event tap while any process holds Secure Keyboard
        # Entry (a password field, Terminal's Secure Keyboard Entry, or
        # loginwindow lingering after an unlock).
        sep2 = QFrame()
        sep2.setObjectName("sep")
        outer.addSpacing(8)
        outer.addWidget(sep2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 8)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(QLabel("Keyboard events"))
        self._secure_desc = QLabel("Reach the hotkey only while no app holds Secure Keyboard Entry")
        self._secure_desc.setObjectName("desc")
        self._secure_desc.setWordWrap(True)
        text.addWidget(self._secure_desc)
        row.addLayout(text, 1)
        self._secure_status = QLabel()
        row.addWidget(self._secure_status)
        outer.addLayout(row)

        note = QLabel("After enabling a permission, relaunch Captura for it to take effect.")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        outer.addSpacing(10)
        outer.addWidget(note)

        from app import __version__

        version = QLabel(f"Captura {__version__}")
        version.setObjectName("subtitle")
        version.setAlignment(Qt.AlignmentFlag.AlignRight)
        outer.addSpacing(8)
        outer.addWidget(version)

        # Secure Input comes and goes with focus (a password field grabs it,
        # leaving it lets go), so poll while the window is open.
        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self._refresh_secure_input)

        self._refresh()

    def _grant(self, name: str) -> None:
        platform_setup.request_permission(name)

    def _refresh_secure_input(self) -> None:
        try:
            blocker = platform_setup.hotkey_blocker()
        except Exception:
            blocker = None
        label = self._secure_status
        if blocker:
            label.setText("Paused")
            label.setObjectName("missing")
            named = "" if blocker == "another app" else f" ({blocker})"
            self._secure_desc.setText(
                f"macOS Secure Keyboard Entry is on{named}, so the system sends keystrokes to no "
                "global shortcut at all — Captura's included. It's switched on by a focused "
                "password field or an app like Signal, 1Password or Terminal (Terminal has it "
                "under its Edit menu). Close that field or quit the app and the shortcut returns; "
                "nothing here needs changing."
            )
        else:
            label.setText("✓ Reaching Captura")
            label.setObjectName("granted")
            self._secure_desc.setText("Reach the hotkey only while no app holds Secure Keyboard Entry")
        label.style().unpolish(label)
        label.style().polish(label)

    def _refresh(self) -> None:
        self._refresh_secure_input()
        status = platform_setup.permission_status()
        for name, label, button in self._rows:
            granted = status.get(name, False)
            label.setText("✓ Granted" if granted else "Not granted")
            label.setObjectName("granted" if granted else "missing")
            label.style().unpolish(label)
            label.style().polish(label)
            button.setVisible(not granted)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # Esc closes the window
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # re-check each time it's shown
        self._refresh()
        self._poll.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._poll.stop()
        super().hideEvent(event)

    def focusInEvent(self, event) -> None:  # and when returning from Settings
        self._refresh()
        super().focusInEvent(event)
