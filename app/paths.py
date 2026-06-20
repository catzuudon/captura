"""Resource paths that work both from source and from a PyInstaller bundle."""
from __future__ import annotations

import sys
from pathlib import Path


def _bundle_root() -> Path:
    if hasattr(sys, "_MEIPASS"):  # PyInstaller extraction/bundle root
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return _bundle_root() / "assets"


def bundled_tesseract() -> Path | None:
    """Path to a Tesseract binary shipped inside the app, or None.

    Release builds vendor Tesseract under ``tesseract/`` so OCR works with no
    separate install. Running from source, this returns None and the caller
    falls back to a system Tesseract.
    """
    exe_name = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    exe = _bundle_root() / "tesseract" / exe_name
    return exe if exe.exists() else None


def bundled_tessdata() -> Path | None:
    """Path to the vendored ``tessdata`` directory, or None."""
    tessdata = _bundle_root() / "tesseract" / "tessdata"
    return tessdata if tessdata.exists() else None


ASSETS_DIR = assets_dir()
