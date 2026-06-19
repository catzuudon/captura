"""Platform-specific behaviour, isolated per OS.

Everything that depends on the host OS (DPI quirks, default hotkey,
registry checks, startup integration) lives in this package so the rest
of the app stays platform-neutral.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication

if sys.platform == "win32":
    from app.platform import windows as _impl
elif sys.platform == "darwin":
    from app.platform import macos as _impl
else:
    from app.platform import linux as _impl


def setup() -> None:
    """OS and DPI setup. Must run before QApplication is created."""
    # Qt 6 is per-monitor DPI aware by default; PassThrough keeps fractional
    # scale factors exact so overlay geometry maps cleanly onto the physical
    # pixel data captured by mss.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _impl.setup()


def default_hotkey() -> str:
    """Default capture hotkey in pynput GlobalHotKeys syntax."""
    return _impl.default_hotkey()


def activate_app() -> None:
    """Make this process the active application (macOS needs an explicit
    nudge when running unbundled; no-op elsewhere)."""
    _impl.activate_app()


def ensure_screen_capture_access() -> bool:
    """True if screen capture is permitted; may trigger the OS prompt."""
    return _impl.ensure_screen_capture_access()


# -- macOS permissions (no-ops / always-granted on other platforms) ----------

def _impl_call(name: str, default: bool) -> bool:
    fn = getattr(_impl, name, None)
    return fn() if fn is not None else default


def has_accessibility() -> bool:
    """macOS: True if Accessibility is granted — required to *suppress* the
    hotkey so it doesn't also reach the focused app. No such concept
    elsewhere, so always True there."""
    return _impl_call("check_accessibility", True)


def request_input_monitoring() -> bool:
    return _impl_call("request_input_monitoring", True)


def request_accessibility() -> bool:
    return _impl_call("request_accessibility", True)


def permission_status() -> dict[str, bool]:
    """Granted-state of each macOS permission (empty dict off macOS)."""
    if sys.platform != "darwin":
        return {}
    return {
        "Screen Recording": _impl_call("check_screen_capture", True),
        "Input Monitoring": _impl_call("check_input_monitoring", True),
        "Accessibility": _impl_call("check_accessibility", True),
    }


_PRIVACY_ANCHORS = {
    "Screen Recording": "Privacy_ScreenCapture",
    "Input Monitoring": "Privacy_ListenEvent",
    "Accessibility": "Privacy_Accessibility",
}


def open_permission_settings(name: str) -> None:
    """Open System Settings to a specific Privacy pane (macOS only)."""
    if sys.platform != "darwin":
        return
    anchor = _PRIVACY_ANCHORS.get(name)
    if anchor:
        QDesktopServices.openUrl(
            QUrl(f"x-apple.systempreferences:com.apple.preference.security?{anchor}")
        )


def request_permission(name: str) -> None:
    """Trigger one permission's native prompt and open its Settings pane.

    The pane is the reliable part (the prompt only appears for permissions
    macOS considers undetermined), so we always open it as well."""
    if sys.platform != "darwin":
        return
    if name == "Screen Recording":
        ensure_screen_capture_access()
    elif name == "Input Monitoring":
        request_input_monitoring()
    elif name == "Accessibility":
        request_accessibility()
    open_permission_settings(name)


def tesseract_paths() -> list[str]:
    """Candidate Tesseract binary locations when it is not on PATH."""
    return _impl.tesseract_paths()


def tesseract_install_hint() -> str:
    """One-line install instruction shown inline when Tesseract is missing."""
    return _impl.tesseract_install_hint()


def launch_command() -> list[str]:
    """Command that relaunches this app (bundle binary or python + main.py)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(sys.argv[0]).resolve())]


def set_launch_on_startup(enabled: bool) -> None:
    """Register/unregister the app to start at login. Raises OSError on failure."""
    _impl.set_launch_on_startup(enabled, launch_command())
