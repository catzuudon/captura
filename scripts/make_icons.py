"""Generate the app icon (assets/icon.icns + assets/icon.ico) from icon.svg.

Run: .venv/bin/python scripts/make_icons.py  (from the project root)
Renders the capture-brackets glyph onto a dark rounded square at every
required size; iconutil packs the .icns (macOS only), Pillow packs the .ico.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter
from PyQt6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "icon.svg"


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Dark rounded tile with a subtle top-down gradient, matching the site's
    # logo tile; the blue glyph (from icon.svg) sits on top.
    margin = size * 0.05
    radius = size * 0.23
    tile = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    grad = QLinearGradient(0, tile.top(), 0, tile.bottom())
    grad.setColorAt(0.0, QColor("#1c1c24"))
    grad.setColorAt(1.0, QColor("#0e0e13"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRoundedRect(tile, radius, radius)
    # Faint inner border for definition (invisible at tiny sizes, polished large).
    if size >= 64:
        pen = painter.pen()
        pen.setColor(QColor(255, 255, 255, 22))
        pen.setWidthF(max(1.0, size * 0.006))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(tile, radius, radius)

    glyph = QSvgRenderer(str(SVG))
    inset = size * 0.27
    glyph.render(painter, QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    painter.end()
    return image


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 — required for rendering

    pngs: dict[int, Path] = {}
    tmp = Path(tempfile.mkdtemp(prefix="captura-icons-"))
    for size in (16, 32, 64, 128, 256, 512, 1024):
        path = tmp / f"icon_{size}.png"
        render(size).save(str(path))
        pngs[size] = path

    # .ico (Windows)
    from PIL import Image

    base = Image.open(pngs[256])
    base.save(
        ROOT / "assets" / "icon.ico",
        sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)],
    )
    print("wrote assets/icon.ico")

    # .icns (macOS)
    if sys.platform == "darwin":
        iconset = tmp / "icon.iconset"
        iconset.mkdir()
        for pt in (16, 32, 128, 256, 512):
            shutil.copy(pngs[pt], iconset / f"icon_{pt}x{pt}.png")
            shutil.copy(pngs[pt * 2], iconset / f"icon_{pt}x{pt}@2x.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(ROOT / "assets" / "icon.icns")],
            check=True,
        )
        print("wrote assets/icon.icns")

    shutil.rmtree(tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
