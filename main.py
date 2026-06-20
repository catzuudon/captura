"""Captura entry point: tray + global hotkey + capture flow + settings."""
from __future__ import annotations

import signal
import sys
import traceback

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication

from app import platform as platform_setup, updater
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
    tray.update_requested.connect(
        lambda: QDesktopServices.openUrl(QUrl(updater.releases_url()))
    )
    tray.quit_requested.connect(app.quit)
    tray.show()

    # Opt-in, off by default: when enabled, anonymously check GitHub for a newer
    # release on launch and once a day, surfacing a link in the tray if found.
    update_ref: dict[str, object] = {}

    def run_update_check() -> None:
        if not settings.check_for_updates:
            return
        check = updater.check_for_updates()
        check.update_available.connect(tray.show_update_available)
        update_ref["check"] = check  # keep alive until the worker finishes

    run_update_check()
    update_timer = QTimer()
    update_timer.setInterval(24 * 60 * 60 * 1000)  # daily while running
    update_timer.timeout.connect(run_update_check)
    update_timer.start()

    exit_code = app.exec()
    hotkey.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
