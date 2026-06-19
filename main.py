"""Captura entry point: tray + global hotkey + capture flow + settings."""
from __future__ import annotations

import signal
import sys
import traceback

from PyQt6.QtWidgets import QApplication

from app import platform as platform_setup
from app.capture import CaptureController
from app.hotkey import HotkeyListener
from app.permissions import PermissionsPanel
from app.settings import Settings, SettingsPanel
from app.tray import TrayIcon


def main() -> int:
    platform_setup.setup()
    app = QApplication(sys.argv)
    app.setApplicationName("Captura")
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    settings = Settings.load()

    controller = CaptureController(settings)

    hotkey = HotkeyListener(settings.hotkey)
    hotkey.triggered.connect(controller.start_capture)
    hotkey.start()

    panel_ref: dict[str, SettingsPanel] = {}

    def open_settings() -> None:
        try:
            panel = panel_ref.get("panel")
            if panel is None or not panel.isVisible():
                panel = SettingsPanel(settings, hotkey)
                panel_ref["panel"] = panel
                panel.show()
            platform_setup.activate_app()
            panel.raise_()
            panel.activateWindow()
        except Exception:
            traceback.print_exc()

    perm_ref: dict[str, PermissionsPanel] = {}

    def open_permissions() -> None:
        try:
            had_accessibility = platform_setup.has_accessibility()
            panel = perm_ref.get("panel")
            if panel is None or not panel.isVisible():
                panel = PermissionsPanel()
                perm_ref["panel"] = panel
                panel.show()
            platform_setup.activate_app()
            panel.raise_()
            panel.activateWindow()
            # If Accessibility was granted since the listener started, restart
            # it so the active tap (hotkey suppression) takes effect.
            if not had_accessibility and platform_setup.has_accessibility():
                hotkey.start()
        except Exception:
            traceback.print_exc()

    tray = TrayIcon()
    tray.capture_requested.connect(controller.start_capture)
    tray.settings_requested.connect(open_settings)
    tray.permissions_requested.connect(open_permissions)
    tray.quit_requested.connect(app.quit)
    tray.show()

    exit_code = app.exec()
    hotkey.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
