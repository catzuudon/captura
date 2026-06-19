#!/bin/sh
# Build Captura.app (run from the project root).
set -e
BUNDLE_ID="com.captura.app"
VERSION=$(.venv/bin/python -c "import app; print(app.__version__)")
.venv/bin/pyinstaller --noconfirm --windowed --name Captura \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --icon "$PWD/assets/icon.icns" \
    --add-data "$PWD/assets:assets" \
    --specpath build \
    main.py
# Tray-only app: no Dock icon, no Cmd-Tab entry. Editing Info.plist
# invalidates the ad-hoc signature, so re-sign afterwards.
plutil -replace LSUIElement -bool true dist/Captura.app/Contents/Info.plist
plutil -replace CFBundleShortVersionString -string "$VERSION" dist/Captura.app/Contents/Info.plist
plutil -replace CFBundleVersion -string "$VERSION" dist/Captura.app/Contents/Info.plist
codesign --force --deep -s - dist/Captura.app
# Ad-hoc signatures change on every rebuild, so macOS treats each build as a
# new app: stale TCC grants (Screen Recording / Input Monitoring) silently
# stop matching. Reset them so the next launch prompts fresh and binds to
# this binary. Harmless if no entry exists.
tccutil reset ScreenCapture "$BUNDLE_ID" 2>/dev/null || true
tccutil reset ListenEvent "$BUNDLE_ID" 2>/dev/null || true
echo "Built: dist/Captura.app"
echo "After installing: launch, accept the Screen Recording prompt, then"
echo "quit and relaunch once (macOS applies the grant on next launch)."
