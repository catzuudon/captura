"""Full-screen dim overlay with rubber-band region selection.

One overlay window is created per display, each showing the frozen
screenshot of that display dimmed. The selected region is un-dimmed live
with its physical pixel dimensions next to the cursor. Selections are
cropped from the overlay's own frozen image, so logical→physical mapping
only ever happens within a single screen — no cross-monitor coordinate
math, which keeps mixed-DPI layouts correct.
"""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget

from app import theme

if TYPE_CHECKING:
    from app.capture import FrozenScreen

_DIM = QColor(8, 8, 10, 140)
_BORDER = QColor(theme.ACCENT)            # blue selection border (brand)
_LABEL_BG = QColor(theme.ACCENT)         # dimensions shown in a blue pill
_LABEL_FG = QColor(255, 255, 255)
_MIN_SELECTION = 3  # logical px; smaller drags are treated as slips


class ScreenOverlay(QWidget):
    selection_made = pyqtSignal(QRect)  # widget-local, logical pixels
    cancelled = pyqtSignal()
    clicked_while_held = pyqtSignal()  # dim-hold click: refocus the editor

    def __init__(self, frozen: FrozenScreen) -> None:
        super().__init__()
        self._image = frozen.image
        self.screen_ref = frozen.screen
        self._origin: QPoint | None = None
        self._current = QPoint()
        self._held = False  # dim-hold: passive backdrop while the editor is open

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if sys.platform.startswith("linux"):
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(frozen.screen.geometry())

        self._pixmap = QPixmap.fromImage(self._image)
        self._pixmap.setDevicePixelRatio(self._image.width() / max(1, self.width()))

    @property
    def full_image(self) -> QImage:
        """The whole frozen screen, physical pixels."""
        return self._image

    def hold_dim(self) -> None:
        """Switch to a passive fully-dimmed backdrop behind the editor."""
        self._held = True
        self._origin = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def crop_physical(self, rect: QRect) -> QImage | None:
        """Crop a widget-local logical rect out of the frozen physical image."""
        sx = self._image.width() / max(1, self.width())
        sy = self._image.height() / max(1, self.height())
        physical = QRect(
            round(rect.x() * sx),
            round(rect.y() * sy),
            round(rect.width() * sx),
            round(rect.height() * sy),
        ).intersected(self._image.rect())
        if physical.isEmpty():
            return None
        return self._image.copy(physical)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.fillRect(self.rect(), _DIM)
        if self._held:
            return

        rect = self._selection_rect()
        if rect is None:
            return
        sx = self._image.width() / max(1, self.width())
        sy = self._image.height() / max(1, self.height())
        source = QRect(
            round(rect.x() * sx),
            round(rect.y() * sy),
            round(rect.width() * sx),
            round(rect.height() * sy),
        )
        painter.drawImage(rect, self._image, source)
        painter.setPen(QPen(_BORDER, 1.5))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        self._draw_dimensions(painter, source)

    def _draw_dimensions(self, painter: QPainter, source: QRect) -> None:
        font = QFont(self.font())
        font.setPointSize(10)
        painter.setFont(font)
        text = f"{source.width()} × {source.height()}"
        metrics = painter.fontMetrics()
        box = metrics.boundingRect(text).adjusted(-5, -3, 5, 3)
        box.moveTopLeft(self._current + QPoint(14, 14))
        if box.right() > self.width():
            box.moveRight(self._current.x() - 14)
        if box.bottom() > self.height():
            box.moveBottom(self._current.y() - 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_LABEL_BG)
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(_LABEL_FG)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._held:
            self.clicked_while_held.emit()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._held:
            return
        self._current = event.position().toPoint()
        if self._origin is not None:
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._held or event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = self._selection_rect()
        self._origin = None
        if rect is not None and rect.width() >= _MIN_SELECTION and rect.height() >= _MIN_SELECTION:
            self.selection_made.emit(rect)
        else:
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    def _selection_rect(self) -> QRect | None:
        if self._origin is None:
            return None
        # QRectF avoids QRect's inclusive-endpoint semantics, so a 200px
        # drag selects exactly 200px, not 201.
        return QRectF(QPointF(self._origin), QPointF(self._current)).normalized().toRect()
