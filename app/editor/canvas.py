"""QGraphicsScene wrapper: background capture, annotations, undo stack."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QImage, QPainter, QPixmap, QUndoCommand, QUndoStack
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsSceneWheelEvent,
    QGraphicsTextItem,
)

from app import theme
from app.editor.tools import Tool, TextTool

_DEBUG = bool(os.environ.get("CAPTURA_DEBUG"))
# Set by the selftest: synthetic QTest events don't move the physical cursor,
# so the cursor cross-check must be disabled for them.
SYNTHETIC_INPUT = bool(os.environ.get("CAPTURA_SYNTHETIC_INPUT"))
_LOG_FILE = Path(tempfile.gettempdir()) / "captura-debug.log"


def debug_log(message: str) -> None:
    """Event tracing for hard-to-reproduce input bugs (CAPTURA_DEBUG=1)."""
    if not _DEBUG:
        return
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {message}\n")
    except OSError:
        pass


class AddItemCommand(QUndoCommand):
    """Undoable addition of an annotation item that is already on the scene."""

    def __init__(self, scene: EditorScene, item: QGraphicsItem) -> None:
        super().__init__("annotate")
        self._scene = scene
        self._item = item
        self._first = True

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        self._scene.addItem(self._item)
        self._scene.annotations.append(self._item)

    def undo(self) -> None:
        self._scene.removeItem(self._item)
        self._scene.annotations.remove(self._item)


class DeleteItemsCommand(QUndoCommand):
    """Undoable removal of selected annotation items."""

    def __init__(self, scene: EditorScene, items: list[QGraphicsItem]) -> None:
        super().__init__("delete")
        self._scene = scene
        self._items = items

    def redo(self) -> None:
        for item in self._items:
            self._scene.removeItem(item)
            self._scene.annotations.remove(item)

    def undo(self) -> None:
        for item in self._items:
            self._scene.addItem(item)
            self._scene.annotations.append(item)


class MoveItemsCommand(QUndoCommand):
    """Undoable move of one or more selected items (already moved)."""

    def __init__(self, moves: list[tuple[QGraphicsItem, QPointF, QPointF]]) -> None:
        super().__init__("move")
        self._moves = moves
        self._first = True

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        for item, _old, new in self._moves:
            item.setPos(new)

    def undo(self) -> None:
        for item, old, _new in self._moves:
            item.setPos(old)


class EditorScene(QGraphicsScene):
    """Frozen full-screen capture as background. The scene covers the whole
    screen (screen-local logical coords, identity-mapped to the fullscreen
    editor window); ``region`` is the capture frame within it. Resizing or
    moving the frame only changes ``region`` — never any window geometry,
    which macOS refuses to apply reliably during live drags. Every
    annotation is a QGraphicsItem."""

    def __init__(self, full_image: QImage, scale: float, region: QRectF) -> None:
        super().__init__()
        self._image = full_image
        self._scale = scale
        self.setSceneRect(QRectF(0, 0, full_image.width() / scale, full_image.height() / scale))
        self.region = QRectF(region)

        pixmap = QPixmap.fromImage(full_image)
        pixmap.setDevicePixelRatio(scale)
        background = self.addPixmap(pixmap)
        background.setZValue(-1)

        self.undo_stack = QUndoStack(self)
        self.annotations: list[QGraphicsItem] = []
        self.color = QColor(theme.DEFAULT_COLOR)
        self.stroke_width = 4
        self.font_size = 16
        self._tool: Tool | None = None
        self._move_origins: dict[QGraphicsItem, QPointF] = {}
        self.focusItemChanged.connect(self._on_focus_changed)

    @property
    def original_image(self) -> QImage:
        """The captured region without annotations — what OCR runs on."""
        region = self.region
        physical = QRectF(
            region.x() * self._scale,
            region.y() * self._scale,
            region.width() * self._scale,
            region.height() * self._scale,
        ).toRect().intersected(self._image.rect())
        return self._image.copy(physical)

    # -- tool management ---------------------------------------------------

    @property
    def select_mode(self) -> bool:
        return self._tool is None

    def set_tool(self, tool: Tool | None) -> None:
        """None means the select/move tool (default scene behaviour)."""
        if self._tool is not None:
            self._tool.cancel(self)  # never leave an orphaned in-progress item
        self._tool = tool
        selectable = tool is None
        for item in self.annotations:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, selectable)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
        if not selectable:
            self.clearSelection()

    def commit_item(self, item: QGraphicsItem) -> None:
        """Push an undo entry for an item the active tool just finished."""
        if _DEBUG and isinstance(item, QGraphicsPathItem):
            path = item.path()
            head = [
                (int(path.elementAt(i).type), round(path.elementAt(i).x), round(path.elementAt(i).y))
                for i in range(min(4, path.elementCount()))
            ]
            debug_log(
                f"commit path: elements={path.elementCount()} "
                f"itemPos=({item.pos().x():.0f},{item.pos().y():.0f}) head={head}"
            )
        selectable = self._tool is None
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, selectable)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
        self.annotations.append(item)
        self.undo_stack.push(AddItemCommand(self, item))

    def cancel_drawing(self) -> bool:
        """Abort the in-progress drawing, if any. Returns True if one existed."""
        return self._tool is not None and self._tool.cancel(self)

    def delete_selected(self) -> bool:
        """Remove selected annotations (undoable). Returns True if any."""
        items = [i for i in self.selectedItems() if i in self.annotations]
        if not items:
            return False
        self.undo_stack.push(DeleteItemsCommand(self, items))
        return True

    def refocus_pending_text(self) -> None:
        """Give the caret back to an uncommitted text item after the window
        was transiently deactivated (e.g. macOS focus flapping)."""
        if self.focusItem() is not None:
            return
        for item in self.items():
            if isinstance(item, QGraphicsTextItem) and item not in self.annotations:
                item.setFocus(Qt.FocusReason.OtherFocusReason)
                return

    # -- output --------------------------------------------------------------

    def render_flattened(self) -> QImage:
        """Render the region (background + annotations) at physical resolution."""
        self.clearSelection()
        self.setFocusItem(None)
        region = self.region
        out = QImage(
            round(region.width() * self._scale),
            round(region.height() * self._scale),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.render(painter, QRectF(out.rect()), region)
        painter.end()
        return out

    # -- event routing ---------------------------------------------------------

    def _corrected_pos(self, event: QGraphicsSceneMouseEvent) -> QPointF:
        """Tool positions come from the physical cursor, not the event.

        macOS keeps delivering mouse events with corrupted coordinates to
        these frameless windows (strokes anchored at the capture corner).
        QCursor.pos() is ground truth, so events only signal *that*
        something happened — never *where*."""
        pos = event.scenePos()
        views = self.views()
        if SYNTHETIC_INPUT or not views:
            return pos
        view = views[0]
        cursor = view.mapToScene(view.mapFromGlobal(QCursor.pos()))
        if (pos - cursor).manhattanLength() > 2:
            debug_log(f"event pos {pos} != cursor {cursor} — using cursor")
        return cursor

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if _DEBUG:
            view = self.views()[0] if self.views() else None
            cursor = view.mapToScene(view.mapFromGlobal(QCursor.pos())) if view else None
            active = view.isActiveWindow() if view else "?"
            debug_log(
                f"press raw={event.scenePos()} screen={event.screenPos()} "
                f"cursor_scene={cursor} active={active} tool={type(self._tool).__name__}"
            )
        if event.button() == Qt.MouseButton.LeftButton and self._tool is not None:
            pos = self._corrected_pos(event)
            if not self.region.contains(pos):
                # Outside the capture frame (dim area, or a phantom press
                # leaked from a toolbar click) — never start drawing.
                event.accept()
                return
            # Clicking inside a text item while the text tool is active edits it
            # instead of stacking a new one on top.
            item = self.itemAt(pos, self.views()[0].transform()) if self.views() else None
            if isinstance(self._tool, TextTool) and isinstance(item, QGraphicsTextItem):
                super().mousePressEvent(event)
                return
            self._tool.press(self, pos)
            event.accept()
            return
        super().mousePressEvent(event)
        if self._tool is None:
            # Record positions after the click resolves selection, so the
            # release handler can build one undoable move per drag.
            self._move_origins = {i: i.pos() for i in self.selectedItems()}

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._tool is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pos = self._corrected_pos(event)
            debug_log(f"move raw={event.scenePos()} corrected={pos}")
            if not self._tool.active and not self.region.contains(pos):
                # Never lazy-start a stroke from outside the frame.
                event.accept()
                return
            self._tool.move(self, pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._tool is not None:
            debug_log(f"release raw={event.scenePos()} corrected={self._corrected_pos(event)}")
            self._tool.release(self, self._corrected_pos(event))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._tool is None and self._move_origins:
            moves = [
                (item, old, item.pos())
                for item, old in self._move_origins.items()
                if item.pos() != old
            ]
            if moves:
                self.undo_stack.push(MoveItemsCommand(moves))
            self._move_origins = {}

    def wheelEvent(self, event: QGraphicsSceneWheelEvent) -> None:
        # Scrolling while a text item is being edited adjusts its font size.
        focus = self.focusItem()
        if isinstance(focus, QGraphicsTextItem):
            font = focus.font()
            delta = 1 if event.delta() > 0 else -1
            size = max(6, min(96, font.pointSize() + delta))
            font.setPointSize(size)
            focus.setFont(font)
            self.font_size = size
            event.accept()
            return
        super().wheelEvent(event)

    def _on_focus_changed(self, new: QGraphicsItem | None, old: QGraphicsItem | None, reason) -> None:
        # Text items are committed (or discarded if empty) when they lose focus.
        # Window (de)activation — e.g. clicking the no-focus toolbar — is
        # transient and must not destroy a text item the user just placed.
        if reason == Qt.FocusReason.ActiveWindowFocusReason:
            return
        if isinstance(old, QGraphicsTextItem) and old not in self.annotations:
            if old.toPlainText().strip():
                self.commit_item(old)
            else:
                self.removeItem(old)
