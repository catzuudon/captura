"""Editor window: the capture stays at its on-screen position, annotatable."""
from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPen,
    QScreen,
    QShortcut,
)
from PyQt6.QtWidgets import QApplication, QFileDialog, QGraphicsView

from app import ocr, platform as platform_setup, theme
from app.editor.canvas import SYNTHETIC_INPUT, EditorScene, debug_log
from app.editor.ocr_panel import OcrPanel
from app.editor.toolbar import Toolbar
from app.editor.tools import (
    ArrowTool,
    EllipseTool,
    HighlighterTool,
    LineTool,
    PenTool,
    RectTool,
    TextTool,
    Tool,
)
from app.settings import Settings

_TOOL_FACTORIES: dict[str, type[Tool]] = {
    "pen": PenTool,
    "line": LineTool,
    "arrow": ArrowTool,
    "rect": RectTool,
    "ellipse": EllipseTool,
    "text": TextTool,
    "highlighter": HighlighterTool,
}


_RESIZE_MARGIN = 6  # px band along the frame edges that drags resize
_CORNER_MARGIN = 16  # px square at each corner that drags both edges
_MIN_REGION = 30
_DRAG_THRESHOLD = 5  # px the cursor must move before a click becomes a drag


class EditorWindow(QGraphicsView):
    """Static fullscreen view over the frozen screen; the capture frame is
    drawn inside it (dim outside, border + handles around the region).

    The window geometry never changes after show: macOS does not reliably
    apply window resizes during a live mouse drag, so frame resize/move are
    pure repaints of ``scene.region``.
    """

    # Fires synchronously from closeEvent so the dim overlays are torn down at
    # once. Relying on ``destroyed`` instead lags a cycle on Windows, where the
    # WA_DeleteOnClose deferred-delete isn't processed until the next event.
    closing = pyqtSignal()

    def __init__(
        self,
        full_image: QImage,
        region: QRect,
        screen: QScreen,
        settings: Settings,
    ) -> None:
        scale = full_image.width() / max(1, screen.geometry().width())
        self._scene = EditorScene(full_image, scale, QRectF(region))
        super().__init__(self._scene)
        self._settings = settings
        self._screen = screen
        self._resize_edges = Qt.Edge(0)
        self._move_anchor: "QPoint | None" = None
        self._move_origin = QRectF(region).topLeft()
        self._new_select_origin: "QPointF | None" = None  # redraw-selection drag
        # A frame interaction is only committed once the cursor moves past a
        # threshold, so a stray click on the border or dim area never resizes
        # or re-selects — the frame stays put unless you deliberately drag.
        self._pending: "str | None" = None  # "resize" | "move" | "new"
        self._pending_edges = Qt.Edge(0)
        self._press_origin: "QPoint | None" = None
        self._armed = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Full repaints: the dim mask + frame chrome change on every drag step.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setGeometry(screen.geometry())  # static; never resized again

        self._toolbar = Toolbar(self)
        self._toolbar.tool_selected.connect(self._set_tool)
        self._toolbar.color_changed.connect(self._set_color)
        self._toolbar.width_changed.connect(self._set_width)
        self._toolbar.undo_requested.connect(self._scene.undo_stack.undo)
        self._toolbar.redo_requested.connect(self._scene.undo_stack.redo)
        self._toolbar.ocr_requested.connect(self.extract_text)
        self._toolbar.copy_requested.connect(self.copy_and_close)
        self._toolbar.save_requested.connect(self.save_and_close)
        self._toolbar.close_requested.connect(self.close)

        QShortcut(QKeySequence.StandardKey.Undo, self, self._scene.undo_stack.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self._scene.undo_stack.redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._scene.undo_stack.redo)

        self._ocr_panel = OcrPanel(self)
        self._ocr_task: ocr.OcrTask | None = None

    def show(self) -> None:  # noqa: D102 — also places the toolbar
        super().show()
        platform_setup.activate_app()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        # macOS sometimes ignores activateWindow() while the capture
        # overlays are still being torn down; retry once the loop settles.
        QTimer.singleShot(0, self.activateWindow)
        self._toolbar.dock_to(self.region_rect(), self._screen)
        self._toolbar.show()

    def event(self, ev: QEvent) -> bool:
        if ev.type() == QEvent.Type.WindowActivate:
            # If macOS focus flapping interrupted inline text editing,
            # give the caret back instead of leaving the box dead.
            self._scene.refocus_pending_text()
        return super().event(ev)

    def bring_to_front(self) -> None:
        """Re-stack above the dim backdrop (clicking it raises the overlay)."""
        self.raise_()
        self._toolbar.raise_()
        if self._ocr_panel.isVisible():
            self._ocr_panel.raise_()
        self.activateWindow()

    # -- frame resize ----------------------------------------------------------

    def _edges_at(self, pos) -> Qt.Edge:
        # Window == screen, so viewport coords are region coords directly.
        # In select mode, corners get a generous square zone (a 6px overlap
        # is unhittable); capped so tiny frames keep a usable interior.
        # With a drawing tool active only the slim edge bands grab, so
        # strokes can reach into the corners.
        region = self._scene.region
        x, y = pos.x(), pos.y()
        if self._scene.select_mode:
            corner = min(_CORNER_MARGIN, region.width() / 3, region.height() / 3)
            near_l = abs(x - region.left()) <= corner
            near_r = abs(x - region.right()) <= corner
            near_t = abs(y - region.top()) <= corner
            near_b = abs(y - region.bottom()) <= corner
            if (near_l or near_r) and (near_t or near_b):
                edges = Qt.Edge(0)
                edges |= Qt.Edge.LeftEdge if near_l else Qt.Edge.RightEdge
                edges |= Qt.Edge.TopEdge if near_t else Qt.Edge.BottomEdge
                return edges
        margin = _RESIZE_MARGIN
        within_x = region.left() - margin <= x <= region.right() + margin
        within_y = region.top() - margin <= y <= region.bottom() + margin
        edges = Qt.Edge(0)
        if abs(x - region.left()) <= margin and within_y:
            edges |= Qt.Edge.LeftEdge
        if abs(x - region.right()) <= margin and within_y:
            edges |= Qt.Edge.RightEdge
        if abs(y - region.top()) <= margin and within_x:
            edges |= Qt.Edge.TopEdge
        if abs(y - region.bottom()) <= margin and within_x:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _edge_cursor(self, edges: Qt.Edge) -> Qt.CursorShape | None:
        horizontal = edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
        vertical = edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge)
        if horizontal and vertical:
            diag_nwse = edges in (
                Qt.Edge.LeftEdge | Qt.Edge.TopEdge,
                Qt.Edge.RightEdge | Qt.Edge.BottomEdge,
            )
            return Qt.CursorShape.SizeFDiagCursor if diag_nwse else Qt.CursorShape.SizeBDiagCursor
        if horizontal:
            return Qt.CursorShape.SizeHorCursor
        if vertical:
            return Qt.CursorShape.SizeVerCursor
        return None

    def region_rect(self) -> QRect:
        """The capture frame in editor-local (== screen-local) coordinates."""
        return self._scene.region.toRect()

    def _set_region(self, region: QRectF) -> None:
        # Pure repaint — window geometry is never touched during drags.
        self._scene.region = QRectF(region)
        self.viewport().update()
        debug_log(f"region={region}")

    def _apply_resize(self, global_pos) -> None:
        local = global_pos - self._screen.geometry().topLeft()  # screen-local logical
        bounds = self._screen.geometry()
        region = QRectF(self._scene.region)
        if self._resize_edges & Qt.Edge.LeftEdge:
            region.setLeft(max(0, min(local.x(), region.right() - _MIN_REGION)))
        if self._resize_edges & Qt.Edge.RightEdge:
            region.setRight(min(bounds.width(), max(local.x(), region.left() + _MIN_REGION)))
        if self._resize_edges & Qt.Edge.TopEdge:
            region.setTop(max(0, min(local.y(), region.bottom() - _MIN_REGION)))
        if self._resize_edges & Qt.Edge.BottomEdge:
            region.setBottom(min(bounds.height(), max(local.y(), region.top() + _MIN_REGION)))
        self._set_region(region)

    def _apply_move(self, global_pos) -> None:
        delta = global_pos - self._move_anchor
        bounds = self._screen.geometry()
        region = QRectF(self._scene.region)
        x = max(0.0, min(self._move_origin.x() + delta.x(), bounds.width() - region.width()))
        y = max(0.0, min(self._move_origin.y() + delta.y(), bounds.height() - region.height()))
        region.moveTo(x, y)
        self._set_region(region)

    def _global_mouse_pos(self, event) -> "QPoint":
        # Same policy as the drawing tools: the physical cursor is ground
        # truth; event coordinates arrive corrupted on macOS at times.
        if SYNTHETIC_INPUT:
            return event.globalPosition().toPoint()
        return QCursor.pos()

    def _movable_interior(self, viewport_pos) -> bool:
        """Interior drags relocate the frame in select mode — but only from
        empty space (the background), never from an annotation."""
        if not self._scene.select_mode:
            return False
        if not self._scene.region.contains(QPointF(viewport_pos)):
            return False
        item = self.itemAt(viewport_pos)
        return item is None or item not in self._scene.annotations

    def _screen_local(self, global_pos) -> "QPointF":
        return QPointF(global_pos - self._screen.geometry().topLeft())

    def _reset_drag(self) -> None:
        self._pending = None
        self._pending_edges = Qt.Edge(0)
        self._press_origin = None
        self._armed = False
        self._resize_edges = Qt.Edge(0)
        self._move_anchor = None
        self._new_select_origin = None

    def mousePressEvent(self, event) -> None:
        if self._pending is not None:  # stale press whose release was lost
            self._reset_drag()
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapFromGlobal(self._global_mouse_pos(event))
            self._press_origin = self._global_mouse_pos(event)
            edges = self._edges_at(pos)
            if edges:
                self._pending, self._pending_edges = "resize", edges
                event.accept()
                return
            if self._movable_interior(pos):
                self._pending = "move"
                self._move_origin = self._scene.region.topLeft()
                event.accept()
                return
            # Select mode + press in the dim area (outside the frame): a real
            # drag draws a fresh selection (re-frame from anywhere). A mere
            # click does nothing — handled by the move-threshold below.
            if self._scene.select_mode and not self._scene.region.contains(QPointF(pos)):
                self._pending = "new"
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pending is not None:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._reset_drag()  # release happened off-window
                return
            gpos = self._global_mouse_pos(event)
            if not self._armed:
                if (gpos - self._press_origin).manhattanLength() < _DRAG_THRESHOLD:
                    event.accept()
                    return  # still within click tolerance — frame unchanged
                self._arm_drag()
            if self._pending == "resize":
                self._apply_resize(gpos)
            elif self._pending == "move":
                self._apply_move(gpos)
            else:
                self._apply_new_select(gpos)
            event.accept()
            return
        if not event.buttons():
            pos = self.mapFromGlobal(self._global_mouse_pos(event))
            cursor = self._edge_cursor(self._edges_at(pos))
            if cursor is not None:
                self.viewport().setCursor(cursor)
            elif self._movable_interior(pos):
                self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
            elif self._scene.select_mode and not self._scene.region.contains(QPointF(pos)):
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)  # redraw zone
            else:
                self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def _arm_drag(self) -> None:
        """Commit to the pending interaction once the cursor passes the
        threshold; only now is the toolbar hidden and the region touched."""
        self._armed = True
        if self._pending == "resize":
            self._resize_edges = self._pending_edges
        elif self._pending == "move":
            self._move_anchor = self._press_origin
        else:
            self._new_select_origin = self._screen_local(self._press_origin)
        self._begin_frame_drag()

    def _apply_new_select(self, global_pos) -> None:
        bounds = self._screen.geometry()
        cur = self._screen_local(global_pos)
        cx = max(0.0, min(cur.x(), bounds.width()))
        cy = max(0.0, min(cur.y(), bounds.height()))
        region = QRectF(self._new_select_origin, QPointF(cx, cy)).normalized()
        if region.width() >= _MIN_REGION and region.height() >= _MIN_REGION:
            self._set_region(region)

    def mouseReleaseEvent(self, event) -> None:
        if self._pending is not None:
            armed = self._armed
            self._reset_drag()
            if armed:
                self._end_frame_drag()  # re-dock the toolbar after a real drag
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _begin_frame_drag(self) -> None:
        # No explicit grabMouse here: the editor is fullscreen, so the cursor
        # cannot leave it mid-drag and the implicit grab suffices. An explicit
        # grab steals clicks meant for the floating toolbar.
        # Hide the toolbar (and OCR panel) while the frame moves/resizes so
        # they don't linger at the old position; re-anchored on release.
        self._toolbar.hide()
        if self._ocr_panel.isVisible():
            self._ocr_panel.hide()
            self._ocr_was_visible = True

    def _end_frame_drag(self) -> None:
        self._resize_edges = Qt.Edge(0)
        self._move_anchor = None
        self._new_select_origin = None
        self._toolbar.dock_to(self.region_rect(), self._screen)
        self._toolbar.show()
        if getattr(self, "_ocr_was_visible", False):
            self._dock_ocr_panel()
            self._ocr_panel.show()
            self._ocr_was_visible = False
        self.activateWindow()

    # -- toolbar slots -------------------------------------------------------

    def _set_tool(self, name: str) -> None:
        factory = _TOOL_FACTORIES.get(name)
        self._scene.set_tool(factory() if factory else None)

    def _set_color(self, color: QColor) -> None:
        self._scene.color = color

    def _set_width(self, width: int) -> None:
        self._scene.stroke_width = width

    # -- OCR -----------------------------------------------------------------

    def extract_text(self) -> None:
        """Run Tesseract on the original capture (annotations excluded)."""
        if self._ocr_task is not None:
            return  # one extraction at a time
        task = ocr.extract_text_async(self._scene.original_image, self._settings.ocr_language)
        task.finished.connect(self._on_ocr_done)
        task.failed.connect(self._on_ocr_failed)
        self._ocr_task = task

    def _on_ocr_done(self, text: str) -> None:
        self._ocr_task = None
        self._dock_ocr_panel()
        self._ocr_panel.show_text(text)

    def _on_ocr_failed(self, message: str) -> None:
        self._ocr_task = None
        self._dock_ocr_panel()
        self._ocr_panel.show_message(message)

    def _dock_ocr_panel(self) -> None:
        # Both anchors are editor-local: the toolbar is a child widget now.
        anchor = self._toolbar.geometry() if self._toolbar.isVisible() else self.region_rect()
        self._ocr_panel.dock_to(anchor, self._screen)

    # -- output --------------------------------------------------------------

    def copy_and_close(self) -> None:
        try:
            QApplication.clipboard().setImage(self._scene.render_flattened())
        except Exception:
            traceback.print_exc()
        self.close()

    def save_and_close(self) -> None:
        try:
            ext = self._settings.image_format.lower()
            default_name = datetime.now().strftime(f"captura-%Y%m%d-%H%M%S.{ext}")
            filters = "PNG (*.png);;JPEG (*.jpg *.jpeg)"
            if ext in ("jpg", "jpeg"):
                filters = "JPEG (*.jpg *.jpeg);;PNG (*.png)"
            path, _ = QFileDialog.getSaveFileName(
                self, "Save capture", str(Path(self._settings.save_dir) / default_name), filters
            )
            if not path:
                return  # cancelled: stay open
            self._scene.render_flattened().save(path)
            self._settings.save_dir = str(Path(path).parent)
            self._settings.save()
        except Exception:
            traceback.print_exc()
            return
        self.close()

    # -- window events ---------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        editing_text = self._scene.focusItem() is not None
        if not editing_text and (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            or event.matches(QKeySequence.StandardKey.Copy)
        ):
            self.copy_and_close()
        elif event.key() == Qt.Key.Key_Escape:
            if editing_text:
                self._scene.setFocusItem(None)  # first Esc ends text editing
            elif self._scene.cancel_drawing():
                pass  # Esc aborts the shape being dragged; editor stays open
            else:
                self.close()
        elif (
            event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
            and not editing_text
            and self._scene.delete_selected()
        ):
            pass  # selected annotations removed (undoable)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        try:
            self.closing.emit()  # tear down the dim overlays immediately
            self._toolbar.close()
            self._ocr_panel.close()
        except Exception:
            traceback.print_exc()
        super().closeEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        # View-level chrome (never flattened into output): dim everything
        # outside the capture frame, then border + Lightshot-style handles.
        region = self._scene.region
        full = self.sceneRect()
        dim = QColor(8, 8, 10, 140)  # near-black spotlight, matches the site
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dim)
        painter.drawRect(QRectF(full.left(), full.top(), full.width(), region.top() - full.top()))
        painter.drawRect(
            QRectF(full.left(), region.bottom(), full.width(), full.bottom() - region.bottom())
        )
        painter.drawRect(
            QRectF(full.left(), region.top(), region.left() - full.left(), region.height())
        )
        painter.drawRect(
            QRectF(region.right(), region.top(), full.right() - region.right(), region.height())
        )

        accent = QColor(theme.ACCENT)
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(region.adjusted(0, 0, -1, -1))

        # Blue corner/edge handles (the site's signature look).
        half = 3.5
        left, top = region.left() + half, region.top() + half
        right, bottom = region.right() - half - 1, region.bottom() - half - 1
        cx, cy = region.center().x(), region.center().y()
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.setBrush(accent)
        for x, y in (
            (left, top), (cx, top), (right, top),
            (left, cy), (right, cy),
            (left, bottom), (cx, bottom), (right, bottom),
        ):
            painter.drawRect(QRectF(x - half, y - half, 2 * half, 2 * half))
