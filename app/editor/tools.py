"""Annotation tool classes. Each tool turns mouse drags into QGraphicsItems."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

if TYPE_CHECKING:
    from app.editor.canvas import EditorScene

_MIN_DRAG = 2.0  # logical px below which a drag is discarded as a slip
# A real first move lands within a few px of the press. A jump beyond this
# means the anchor came from a corrupted event — re-anchor at the cursor.
_MAX_FIRST_JUMP = 150.0


def _pen(scene: EditorScene) -> QPen:
    pen = QPen(scene.color, scene.stroke_width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


class Tool:
    """Base: press starts an item, move updates it, release commits it.

    Tools start lazily: if the press was lost (macOS may consume the click
    that re-activates the editor window), the first drag move starts the
    item at the cursor instead of anchoring it at a stale origin.
    """

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def active(self) -> bool:
        """True while an item is being drawn (between press and release)."""
        return getattr(self, "_item", None) is not None

    def press(self, scene: EditorScene, pos: QPointF) -> None: ...

    def move(self, scene: EditorScene, pos: QPointF) -> None: ...

    def release(self, scene: EditorScene, pos: QPointF) -> None:
        self._cancelled = False

    def cancel(self, scene: EditorScene) -> bool:
        """Discard the in-progress item. Returns True if there was one."""
        return False


class PenTool(Tool):
    def __init__(self) -> None:
        super().__init__()
        self._item: QGraphicsPathItem | None = None
        # The path is tool state, never read back from the item:
        # QGraphicsPathItem silently drops a path holding only a MoveTo,
        # and lineTo on the resulting empty path anchors strokes at (0,0).
        self._path = QPainterPath()

    def press(self, scene: EditorScene, pos: QPointF) -> None:
        self._path = QPainterPath(pos)
        self._item = scene.addPath(self._path, _pen(scene))

    def move(self, scene: EditorScene, pos: QPointF) -> None:
        if self._cancelled:
            return
        if self._item is None:
            self.press(scene, pos)
            return
        if self._path.elementCount() == 1:
            start = self._path.elementAt(0)
            if abs(pos.x() - start.x) + abs(pos.y() - start.y) > _MAX_FIRST_JUMP:
                self._path = QPainterPath(pos)  # corrupted anchor — restart
                self._item.setPath(self._path)
                return
        self._path.lineTo(pos)
        self._item.setPath(self._path)

    def release(self, scene: EditorScene, pos: QPointF) -> None:
        super().release(scene, pos)
        if self._item is None:
            return
        if self._path.length() < _MIN_DRAG:
            scene.removeItem(self._item)
        else:
            scene.commit_item(self._item)
        self._item = None

    def cancel(self, scene: EditorScene) -> bool:
        if self._item is None:
            return False
        scene.removeItem(self._item)
        self._item = None
        self._cancelled = True  # swallow moves until the button is released
        return True


class HighlighterTool(PenTool):
    """Freehand marker: wide, semi-transparent stroke."""

    def press(self, scene: EditorScene, pos: QPointF) -> None:
        super().press(scene, pos)
        assert self._item is not None
        color = QColor(scene.color)
        color.setAlpha(110)
        pen = QPen(color, scene.stroke_width * 3.5)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._item.setPen(pen)


class _DragTool(Tool):
    """Shared origin tracking for two-point shapes."""

    def __init__(self) -> None:
        super().__init__()
        self._origin = QPointF()
        self._item: QGraphicsItem | None = None
        self._began = False

    def press(self, scene: EditorScene, pos: QPointF) -> None:  # noqa: D102
        self._began = False

    def move(self, scene: EditorScene, pos: QPointF) -> None:
        if self._cancelled:
            return
        if self._item is None:
            self.press(scene, pos)
            return
        if not self._began and (pos - self._origin).manhattanLength() > _MAX_FIRST_JUMP:
            self._origin = pos  # corrupted anchor — re-anchor at the cursor
        self._began = True
        self._update(pos)

    def _update(self, pos: QPointF) -> None: ...

    def release(self, scene: EditorScene, pos: QPointF) -> None:
        super().release(scene, pos)
        if self._item is None:
            return
        if (pos - self._origin).manhattanLength() < _MIN_DRAG:
            scene.removeItem(self._item)
        else:
            scene.commit_item(self._item)
        self._item = None

    def cancel(self, scene: EditorScene) -> bool:
        if self._item is None:
            return False
        scene.removeItem(self._item)
        self._item = None
        self._cancelled = True
        return True


class LineTool(_DragTool):
    def press(self, scene: EditorScene, pos: QPointF) -> None:
        super().press(scene, pos)
        self._origin = pos
        self._item = scene.addLine(pos.x(), pos.y(), pos.x(), pos.y(), _pen(scene))

    def _update(self, pos: QPointF) -> None:
        if isinstance(self._item, QGraphicsLineItem):
            self._item.setLine(self._origin.x(), self._origin.y(), pos.x(), pos.y())


class ArrowTool(_DragTool):
    def press(self, scene: EditorScene, pos: QPointF) -> None:
        super().press(scene, pos)
        self._origin = pos
        item = QGraphicsPathItem()
        item.setPen(_pen(scene))
        item.setBrush(scene.color)
        scene.addItem(item)
        self._item = item

    def _update(self, pos: QPointF) -> None:
        if isinstance(self._item, QGraphicsPathItem):
            self._item.setPath(self._arrow_path(self._origin, pos, self._item.pen().widthF()))

    @staticmethod
    def _arrow_path(start: QPointF, end: QPointF, width: float) -> QPainterPath:
        path = QPainterPath(start)
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head = max(10.0, width * 3.5)
        # Shaft stops short of the tip so the head stays sharp.
        shaft_end = QPointF(
            end.x() - head * 0.6 * math.cos(angle),
            end.y() - head * 0.6 * math.sin(angle),
        )
        path.lineTo(shaft_end)
        left = QPointF(
            end.x() - head * math.cos(angle - math.pi / 7),
            end.y() - head * math.sin(angle - math.pi / 7),
        )
        right = QPointF(
            end.x() - head * math.cos(angle + math.pi / 7),
            end.y() - head * math.sin(angle + math.pi / 7),
        )
        path.addPolygon(QPolygonF([end, left, right]))
        path.closeSubpath()
        return path


class RectTool(_DragTool):
    def press(self, scene: EditorScene, pos: QPointF) -> None:
        super().press(scene, pos)
        self._origin = pos
        self._item = scene.addRect(QRectF(pos, pos), _pen(scene))

    def _update(self, pos: QPointF) -> None:
        if isinstance(self._item, QGraphicsRectItem):
            self._item.setRect(QRectF(self._origin, pos).normalized())


class EllipseTool(_DragTool):
    def press(self, scene: EditorScene, pos: QPointF) -> None:
        super().press(scene, pos)
        self._origin = pos
        self._item = scene.addEllipse(QRectF(pos, pos), _pen(scene))

    def _update(self, pos: QPointF) -> None:
        if isinstance(self._item, QGraphicsEllipseItem):
            self._item.setRect(QRectF(self._origin, pos).normalized())


class TextTool(Tool):
    """Click to place; type inline on the canvas; scroll adjusts font size.

    The item is committed (or discarded if empty) by the scene when it
    loses focus — see EditorScene._on_focus_changed.
    """

    def press(self, scene: EditorScene, pos: QPointF) -> None:
        item = QGraphicsTextItem()
        font = QFont()
        font.setPointSize(scene.font_size)
        item.setFont(font)
        item.setDefaultTextColor(scene.color)
        item.setPos(pos)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        scene.addItem(item)
        item.setFocus()
