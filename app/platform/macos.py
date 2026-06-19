"""macOS-specific behaviour."""
from __future__ import annotations

import ctypes
import ctypes.util
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape


def setup() -> None:
    pass


def activate_app() -> None:
    """Force this process to be the active application.

    Running from a terminal (no app bundle), the process often stays
    inactive: its windows then get 'inactive window' clicks with corrupted
    coordinates and the key window flaps. [NSApp activateIgnoringOtherApps:]
    fixes both. Failures are non-fatal.
    """
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send_id = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            ("objc_msgSend", objc)
        )
        send_bool = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(
            ("objc_msgSend", objc)
        )
        nsapp = send_id(
            objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication")
        )
        if nsapp:
            send_bool(nsapp, objc.sel_registerName(b"activateIgnoringOtherApps:"), True)
    except Exception:
        pass


def default_hotkey() -> str:
    # Mac keyboards have no PrintScreen key; Cmd+Shift+7 is the nearest
    # free slot next to the system screenshot shortcuts (Cmd+Shift+3/4/5).
    return "<cmd>+<shift>+7"


def ensure_screen_capture_access() -> bool:
    """Check Screen Recording permission; trigger the OS prompt if missing.

    Without it, CoreGraphics silently captures only the wallpaper. The
    permission is per-signature, so every rebuilt bundle needs a re-grant.
    """
    try:
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        if cg.CGPreflightScreenCaptureAccess():
            return True
        cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        return bool(cg.CGRequestScreenCaptureAccess())
    except Exception:
        return True  # older macOS without the API


# Permission model (macOS):
#   Screen Recording  — required, to capture pixels (CGRequestScreenCaptureAccess)
#   Input Monitoring  — required, for the global hotkey (pynput's event tap)
#   Accessibility     — optional, only to *suppress* the hotkey so it doesn't
#                       also reach the focused app (e.g. Finder's Make Alias)
# macOS never auto-prompts for Accessibility; an app must explicitly call
# AXIsProcessTrustedWithOptions with the prompt option, which these helpers do.


def check_screen_capture() -> bool:
    try:
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(cg.CGPreflightScreenCaptureAccess())
    except Exception:
        return True


def check_input_monitoring() -> bool:
    try:
        iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
        iokit.IOHIDCheckAccess.restype = ctypes.c_int
        iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint]
        return iokit.IOHIDCheckAccess(1) == 0  # 1=ListenEvent, 0=Granted
    except Exception:
        return True


def request_input_monitoring() -> bool:
    """Trigger the Input Monitoring prompt if status is undetermined."""
    try:
        iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
        iokit.IOHIDCheckAccess.restype = ctypes.c_int
        iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint]
        if iokit.IOHIDCheckAccess(1) == 0:
            return True
        iokit.IOHIDRequestAccess.restype = ctypes.c_bool
        iokit.IOHIDRequestAccess.argtypes = [ctypes.c_uint]
        return bool(iokit.IOHIDRequestAccess(1))
    except Exception:
        return True


def check_accessibility() -> bool:
    try:
        appsvc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        appsvc.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(appsvc.AXIsProcessTrusted())
    except Exception:
        return False


def request_accessibility() -> bool:
    """Show the native Accessibility prompt (offers "Open System Settings")."""
    try:
        appsvc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        appsvc.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        appsvc.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        prompt_key = ctypes.c_void_p.in_dll(appsvc, "kAXTrustedCheckOptionPrompt")
        true_val = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
        ]
        keys = (ctypes.c_void_p * 1)(prompt_key)
        vals = (ctypes.c_void_p * 1)(true_val)
        opts = cf.CFDictionaryCreate(None, keys, vals, 1, None, None)
        trusted = bool(appsvc.AXIsProcessTrustedWithOptions(opts))
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease(opts)
        return trusted
    except Exception:
        return False


def tesseract_paths() -> list[str]:
    return ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]


def tesseract_install_hint() -> str:
    return "brew install tesseract"


_LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.captura.app.plist"


def set_launch_on_startup(enabled: bool, command: list[str]) -> None:
    if not enabled:
        _LAUNCH_AGENT.unlink(missing_ok=True)
        return
    # Escape paths so a folder name with & < > can't corrupt the plist XML.
    args = "\n".join(f"        <string>{_xml_escape(c)}</string>" for c in command)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.captura.app</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    _LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    _LAUNCH_AGENT.write_text(plist, encoding="utf-8")
