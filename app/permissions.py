"""macOS permissions status window, opened from the tray.

Gives visible feedback for each permission instead of silently firing native
prompts (which don't appear when macOS already knows the app). Each row shows
the live granted-state and a button that opens the relevant Settings pane and
triggers the native prompt.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
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

        note = QLabel("After enabling a permission, relaunch Captura for it to take effect.")
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        outer.addSpacing(10)
        outer.addWidget(note)

        self._refresh()

    def _grant(self, name: str) -> None:
        platform_setup.request_permission(name)

    def _refresh(self) -> None:
        status = platform_setup.permission_status()
        for name, label, button in self._rows:
            granted = status.get(name, False)
            label.setText("✓ Granted" if granted else "Not granted")
            label.setObjectName("granted" if granted else "missing")
            label.style().unpolish(label)
            label.style().polish(label)
            button.setVisible(not granted)

    def showEvent(self, event) -> None:  # re-check each time it's shown
        self._refresh()
        super().showEvent(event)

    def focusInEvent(self, event) -> None:  # and when returning from Settings
        self._refresh()
        super().focusInEvent(event)
