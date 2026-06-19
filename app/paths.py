"""Resource paths that work both from source and from a PyInstaller bundle."""
from __future__ import annotations

import sys
from pathlib import Path


def assets_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):  # PyInstaller extraction/bundle root
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


ASSETS_DIR = assets_dir()
