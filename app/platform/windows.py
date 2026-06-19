"""Windows-specific behaviour."""
from __future__ import annotations


def setup() -> None:
    pass


def activate_app() -> None:
    pass


def ensure_screen_capture_access() -> bool:
    return True


def default_hotkey() -> str:
    return "<ctrl>+<print_screen>" if _printscreen_hijacked() else "<print_screen>"


def tesseract_paths() -> list[str]:
    return [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]


def tesseract_install_hint() -> str:
    return "install Tesseract from github.com/UB-Mannheim/tesseract"


def set_launch_on_startup(enabled: bool, command: list[str]) -> None:
    import winreg

    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            cmd = " ".join(f'"{c}"' for c in command)
            winreg.SetValueEx(key, "Captura", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "Captura")
            except FileNotFoundError:
                pass


def _printscreen_hijacked() -> bool:
    """Windows 11 lets Snipping Tool claim the PrintScreen key.

    Recent builds enable that binding by default, so a missing registry
    value is treated as hijacked and we fall back to Ctrl+PrintScreen.
    """
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Keyboard") as key:
            value, _ = winreg.QueryValueEx(key, "PrintScreenKeyForSnippingEnabled")
        return bool(value)
    except OSError:
        return True
