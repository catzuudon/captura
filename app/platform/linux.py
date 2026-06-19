"""Linux-specific behaviour."""
from __future__ import annotations


def setup() -> None:
    pass


def activate_app() -> None:
    pass


def ensure_screen_capture_access() -> bool:
    return True


def default_hotkey() -> str:
    return "<print_screen>"


def tesseract_paths() -> list[str]:
    return ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]


def tesseract_install_hint() -> str:
    return "sudo apt install tesseract-ocr"


def set_launch_on_startup(enabled: bool, command: list[str]) -> None:
    from pathlib import Path

    desktop_file = Path.home() / ".config" / "autostart" / "captura.desktop"
    if not enabled:
        desktop_file.unlink(missing_ok=True)
        return
    exec_line = " ".join(f'"{c}"' if " " in c else c for c in command)
    desktop_file.parent.mkdir(parents=True, exist_ok=True)
    desktop_file.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Captura\n"
        f"Exec={exec_line}\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
