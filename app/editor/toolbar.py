"""Compact floating toolbar: icon-only tools, inline color swatches.

Styled to match the Captura site — dark glass surface, blue accent, rounded
controls, and a quick-color row.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QScreen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from app import theme
from app.paths import ASSETS_DIR as _ASSETS

_STROKE_PRESETS = [2, 4, 8]  # thin / medium / thick
_SWATCH_COLORS = theme.QUICK_COLORS

_STYLE = f"""
QWidget#toolbar {{
    background: {theme.SURFACE_RAISED};
    border: 1px solid {theme.BORDER};
    border-radius: 13px;
}}
QToolButton {{
    border: 1px solid transparent; border-radius: 9px;
    padding: 6px; background: transparent;
}}
QToolButton:hover {{ background: rgba(255, 255, 255, 0.06); }}
QToolButton:checked {{
    background: rgba({theme.ACCENT_RGB[0]}, {theme.ACCENT_RGB[1]}, {theme.ACCENT_RGB[2]}, 0.22);
    border: 1px solid {theme.ACCENT};
}}
QToolButton#swatch {{ border-radius: 13px; padding: 0; }}
QToolButton#swatch:hover {{ background: transparent; }}
QFrame[frameShape="5"] {{ color: rgba(255, 255, 255, 0.10); margin: 4px 2px; }}
QToolTip {{
    background: {theme.SURFACE}; color: {theme.TEXT};
    border: 1px solid {theme.BORDER}; padding: 4px 7px; border-radius: 6px;
}}
"""

_TOOLS = ["select", "pen", "line", "arrow", "rect", "ellipse", "text", "highlighter"]


def _swatch_icon(color: QColor, selected: bool, size: int = 22) -> QIcon:
    """A round color chip; ringed when it's the active color."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = 7
    cx = cy = size / 2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(int(cx - r), int(cy - r), 2 * r, 2 * r)
    if selected:
        # Ring in a tone that stays visible on any swatch colour.
        light = color.lightnessF() > 0.7
        ring = QColor("#3a3a3e") if light else QColor("#ffffff")
        pen = p.pen()
        pen.setColor(ring)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - r - 3), int(cy - r - 3), 2 * (r + 3), 2 * (r + 3))
    p.end()
    return QIcon(pm)


def _custom_icon(color: QColor, size: int = 22) -> QIcon:
    """Custom-color chip: the current colour with a small '+' hint ring."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = cy = size / 2
    p.setPen(QColor(theme.TEXT_MUTED))
    p.setBrush(color)
    p.drawEllipse(int(cx - 7), int(cy - 7), 14, 14)
    p.setPen(QColor("#ffffff"))
    p.drawLine(int(cx - 3), int(cy), int(cx + 3), int(cy))
    p.drawLine(int(cx), int(cy - 3), int(cx), int(cy + 3))
    p.end()
    return QIcon(pm)


def _stroke_icon(width: int, size: int = 18) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(theme.TEXT))
    p.setPen(Qt.PenStyle.NoPen)
    r = 2 + width
    p.drawEllipse(QPoint(size // 2, size // 2), r // 2 + 1, r // 2 + 1)
    p.end()
    return QIcon(pm)


class Toolbar(QWidget):
    """Single horizontal row: tools · colors · stroke · undo/redo · actions."""

    tool_selected = pyqtSignal(str)  # one of _TOOLS
    color_changed = pyqtSignal(QColor)
    width_changed = pyqtSignal(int)
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    ocr_requested = pyqtSignal()
    copy_requested = pyqtSignal()
    save_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        # Plain child widget INSIDE the fullscreen editor — not a separate
        # window. Separate windows kept getting buried whenever macOS raised
        # the fullscreen editor (Qt's window parenting is only transient on
        # macOS, no real z-order pinning). A child widget paints above the
        # viewport unconditionally and shares the editor's keyboard focus.
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setStyleSheet(_STYLE)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._color = QColor(theme.DEFAULT_COLOR)
        self._stroke_index = 1
        self._swatches: list[tuple[QToolButton, QColor]] = []

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(3)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for name in _TOOLS:
            btn = self._button(f"tool-{name}.svg", name.capitalize(), checkable=True)
            btn.toggled.connect(lambda on, n=name: on and self.tool_selected.emit(n))
            self._group.addButton(btn)
            row.addWidget(btn)
            if name == "select":
                btn.setChecked(True)

        row.addWidget(self._separator())
        for hexcolor in _SWATCH_COLORS:
            color = QColor(hexcolor)
            sw = QToolButton(self)
            sw.setObjectName("swatch")
            sw.setIconSize(QSize(22, 22))
            sw.setFixedSize(QSize(26, 26))
            sw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            sw.setToolTip(hexcolor)
            sw.clicked.connect(lambda _, c=color: self._set_color(c))
            self._swatches.append((sw, color))
            row.addWidget(sw)
        self._custom_btn = QToolButton(self)
        self._custom_btn.setObjectName("swatch")
        self._custom_btn.setIconSize(QSize(22, 22))
        self._custom_btn.setFixedSize(QSize(26, 26))
        self._custom_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._custom_btn.setToolTip("Custom color")
        self._custom_btn.setIcon(_custom_icon(self._color))
        self._custom_btn.clicked.connect(self._pick_custom)
        row.addWidget(self._custom_btn)

        self._width_btn = self._button(None, "Stroke width")
        self._width_btn.setIcon(_stroke_icon(_STROKE_PRESETS[self._stroke_index]))
        self._width_btn.clicked.connect(self._cycle_width)
        row.addWidget(self._width_btn)

        row.addWidget(self._separator())
        for icon, tip, signal in (
            ("tool-undo.svg", "Undo (Ctrl+Z)", self.undo_requested),
            ("tool-redo.svg", "Redo (Ctrl+Y)", self.redo_requested),
        ):
            btn = self._button(icon, tip)
            btn.clicked.connect(signal.emit)
            row.addWidget(btn)

        row.addWidget(self._separator())
        for icon, tip, signal in (
            ("tool-ocr.svg", "Extract text", self.ocr_requested),
            ("tool-copy.svg", "Copy (Enter)", self.copy_requested),
            ("tool-save.svg", "Save", self.save_requested),
            ("tool-close.svg", "Close (Esc)", self.close_requested),
        ):
            btn = self._button(icon, tip)
            btn.clicked.connect(signal.emit)
            row.addWidget(btn)

        self._refresh_swatches()

    def _button(self, icon: str | None, tooltip: str, checkable: bool = False) -> QToolButton:
        btn = QToolButton(self)
        if icon:
            btn.setIcon(QIcon(str(_ASSETS / icon)))
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def _separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.VLine)
        return line

    def _refresh_swatches(self) -> None:
        for sw, color in self._swatches:
            sw.setIcon(_swatch_icon(color, color.rgb() == self._color.rgb()))
        self._custom_btn.setIcon(_custom_icon(self._color))

    def _pick_custom(self) -> None:
        color = QColorDialog.getColor(parent=self.parentWidget())
        if color.isValid():
            self._set_color(color)

    def _set_color(self, color: QColor) -> None:
        self._color = color
        self._refresh_swatches()
        self.color_changed.emit(color)

    def _cycle_width(self) -> None:
        self._stroke_index = (self._stroke_index + 1) % len(_STROKE_PRESETS)
        width = _STROKE_PRESETS[self._stroke_index]
        self._width_btn.setIcon(_stroke_icon(width))
        self.width_changed.emit(width)

    def dock_to(self, selection: QRect, screen: QScreen) -> None:
        """Place the toolbar near the selection, always fully visible.

        ``selection`` is in editor-local (== screen-local) coordinates. Prefer
        just below the selection, then just above; otherwise (a full-screen
        capture leaves no room) tuck it inside near the bottom. The final
        position is clamped to the screen's *available* area, so it can never
        land off-screen or behind the menu bar / Dock."""
        self.adjustSize()
        size = self.sizeHint()
        avail = screen.availableGeometry().translated(-screen.geometry().topLeft())
        gap = 10
        below = selection.bottom() + gap
        above = selection.top() - gap - size.height()
        if below + size.height() <= avail.bottom():
            y = below
        elif above >= avail.top():
            y = above
        else:
            y = avail.bottom() - size.height() - gap  # inside, above the Dock
        x = selection.right() - size.width()
        x = max(avail.left() + 4, min(x, avail.right() - size.width() - 4))
        y = max(avail.top() + 4, min(y, avail.bottom() - size.height() - 4))
        self.move(x, y)
        self.resize(size)
        self.raise_()
