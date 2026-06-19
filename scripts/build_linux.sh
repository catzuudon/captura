#!/bin/sh
# Build a Linux distributable tarball (run from the project root).
# One-time setup:
#   python3 -m venv .venv
#   .venv/bin/pip install -r requirements-build.txt
# System packages Captura needs at runtime (Debian/Ubuntu):
#   sudo apt install tesseract-ocr libxcb-cursor0
set -e

VERSION=$(.venv/bin/python -c "import app; print(app.__version__)")
.venv/bin/pyinstaller --noconfirm --windowed --name Captura \
    --icon "$PWD/assets/icon.ico" \
    --add-data "$PWD/assets:assets" \
    --specpath build \
    main.py

TARBALL="dist/Captura-${VERSION}-linux-x86_64.tar.gz"
tar -czf "$TARBALL" -C dist Captura
echo "Built: $TARBALL"
sha256sum "$TARBALL"
echo "Run with: tar xzf $(basename "$TARBALL") && ./Captura/Captura"
