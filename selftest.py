"""Dev self-test: drives capture + editor flows with synthetic input.

Run: .venv/bin/python selftest.py
Phase 1: grab, overlay, drag-select, Escape cancel.
Phase 2: editor opens at capture position, annotations, undo/redo,
text tool, Enter flattens to clipboard, Escape closes.
Phase 3: OCR on a generated image; inline result panel in the editor.
"""
from __future__ import annotations

import os
import sys

# Synthetic QTest events don't move the physical cursor; disable the
# cursor cross-check in the scene before app modules are imported.
os.environ["CAPTURA_SYNTHETIC_INPUT"] = "1"

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from app import platform as platform_setup
from app.capture import CaptureController
from app.settings import Settings
from app.tray import TrayIcon

failures: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not ok:
        failures.append(name)


def _mouse(
    widget: QWidget,
    kind: QEvent.Type,
    pos: QPoint,
    buttons: Qt.MouseButton,
    global_pos: QPoint | None = None,
) -> None:
    event = QMouseEvent(
        kind,
        QPointF(pos),
        QPointF(global_pos if global_pos is not None else widget.mapToGlobal(pos)),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)


def drag(widget: QWidget, start: QPoint, end: QPoint) -> None:
    """Press-drag-release with the left button held during the move."""
    _mouse(widget, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    mid = QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2)
    for pos in (mid, end):
        _mouse(widget, QEvent.Type.MouseMove, pos, Qt.MouseButton.LeftButton)
    _mouse(widget, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton)
    QTest.qWait(30)


def select_region(controller: CaptureController) -> None:
    controller.start_capture()
    QTest.qWait(150)
    overlay = controller._overlays[0]
    drag(overlay, QPoint(100, 100), QPoint(300, 250))
    QTest.qWait(100)


def run_tests(app: QApplication, controller: CaptureController) -> None:
    # --- Phase 1: escape cancels the overlay ---
    controller.start_capture()
    check("overlays created (one per screen)", len(controller._overlays) == len(app.screens()))
    QTest.qWait(100)
    QTest.keyClick(controller._overlays[0], Qt.Key.Key_Escape)
    QTest.qWait(50)
    check("escape closes overlays", not controller._overlays)

    # --- Phase 2: selection opens the editor ---
    select_region(controller)
    check("editor opened after selection", len(controller._editors) == 1)
    check("screen stays dimmed while editing", bool(controller._overlays))
    if not controller._editors:
        app.quit()
        return
    editor = controller._editors[0]
    scene = editor._scene
    region = scene.region
    check(
        "frame placed at capture position",
        (region.x(), region.y(), region.width(), region.height()) == (100, 100, 200, 150),
    )
    check("toolbar visible", editor._toolbar.isVisible())

    # The editor window is fullscreen; viewport coords ARE screen coords,
    # so editor interactions below address region-local points + (100, 100).
    def rp(x: int, y: int) -> QPoint:
        return QPoint(100 + x, 100 + y)

    # pen: draw a stroke through the viewport event path
    editor._set_tool("pen")
    drag(editor.viewport(), rp(10, 10), rp(80, 60))
    check("pen stroke added", len(scene.annotations) == 1)
    if scene.annotations:
        path = scene.annotations[0].path()
        ox, oy = scene.region.x(), scene.region.y()
        first = path.elementAt(0)
        check(
            "pen path anchored at press point",
            path.elementCount() >= 2
            and abs(first.x - ox - 10) < 2 and abs(first.y - oy - 10) < 2,
        )

    # undo / redo
    scene.undo_stack.undo()
    check("undo removes stroke", len(scene.annotations) == 0)
    scene.undo_stack.redo()
    check("redo restores stroke", len(scene.annotations) == 1)

    # rect
    editor._set_tool("rect")
    drag(editor.viewport(), rp(20, 80), rp(120, 130))
    check("rectangle added", len(scene.annotations) == 2)

    # line: must start exactly where the press landed, not at a corner
    ox, oy = scene.region.x(), scene.region.y()
    editor._set_tool("line")
    drag(editor.viewport(), rp(50, 40), rp(150, 90))
    check("line added", len(scene.annotations) == 3)
    if len(scene.annotations) == 3:
        line = scene.annotations[-1].line()
        check(
            "line anchored at click point",
            abs(line.x1() - ox - 50) < 1 and abs(line.y1() - oy - 40) < 1
            and abs(line.x2() - ox - 150) < 1 and abs(line.y2() - oy - 90) < 1,
        )
        scene.undo_stack.undo()  # keep 2 annotations for the counts below

    # delete: select an annotation, Del removes it, undo restores it
    editor._set_tool("select")
    target = scene.annotations[-1]
    target.setSelected(True)
    QTest.keyClick(editor, Qt.Key.Key_Delete)
    check("delete removes selected annotation", len(scene.annotations) == 1)
    scene.undo_stack.undo()
    check("undo restores deleted annotation", len(scene.annotations) == 2)

    # Esc mid-drag cancels the in-progress shape, editor stays open
    editor._set_tool("ellipse")
    _mouse(editor.viewport(), QEvent.Type.MouseButtonPress, rp(30, 30), Qt.MouseButton.LeftButton)
    _mouse(editor.viewport(), QEvent.Type.MouseMove, rp(90, 70), Qt.MouseButton.LeftButton)
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    _mouse(editor.viewport(), QEvent.Type.MouseMove, rp(110, 80), Qt.MouseButton.LeftButton)
    _mouse(editor.viewport(), QEvent.Type.MouseButtonRelease, rp(110, 80), Qt.MouseButton.NoButton)
    QTest.qWait(30)
    check("esc cancels in-progress shape", len(scene.annotations) == 2)
    check("editor stays open after drawing cancel", editor.isVisible())

    # text: click, type, then defocus commits
    editor._set_tool("text")
    _mouse(editor.viewport(), QEvent.Type.MouseButtonPress, rp(40, 30), Qt.MouseButton.LeftButton)
    _mouse(editor.viewport(), QEvent.Type.MouseButtonRelease, rp(40, 30), Qt.MouseButton.NoButton)
    QTest.qWait(50)
    focus = scene.focusItem()
    check("text item focused for inline typing", focus is not None)
    if focus is not None:
        QTest.keyClicks(editor.viewport(), "hi")
        scene.setFocusItem(None)
        QTest.qWait(30)
    check("text committed on defocus", len(scene.annotations) == 3)

    # Enter flattens to clipboard and closes everything
    QApplication.clipboard().setImage(QImage())
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(150)
    clip = QApplication.clipboard().image()
    check("enter copies flattened image", not clip.isNull())
    if not clip.isNull():
        print(f"  flattened image: {clip.width()}x{clip.height()}")
    check("editor closed after copy", not controller._editors)
    check("dim overlays closed with editor", not controller._overlays)

    # --- Phase 3: OCR ---
    from app import ocr

    if ocr.find_tesseract() is None:
        print("SKIP: tesseract not installed — OCR accuracy checks skipped")
    else:
        from PyQt6.QtGui import QFont, QPainter

        sample = QImage(600, 160, QImage.Format.Format_RGB32)
        sample.fill(Qt.GlobalColor.white)
        painter = QPainter(sample)
        painter.setPen(Qt.GlobalColor.black)
        painter.setFont(QFont("Helvetica", 42))
        painter.drawText(sample.rect(), Qt.AlignmentFlag.AlignCenter, "CAPTURA 123")
        painter.end()
        text = ocr.extract_text(sample, "eng")
        check("ocr reads generated text", "CAPTURA" in text and "123" in text)

    # OCR through the editor UI (panel must appear either way)
    select_region(controller)
    if controller._editors:
        editor = controller._editors[0]
        editor.extract_text()
        for _ in range(100):  # up to ~10s for tesseract
            QTest.qWait(100)
            if editor._ocr_task is None:
                break
        panel = editor._ocr_panel
        check("ocr task completed", editor._ocr_task is None)
        check("ocr panel shown inline", panel.isVisible())
        # Copy text → green confirmation appears
        QApplication.clipboard().setText("")
        panel._copy()
        check("ocr copy puts text on clipboard", bool(QApplication.clipboard().text()))
        check("ocr copy shows confirmation", panel._copied.isVisible())
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        QTest.qWait(150)
        try:
            panel_gone = not panel.isVisible()
        except RuntimeError:
            panel_gone = True  # child window deleted together with the editor
        check("editor + ocr panel closed", not controller._editors and panel_gone)

    # Frame resize (drag right edge), then Ctrl+C copies the resized region.
    # Region starts at (100, 100, 200, 150); viewport coords == screen coords.
    select_region(controller)
    check("second editor opened", len(controller._editors) == 1)
    if controller._editors:
        editor = controller._editors[0]
        vp = editor.viewport()
        drag(vp, QPoint(298, 175), QPoint(328, 175))  # right-edge drag outward
        reg = editor._scene.region
        check("frame resized by edge drag", reg.width() == 228)

        # a click on the border (press + release, no real drag) must NOT
        # resize — the frame stays locked against accidental clicks.
        before = editor._scene.region.getRect()
        _mouse(vp, QEvent.Type.MouseButtonPress, QPoint(228, 175), Qt.MouseButton.LeftButton)
        _mouse(vp, QEvent.Type.MouseButtonRelease, QPoint(228, 175), Qt.MouseButton.NoButton)
        QTest.qWait(20)
        check("border click does not resize", editor._scene.region.getRect() == before)
        check("toolbar stays after a click", editor._toolbar.isVisible())

        # corner drag (bottom-right, inside the 16px corner zone but outside
        # the 6px edge bands) must resize BOTH dimensions, and the toolbar
        # must hide once the drag actually engages.
        _mouse(vp, QEvent.Type.MouseButtonPress, QPoint(318, 244), Qt.MouseButton.LeftButton)
        _mouse(vp, QEvent.Type.MouseMove, QPoint(350, 272), Qt.MouseButton.LeftButton)
        check("toolbar hidden during frame drag", not editor._toolbar.isVisible())
        _mouse(vp, QEvent.Type.MouseButtonRelease, QPoint(350, 272), Qt.MouseButton.NoButton)
        QTest.qWait(30)
        reg = editor._scene.region
        check("corner drag resizes both dimensions", (reg.width(), reg.height()) == (250, 172))
        check("toolbar re-anchored after frame drag", editor._toolbar.isVisible())
        check("editor window geometry untouched", editor.geometry() == editor.screen().geometry())

        # interior drag in select mode relocates the frame (size unchanged)
        drag(vp, QPoint(200, 175), QPoint(220, 190))
        reg = editor._scene.region
        check(
            "frame moved by interior drag",
            (reg.x(), reg.y(), reg.width(), reg.height()) == (120, 115, 250, 172),
        )

        # dragging from the dim area (outside the frame) draws a NEW selection,
        # so you can re-frame to the screen border without resizing
        drag(vp, QPoint(500, 500), QPoint(580, 560))
        reg = editor._scene.region
        check(
            "dim-area drag draws a fresh selection",
            (reg.x(), reg.y(), reg.width(), reg.height()) == (500, 500, 80, 60),
        )
        QApplication.clipboard().setImage(QImage())
        QTest.keyClick(editor, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(150)
        clip = QApplication.clipboard().image()
        check("ctrl+c copies to clipboard", not clip.isNull())
        if not clip.isNull():
            check("copied image matches re-selected frame", abs(clip.width() - 80) <= 1)
    check("ctrl+c closes editor", not controller._editors)

    # Escape closes a fresh editor without copying
    select_region(controller)
    check("third editor opened", len(controller._editors) == 1)
    if controller._editors:
        QTest.keyClick(controller._editors[0], Qt.Key.Key_Escape)
        QTest.qWait(150)
    check("escape closes editor", not controller._editors)

    # --- Phase 4: hotkey mapping + settings panel ---
    from PyQt6.QtGui import QKeyEvent

    from app.hotkey import HotkeyListener, hotkey_from_qt
    from app.settings import SettingsPanel

    ctrl_shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    mapped = hotkey_from_qt(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_7, ctrl_shift))
    expected = "<cmd>+<shift>+7" if sys.platform == "darwin" else "<ctrl>+<shift>+7"
    check("hotkey mapping modifier combo", mapped == expected)
    check(
        "hotkey mapping rejects bare letter",
        hotkey_from_qt(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)) is None,
    )
    check(
        "hotkey mapping allows standalone F-key",
        hotkey_from_qt(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F2, Qt.KeyboardModifier.NoModifier)) == "<f2>",
    )

    # macOS hotkey suppression: the keystroke that completes the hotkey is
    # swallowed (returns None) so it never reaches the focused app.
    hk = HotkeyListener("<cmd>+<shift>+7")
    hk._fired = False
    hk._on_activate()
    suppressed = hk._darwin_intercept(0, "EVT") is None
    passes = hk._darwin_intercept(0, "EVT") == "EVT"
    check("hotkey completing key suppressed, others pass through", suppressed and passes)

    settings = controller._settings
    orig_hotkey, orig_format = settings.hotkey, settings.image_format
    panel = SettingsPanel(settings, HotkeyListener(settings.hotkey))
    panel.show()
    QTest.qWait(100)
    panel._format_box.setCurrentText("JPG")
    check("format change persisted", Settings.load().image_format == "jpg")
    panel._start_recording()
    QTest.keyClick(panel, Qt.Key.Key_9, ctrl_shift)
    expected9 = "<cmd>+<shift>+9" if sys.platform == "darwin" else "<ctrl>+<shift>+9"
    check(
        "hotkey rebind recorded and persisted",
        settings.hotkey == expected9 and Settings.load().hotkey == expected9,
    )
    settings.hotkey, settings.image_format = orig_hotkey, orig_format
    settings.save()  # restore the user's configuration
    panel.close()

    app.quit()


def main() -> int:
    platform_setup.setup()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    settings = Settings.load()
    check("settings load", bool(settings.hotkey))
    check("system tray available", QSystemTrayIcon.isSystemTrayAvailable())
    tray = TrayIcon()
    tray.show()
    check("tray icon visible", tray.isVisible())

    controller = CaptureController(settings)

    def _safe() -> None:
        try:
            run_tests(app, controller)
        except Exception:
            import traceback
            traceback.print_exc()
            failures.append("unexpected exception — see traceback above")
            app.quit()

    QTimer.singleShot(200, _safe)
    app.exec()
    print(f"\n{'ALL PASS' if not failures else f'{len(failures)} FAILURE(S): {failures}'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
