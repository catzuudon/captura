#!/bin/sh
# Package dist/Captura.app into a distributable DMG (drag-to-Applications).
# Run after scripts/build_macos.sh, from the project root.
set -e

APP="dist/Captura.app"
[ -d "$APP" ] || { echo "error: $APP not found — run scripts/build_macos.sh first"; exit 1; }

VERSION=$(.venv/bin/python -c "import app; print(app.__version__)")
DMG="dist/Captura-${VERSION}-macos.dmg"
STAGING=$(mktemp -d)

cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

rm -f "$DMG"
hdiutil create -volname "Captura" -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGING"

echo "Built: $DMG"
shasum -a 256 "$DMG"
