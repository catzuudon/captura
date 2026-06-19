"""Minimal inline panel showing OCR results, docked to the editor."""
from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QIcon, QKeyEvent, QScreen
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.paths import ASSETS_DIR as _ASSETS

_STYLE = f"""
QWidget#ocrpanel {{
    background: {theme.SURFACE}; border: 1px solid {theme.BORDER}; border-radius: 13px;
}}
QPlainTextEdit {{
    background: #0e0e12; color: #e6e6ec; border: 1px solid {theme.BORDER};
    border-radius: 9px; padding: 6px;
    selection-background-color: {theme.ACCENT}; selection-color: #ffffff;
    font-family: ui-monospace, 'SF Mono', Menlo, monospace;
}}
QLabel {{ color: {theme.TEXT_MUTED}; }}
QLabel#copied {{ color: {theme.SUCCESS}; }}
QToolButton {{ border: 1px solid transparent; border-radius: 9px; padding: 5px; background: transparent; }}
QToolButton:hover {{ background: rgba(255, 255, 255, 0.06); }}
"""


class OcrPanel(QWidget):
    """Text result with a single Copy Text button; errors show inline."""

    def __init__(self, parent: QWidget) -> None:
        # Child widget inside the fullscreen editor (same reasoning as the
        # toolbar: separate windows get buried under the fullscreen editor).
        super().__init__(parent)
        self.setObjectName("ocrpanel")
        self.setStyleSheet(_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        self._text = QPlainTextEdit()
        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.hide()

        copy_btn = QToolButton()
        copy_btn.setIcon(QIcon(str(_ASSETS / "tool-copy.svg")))
        copy_btn.setIconSize(QSize(16, 16))
        copy_btn.setToolTip("Copy text")
        copy_btn.clicked.connect(self._copy)
        close_btn = QToolButton()
        close_btn.setIcon(QIcon(str(_ASSETS / "tool-close.svg")))
        close_btn.setIconSize(QSize(16, 16))
        close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.close)

        self._copied = QLabel("✓ Copied to clipboard")
        self._copied.setObjectName("copied")
        self._copied.hide()
        self._copied_timer = QTimer(self)
        self._copied_timer.setSingleShot(True)
        self._copied_timer.timeout.connect(self._copied.hide)

        buttons = QHBoxLayout()
        buttons.addWidget(self._copied)
        buttons.addStretch(1)
        buttons.addWidget(copy_btn)
        buttons.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._message)
        layout.addWidget(self._text)
        layout.addLayout(buttons)

    def show_text(self, text: str) -> None:
        self._copied.hide()
        self._message.hide()
        self._text.show()
        self._text.setPlainText(text if text else "No text found in the selection.")
        if text:
            self._text.selectAll()
        self.show()
        self.raise_()
        self._text.setFocus()

    def show_message(self, message: str) -> None:
        """Inline guidance (e.g. Tesseract missing) — never a popup."""
        self._text.hide()
        self._message.setText(message)
        self._message.show()
        self.show()
        self.raise_()

    def dock_to(self, anchor: QRect, screen: QScreen) -> None:
        """Place the panel below the anchor (editor-local coordinates)."""
        width = max(280, min(420, anchor.width()))
        height = 170
        avail = screen.availableGeometry().translated(-screen.geometry().topLeft())
        x = min(max(anchor.left(), avail.left() + 4), avail.right() - width - 4)
        below = anchor.bottom() + 8
        if below + height <= avail.bottom():
            y = below
        else:
            y = max(avail.top() + 4, anchor.top() - 8 - height)
        self.setGeometry(x, y, width, height)

    def _copy(self) -> None:
        cursor = self._text.textCursor()
        # QTextCursor.selectedText() uses U+2029 as the paragraph separator.
        text = (
            cursor.selectedText().replace("\u2029", "\n")
            if cursor.hasSelection()
            else self._text.toPlainText()
        )
        QApplication.clipboard().setText(text)
        self._copied.show()
        self._copied_timer.start(1800)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
