"""macOS global hotkey via Carbon ``RegisterEventHotKey`` (ctypes).

Why not pynput's event tap on macOS: a ``CGEventTap`` is silenced whenever any
process holds **Secure Keyboard Entry** (a password field, or apps like Signal
that enable it and never let go). While it's held, macOS delivers key events to
*no* tap system-wide, so the hotkey goes dead through no fault of Captura's.

``RegisterEventHotKey`` is a different mechanism entirely — the app registers
one exact combo and the WindowServer posts a Carbon event when it's pressed. It
is **not** an event tap, so Secure Keyboard Entry does not block it (verified:
the handler fires with Secure Input enabled). It also needs neither Input
Monitoring nor Accessibility, and the system consumes the combo, so it never
leaks to the focused app. It's the same API Slack, VS Code and most menu-bar
apps use for global shortcuts.

The Carbon event is dispatched on the main run loop, which Qt drives — so the
callback runs on the Qt main thread and may touch Qt directly.
"""
from __future__ import annotations

import ctypes
import ctypes.util
from ctypes import CFUNCTYPE, POINTER, Structure, byref, c_int, c_uint32, c_void_p
from typing import Callable

_carbon = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Carbon"))


class _EventTypeSpec(Structure):
    _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]


class _EventHotKeyID(Structure):
    _fields_ = [("signature", c_uint32), ("id", c_uint32)]


_kEventClassKeyboard = 0x6B657962  # 'keyb'
_kEventHotKeyPressed = 6

# Carbon modifier masks (independent of the CG event flags).
_CMD, _SHIFT, _OPTION, _CONTROL = 0x0100, 0x0200, 0x0800, 0x1000

_carbon.GetApplicationEventTarget.restype = c_void_p
_carbon.InstallEventHandler.argtypes = [c_void_p, c_void_p, c_uint32, POINTER(_EventTypeSpec), c_void_p, POINTER(c_void_p)]
_carbon.InstallEventHandler.restype = c_int
_carbon.RegisterEventHotKey.argtypes = [c_uint32, c_uint32, _EventHotKeyID, c_void_p, c_uint32, POINTER(c_void_p)]
_carbon.RegisterEventHotKey.restype = c_int
_carbon.UnregisterEventHotKey.argtypes = [c_void_p]
_carbon.UnregisterEventHotKey.restype = c_int

# pynput-hotkey token → macOS ANSI virtual key code.
_VK = {
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4, "i": 34,
    "j": 38, "k": 40, "l": 37, "m": 46, "n": 45, "o": 31, "p": 35, "q": 12,
    "r": 15, "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26,
    "8": 28, "9": 25,
    "space": 49, "home": 115, "end": 119, "page_up": 116, "page_down": 121,
    "insert": 114, "left": 123, "right": 124, "down": 125, "up": 126,
    "print_screen": 105,  # mac keyboards have no PrintScreen; F13 is the nearest
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111, "f13": 105,
    "f14": 107, "f15": 113, "f16": 106, "f17": 64, "f18": 79, "f19": 80, "f20": 90,
}
_MODS = {"cmd": _CMD, "shift": _SHIFT, "alt": _OPTION, "ctrl": _CONTROL}


def parse_hotkey(hotkey: str) -> tuple[int, int] | None:
    """('<cmd>+<shift>+7') → (keycode, carbon_modifier_mask), or None if unmappable."""
    keycode: int | None = None
    mods = 0
    for token in hotkey.split("+"):
        name = token.strip("<>").lower()
        if name in _MODS:
            mods |= _MODS[name]
        elif name in _VK:
            if keycode is not None:
                return None  # two non-modifier keys: not a valid single hotkey
            keycode = _VK[name]
        else:
            return None
    if keycode is None:
        return None
    return keycode, mods


class CarbonHotKey:
    """Registers one global hotkey and calls ``on_activate`` when it fires.

    Reusable: ``set_hotkey`` swaps the combo, ``stop`` tears it down. The Carbon
    event handler is installed once and left in place for the object's life.
    """

    _HANDLER_PROC = CFUNCTYPE(c_int, c_void_p, c_void_p, c_void_p)

    def __init__(self, hotkey: str, on_activate: Callable[[], None]) -> None:
        self._hotkey = hotkey
        self._on_activate = on_activate
        self._ref: c_void_p | None = None
        self._handler_ref = c_void_p()
        self._installed = False
        # Keep a strong reference to the C callback — if it is garbage-collected
        # while registered, the next hotkey press calls freed memory and crashes.
        self._callback = self._HANDLER_PROC(self._handle)

    def _handle(self, next_handler, event, user_data) -> int:
        try:
            self._on_activate()
        except Exception:
            import traceback

            traceback.print_exc()
        return 0  # noErr — we handled it (also consumes the combo)

    def _install_handler(self) -> None:
        if self._installed:
            return
        target = _carbon.GetApplicationEventTarget()
        spec = _EventTypeSpec(_kEventClassKeyboard, _kEventHotKeyPressed)
        err = _carbon.InstallEventHandler(
            target, ctypes.cast(self._callback, c_void_p), 1, byref(spec), None,
            byref(self._handler_ref),
        )
        self._installed = err == 0
        if not self._installed:
            raise OSError(f"InstallEventHandler failed ({err})")

    def start(self) -> bool:
        """Register the hotkey. True on success, False if it couldn't be mapped
        or the OS refused it (the caller decides how loudly to complain)."""
        self.stop()
        parsed = parse_hotkey(self._hotkey)
        if parsed is None:
            return False
        keycode, mods = parsed
        self._install_handler()
        ref = c_void_p()
        err = _carbon.RegisterEventHotKey(
            keycode, mods, _EventHotKeyID(0x43415054, 1),  # 'CAPT'
            _carbon.GetApplicationEventTarget(), 0, byref(ref),
        )
        if err != 0:
            self._ref = None
            return False
        self._ref = ref
        return True

    def stop(self) -> None:
        if self._ref is not None:
            _carbon.UnregisterEventHotKey(self._ref)
            self._ref = None

    def set_hotkey(self, hotkey: str) -> bool:
        self._hotkey = hotkey
        return self.start()

    def is_registered(self) -> bool:
        return self._ref is not None
