"""Global hotkey listener (pynput) bridged to a Qt signal, plus the
Qt-key-event → pynput-hotkey-string mapping used by the settings panel."""
from __future__ import annotations

import contextlib
import os
import sys
import time
import traceback

from pynput import keyboard
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
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

# -- macOS event-tap health --------------------------------------------------
# macOS switches an event tap off behind the app's back: when a tap callback
# overruns its time limit, and — the common one — across sleep/wake, display
# sleep and fast user switching. pynput neither notices nor re-enables it, so
# the hotkey silently goes deaf until Captura is relaunched. It also can't
# create a tap at all when the app launches at login before the permission
# system is ready, and reports that as a listener that started fine. These two
# Quartz calls let the watchdog below see the real state and repair it.
_CGEventTapEnable = None
_CGEventTapIsEnabled = None
if sys.platform == "darwin":
    try:
        from Quartz import (  # noqa: F811  (pyobjc ships with pynput on macOS)
            CGEventTapEnable as _CGEventTapEnable,
            CGEventTapIsEnabled as _CGEventTapIsEnabled,
        )
    except Exception:
        pass

# Event types macOS delivers to the tap callback when it disables the tap
# (kCGEventTapDisabledByTimeout / kCGEventTapDisabledByUserInput).
_TAP_DISABLED_EVENTS = (0xFFFFFFFE, 0xFFFFFFFF)

_WATCHDOG_INTERVAL_MS = 5000
# Wall clock keeps running while the Mac sleeps; the monotonic clock does not.
# A gap this large between the two across one tick means we just woke up.
_SLEEP_GAP_SECONDS = 8.0
# Backoff between restart attempts when the listener can't be created at all
# (e.g. permissions not resolvable yet, moments after login).
_RETRY_MIN_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0

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

    A watchdog on the main thread keeps the listener honest. macOS hands out
    event taps that stop working without saying so — disabled across sleep/wake
    or after a tap timeout, and simply not created when the app launches at
    login before the permission system is ready. In every one of those cases
    pynput still reports a happily running listener, which is exactly the
    "hotkey does nothing after waking the Mac" symptom. ``ensure_alive`` re-arms
    the tap, or rebuilds the listener when the tap is gone for good.
    """

    triggered = pyqtSignal()
    # Name of the process silencing the hotkey via macOS Secure Keyboard Entry,
    # or "" once it lets go. Emitted only on change, from the watchdog.
    blocked_changed = pyqtSignal(str)

    def __init__(self, hotkey: str) -> None:
        super().__init__()
        self._hotkey = hotkey
        self._listener: keyboard.GlobalHotKeys | None = None
        self._fired = False
        self._tap = None  # Quartz event tap handle (macOS only)
        self._blocker = ""
        self._retry_delay = _RETRY_MIN_SECONDS
        self._last_attempt = 0.0
        self._last_tick = (time.monotonic(), time.time())
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(_WATCHDOG_INTERVAL_MS)
        self._watchdog.timeout.connect(self.ensure_alive)

        # macOS: use a Carbon RegisterEventHotKey instead of pynput's event tap.
        # A tap is silenced whenever any app holds Secure Keyboard Entry (Signal
        # etc.), which made the hotkey randomly die; RegisterEventHotKey is immune
        # to it, needs neither Input Monitoring nor Accessibility, and consumes
        # the combo so it never leaks to the focused app. pynput stays the
        # backend on Windows/Linux (with the watchdog and blocker machinery).
        self._carbon = None
        if sys.platform == "darwin":
            from app.platform.macos_hotkey import CarbonHotKey

            self._carbon = CarbonHotKey(hotkey, self.triggered.emit)

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
        if event_type in _TAP_DISABLED_EVENTS:
            # Not a keystroke: macOS telling us it just switched the tap off.
            # Turning it back on here is the only way to recover without
            # rebuilding the listener, and it keeps the hotkey alive across
            # sleep/wake. Pass the event on untouched.
            self._reenable_tap()
            return event
        if self._fired:
            self._fired = False
            return None
        return event

    # -- listener lifecycle ---------------------------------------------------

    def _make_listener(self) -> "keyboard.GlobalHotKeys":
        kwargs = {}
        # Suppressing the hotkey uses an *active* event tap, which needs
        # Accessibility. Only request it when that permission is present;
        # otherwise fall back to a passive listener (Input Monitoring only)
        # so the hotkey still works — it just also reaches the focused app.
        from app import platform as platform_setup

        if sys.platform == "darwin" and platform_setup.has_accessibility():
            kwargs["darwin_intercept"] = self._darwin_intercept
        listener = keyboard.GlobalHotKeys({self._hotkey: self._on_activate}, **kwargs)
        if sys.platform == "darwin":
            self._capture_tap(listener)
        return listener

    def _capture_tap(self, listener: "keyboard.GlobalHotKeys") -> None:
        """Keep a handle on the Quartz tap pynput creates on its own thread.

        pynput creates the tap inside the listener thread and never exposes it,
        so wrap that one call to keep the handle. Without it we can neither
        check whether the tap is still enabled nor turn it back on."""
        create = listener._create_event_tap

        def _create_and_keep():
            tap = create()
            self._tap = tap
            return tap

        listener._create_event_tap = _create_and_keep

    def _await_tap(self, timeout: float = 1.0) -> None:
        """Block briefly until the listener thread has created its tap.

        The thread creates the tap a beat after ``start()`` returns, so without
        this the very first health check would see ``_tap is None`` and restart
        a listener that was coming up fine."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._tap is not None or not self._listener.is_alive():
                return
            time.sleep(0.02)

    def start(self) -> None:
        if self._carbon is not None:  # macOS: Carbon RegisterEventHotKey path
            if not self._carbon.start():
                print(
                    "captura: could not register the global hotkey "
                    f"({self._hotkey!r}) — it may be unmappable or already taken",
                    file=sys.stderr,
                )
            return
        self.stop()
        self._fired = False
        self._last_attempt = time.monotonic()
        self._last_tick = (time.monotonic(), time.time())
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
                self._await_tap()
            except Exception:
                self._listener = None
            finally:
                os.dup2(_saved, 2)
                os.close(_saved)
                os.close(_devnull)
            if self._listener is None or self._tap is None:
                # A missing tap is the login-race case: the listener thread is
                # up but deaf. The watchdog retries with backoff, so this stays
                # a log line — no dialog, per the app's UI rules.
                print(
                    "captura: hotkey listener unavailable (check Input Monitoring permission)",
                    file=sys.stderr,
                )
        else:
            try:
                self._listener = self._make_listener()
                self._listener.start()
            except Exception as exc:
                self._listener = None
                print(f"captura: hotkey listener unavailable: {exc}", file=sys.stderr)
        self._check_blocker()  # so callers see the state immediately, not after the first tick
        self._watchdog.start()

    def stop(self) -> None:
        if self._carbon is not None:
            self._carbon.stop()
            return
        self._watchdog.stop()
        self._tap = None
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def set_hotkey(self, hotkey: str) -> None:
        self._hotkey = hotkey
        if self._carbon is not None:
            self._carbon.set_hotkey(hotkey)
            return
        if self._listener is not None or self._watchdog.isActive():
            self.start()

    # -- health watchdog ------------------------------------------------------

    def _thread_alive(self) -> bool:
        listener = self._listener
        # pynput leaves ``running`` True when its run loop drops out from under
        # it, so the thread's own liveness is the honest half of this check.
        return listener is not None and listener.running and listener.is_alive()

    def _tap_enabled(self) -> bool | None:
        """True/False if the tap's state is known, None if it isn't knowable."""
        if self._tap is None or _CGEventTapIsEnabled is None:
            return None
        try:
            return bool(_CGEventTapIsEnabled(self._tap))
        except Exception:
            return None

    def _reenable_tap(self) -> bool:
        if self._tap is None or _CGEventTapEnable is None:
            return False
        try:
            _CGEventTapEnable(self._tap, True)
            return True
        except Exception:
            return False

    def is_healthy(self) -> bool:
        """True if the hotkey would actually fire right now."""
        if not self._thread_alive():
            return False
        if sys.platform != "darwin":
            return True
        if self._tap is None:
            return False
        return self._tap_enabled() is not False

    def blocker(self) -> str:
        """Process currently holding Secure Keyboard Entry, or ""."""
        return self._blocker

    def _check_blocker(self) -> None:
        # A tap can be created, enabled and permitted and still hear nothing:
        # while any process holds Secure Keyboard Entry, macOS delivers
        # keystrokes to no tap at all. Nothing here can fix that — it's the
        # other process's to release — but it must be *said*, or it looks
        # exactly like a broken hotkey with every permission check passing.
        from app import platform as platform_setup

        blocker = platform_setup.hotkey_blocker() or ""
        if blocker == self._blocker:
            return
        self._blocker = blocker
        if blocker:
            print(f"captura: hotkey silenced — macOS Secure Keyboard Entry is held by {blocker}",
                  file=sys.stderr)
        else:
            print("captura: Secure Keyboard Entry released; hotkey active again", file=sys.stderr)
        self.blocked_changed.emit(blocker)

    def ensure_alive(self) -> None:
        """Repair the listener if it has gone deaf. Safe to call any time."""
        try:
            self._check_blocker()
            mono, wall = time.monotonic(), time.time()
            last_mono, last_wall = self._last_tick
            self._last_tick = (mono, wall)
            # The process is frozen while the Mac sleeps: the wall clock keeps
            # running, the monotonic clock doesn't. A gap between the two means
            # we just woke, which is when taps come back dead most often — and
            # a dead tap can look enabled, so rebuild rather than probe.
            if (wall - last_wall) - (mono - last_mono) > _SLEEP_GAP_SECONDS:
                self._restart("woke from sleep")
                return
            if self.is_healthy():
                self._retry_delay = _RETRY_MIN_SECONDS
                return
            # A tap that exists but was switched off only needs re-arming.
            if self._thread_alive() and self._reenable_tap() and self.is_healthy():
                self._retry_delay = _RETRY_MIN_SECONDS
                return
            if mono - self._last_attempt >= self._retry_delay:
                self._restart("listener not responding")
        except Exception:
            traceback.print_exc()

    def _restart(self, reason: str) -> None:
        print(f"captura: restarting hotkey listener ({reason})", file=sys.stderr)
        # start() resets _last_attempt, so a failed attempt can't spin: the
        # delay doubles until the listener comes back (permission granted,
        # login finished), then resets.
        self._retry_delay = min(self._retry_delay * 2, _RETRY_MAX_SECONDS)
        self.start()
        if self.is_healthy():
            self._retry_delay = _RETRY_MIN_SECONDS
