"""Global hotkey listener (pynput) bridged to a Qt signal, plus the
Qt-key-event → pynput-hotkey-string mapping used by the settings panel."""
from __future__ import annotations

import contextlib
import os
import sys
import time

from pynput import keyboard
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QKeyEvent


def _neutralize_macos_tis() -> None:
    """Stop pynput from crashing the app on macOS 26+.

    pynput's keyboard listener enters ``keycode_context()`` on its background
    listener thread, which calls Text Input Source APIs
    (TISCopyCurrentKeyboardInputSource …). macOS 26 traps any off-main-thread
    call into that subsystem with a dispatch-queue assertion → SIGTRAP, so the
    app dies the moment the listener (re)starts in a fully initialized GUI
    process — e.g. right after rebinding the hotkey.

    The listener only assigns that context to an attribute it never reads
    (the consumer, the keyboard *Controller*, is unused by Captura). Replacing
    the contextmanager with a no-op removes the fatal call with no loss of
    function. pynput is pinned, so this targeted patch is safe.
    """
    if sys.platform != "darwin":
        return
    try:
        from pynput.keyboard import _darwin as _kb

        @contextlib.contextmanager
        def _noop_context():
            yield None

        _kb.keycode_context = _noop_context
    except Exception:
        pass


_neutralize_macos_tis()

_QT_SPECIAL_KEYS = {
    Qt.Key.Key_Print: "<print_screen>",
    Qt.Key.Key_Space: "<space>",
    Qt.Key.Key_Home: "<home>",
    Qt.Key.Key_End: "<end>",
    Qt.Key.Key_PageUp: "<page_up>",
    Qt.Key.Key_PageDown: "<page_down>",
    Qt.Key.Key_Insert: "<insert>",
    Qt.Key.Key_Up: "<up>",
    Qt.Key.Key_Down: "<down>",
    Qt.Key.Key_Left: "<left>",
    Qt.Key.Key_Right: "<right>",
}

_PRETTY_NAMES = {
    "cmd": "Cmd",
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "print_screen": "PrintScreen",
    "space": "Space",
    "page_up": "PageUp",
    "page_down": "PageDown",
}


def hotkey_from_qt(event: QKeyEvent) -> str | None:
    """Map a Qt key press to pynput GlobalHotKeys syntax, or None if the
    combination is unusable (modifier-only, or would hijack plain typing)."""
    key = event.key()
    if key in (
        Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
        Qt.Key.Key_Meta, Qt.Key.Key_unknown, Qt.Key.Key_Escape,
    ):
        return None
    parts: list[str] = []
    mods = event.modifiers()
    darwin = sys.platform == "darwin"
    # Qt swaps Control/Meta on macOS: ControlModifier is the Command key.
    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append("<cmd>" if darwin else "<ctrl>")
    if mods & Qt.KeyboardModifier.MetaModifier:
        parts.append("<ctrl>" if darwin else "<cmd>")
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append("<alt>")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        parts.append("<shift>")

    if key in _QT_SPECIAL_KEYS:
        parts.append(_QT_SPECIAL_KEYS[key])
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F20:
        parts.append(f"<f{key - Qt.Key.Key_F1 + 1}>")
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        parts.append(chr(key).lower())
    else:
        return None

    # A bare letter/digit/arrow would fire while typing anywhere; require a
    # modifier unless the key is inherently a hotkey (PrintScreen, F-keys).
    last = parts[-1]
    standalone_ok = last == "<print_screen>" or last.startswith("<f")
    if len(parts) == 1 and not standalone_ok:
        return None
    hotkey = "+".join(parts)
    try:
        keyboard.HotKey.parse(hotkey)
    except ValueError:
        return None
    return hotkey


def pretty_hotkey(hotkey: str) -> str:
    """Human form of a pynput hotkey string: <cmd>+<shift>+7 → Cmd+Shift+7."""
    parts = []
    for token in hotkey.split("+"):
        name = token.strip("<>")
        parts.append(_PRETTY_NAMES.get(name, name.upper() if len(name) <= 3 else name.title()))
    return "+".join(parts)


class HotkeyListener(QObject):
    """Listens for the capture hotkey on a background thread.

    The pynput callback fires off the Qt main thread; ``triggered`` is
    therefore delivered as a queued cross-thread signal, so connected
    slots always run on the main thread.
    """

    triggered = pyqtSignal()

    def __init__(self, hotkey: str) -> None:
        super().__init__()
        self._hotkey = hotkey
        self._listener: keyboard.GlobalHotKeys | None = None
        self._fired = False

    def _on_activate(self) -> None:
        # Runs on the listener thread, before the macOS intercept for the same
        # key event — set the flag so the intercept swallows that keystroke.
        self._fired = True
        self.triggered.emit()

    def _darwin_intercept(self, event_type, event):
        # Active event tap (because darwin_intercept is set): return the event
        # to pass it through, None to suppress. We drop only the keystroke that
        # just completed the hotkey, so it never reaches the focused app (e.g.
        # Finder turning Cmd+Ctrl+A into "Make Alias").
        if self._fired:
            self._fired = False
            return None
        return event

    def _make_listener(self) -> "keyboard.GlobalHotKeys":
        kwargs = {}
        # Suppressing the hotkey uses an *active* event tap, which needs
        # Accessibility. Only request it when that permission is present;
        # otherwise fall back to a passive listener (Input Monitoring only)
        # so the hotkey still works — it just also reaches the focused app.
        from app import platform as platform_setup

        if sys.platform == "darwin" and platform_setup.has_accessibility():
            kwargs["darwin_intercept"] = self._darwin_intercept
        return keyboard.GlobalHotKeys({self._hotkey: self._on_activate}, **kwargs)

    def start(self) -> None:
        self.stop()
        self._fired = False
        # macOS prints "This process is not trusted!" via C-level stderr from
        # CGEventTapCreate (in a background thread). Redirect fd 2 for a brief
        # window that covers both the Python call and thread startup.
        if sys.platform == "darwin":
            _devnull = os.open(os.devnull, os.O_WRONLY)
            _saved = os.dup(2)
            os.dup2(_devnull, 2)
            try:
                self._listener = self._make_listener()
                self._listener.start()
                time.sleep(0.15)  # give the background thread time to create the event tap
            except Exception:
                self._listener = None
            finally:
                os.dup2(_saved, 2)
                os.close(_saved)
                os.close(_devnull)
            if self._listener is None:
                print("captura: hotkey listener unavailable (check Input Monitoring permission)", file=sys.stderr)
        else:
            try:
                self._listener = self._make_listener()
                self._listener.start()
            except Exception as exc:
                self._listener = None
                print(f"captura: hotkey listener unavailable: {exc}", file=sys.stderr)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def set_hotkey(self, hotkey: str) -> None:
        self._hotkey = hotkey
        if self._listener is not None:
            self.start()
