"""mss screen capture and the capture flow controller."""
from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass

import mss
from PyQt6.QtCore import QObject, QRect, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication, QImage, QScreen

from app import platform as platform_setup
from app.editor.editor import EditorWindow
from app.overlay import ScreenOverlay
from app.settings import Settings


@dataclass(frozen=True)
class FrozenScreen:
    """A frozen snapshot of one display, in physical pixels."""

    screen: QScreen
    image: QImage


def grab_all_screens() -> list[FrozenScreen]:
    frozen: list[FrozenScreen] = []
    with mss.mss() as sct:
        # Zero-size entries show up transiently (e.g. display waking up).
        monitors = [m for m in sct.monitors[1:] if m["width"] > 0 and m["height"] > 0]
        if not monitors:
            raise RuntimeError("no usable displays reported by mss")
        for screen in QGuiApplication.screens():
            shot = sct.grab(_grab_region(monitors, screen))
            # mss raw is tightly packed BGRA, which matches Format_RGB32
            # little-endian memory layout; copy() detaches from mss's buffer.
            image = QImage(
                shot.raw, shot.width, shot.height, shot.width * 4,
                QImage.Format.Format_RGB32,
            ).copy()
            frozen.append(FrozenScreen(screen=screen, image=image))
    return frozen


def _grab_region(monitors: list[dict], screen: QScreen) -> dict:
    """The mss grab region for a Qt screen, corrected for display rotation.

    mss reports a rotated display in its *native* (unrotated) orientation, so
    a portrait screen comes back with width/height transposed — and grabbing
    that region runs past the display into a neighbour (capturing the wrong
    area). Qt reports the screen in its presented orientation, so when the two
    disagree on portrait-vs-landscape we swap mss's dimensions to match Qt.
    Comparing orientation (not absolute size) keeps this DPI-independent.
    """
    geo = screen.geometry()
    monitor = min(
        monitors,
        key=lambda m: abs(m["left"] - geo.x()) + abs(m["top"] - geo.y()),
    )
    qt_portrait = geo.height() > geo.width()
    mss_portrait = monitor["height"] > monitor["width"]
    if qt_portrait != mss_portrait:
        return {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["height"],
            "height": monitor["width"],
        }
    return monitor


class CaptureController(QObject):
    """Runs the hotkey → overlay → editor capture flow."""

    captured = pyqtSignal(QImage)  # final flattened output (clipboard copy)
    cancelled = pyqtSignal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._overlays: list[ScreenOverlay] = []
        self._editors: list[EditorWindow] = []  # keeps WA_DeleteOnClose windows alive

    def start_capture(self) -> None:
        if self._overlays or self._editors:
            return  # one capture session at a time
        platform_setup.ensure_screen_capture_access()
        try:
            screens = grab_all_screens()
        except Exception:
            traceback.print_exc()
            print(
                "captura: screen grab failed — on macOS grant Screen Recording permission "
                "in System Settings → Privacy & Security",
                file=sys.stderr,
            )
            self.cancelled.emit()
            return
        for frozen in screens:
            overlay = ScreenOverlay(frozen)
            overlay.selection_made.connect(self._on_selection)
            overlay.cancelled.connect(self._on_cancel)
            self._overlays.append(overlay)
        for overlay in self._overlays:
            overlay.show()
        platform_setup.activate_app()
        cursor = QCursor.pos()
        for overlay in self._overlays:
            if overlay.geometry().contains(cursor):
                overlay.activateWindow()
                overlay.raise_()
                break

    def _on_selection(self, rect: QRect) -> None:
        try:
            overlay = self.sender()
            if not isinstance(overlay, ScreenOverlay):
                return
            # rect is overlay-local == screen-local; the editor gets the whole
            # frozen screen so the frame can be resized to reveal more of it.
            editor = EditorWindow(overlay.full_image, rect, overlay.screen_ref, self._settings)
            self._editors.append(editor)
            # Close the dim overlays the moment the editor closes (synchronous),
            # not when it's later destroyed — that lags a cycle on Windows.
            editor.closing.connect(self._close_overlays)
            editor.destroyed.connect(lambda *_, e=editor: self._end_session(e))
            # The screen stays dimmed behind the editor until the session ends.
            for held in self._overlays:
                held.hold_dim()
                held.clicked_while_held.connect(editor.bring_to_front)
            editor.show()
        except Exception:
            traceback.print_exc()
            self._close_overlays()
            self.cancelled.emit()

    def _on_cancel(self) -> None:
        try:
            self._close_overlays()
            for editor in list(self._editors):
                editor.close()
            self.cancelled.emit()
        except Exception:
            traceback.print_exc()

    def _end_session(self, editor: EditorWindow) -> None:
        if editor in self._editors:
            self._editors.remove(editor)
        self._close_overlays()

    def _close_overlays(self) -> None:
        overlays, self._overlays = self._overlays, []
        for overlay in overlays:
            overlay.close()
            overlay.deleteLater()
