# Changelog

All notable changes to Captura are documented here. This project follows
[Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

## [1.0.2] — 2026-06-21

### Added
- **Optional update check** (Settings → *Check for updates*, off by default).
  When enabled, Captura anonymously checks GitHub's releases API on launch and
  daily, surfacing a quiet "Update available" link in the tray menu. It sends
  nothing about you and never downloads or installs anything.

## [1.0.1] — 2026-06-20

### Changed
- **Tesseract is now bundled** in the macOS, Windows, and Linux installers, so
  OCR works out of the box with no separate install. Running from source still
  uses a system Tesseract.

### Fixed
- CI now runs a headless-safe smoke test instead of the GUI self-test, and the
  release builds bundle assets correctly (the prior `--specpath` broke them).

## [1.0.0] — 2026-06-15

First public release.

### Features
- Global-hotkey capture with a frozen, dimmed screen and live selection dimensions
- Adjustable capture frame: drag any edge/corner to resize, drag the interior to move, or drag in the dim area to draw a fresh selection — all before copying
- Annotation tools: pen, line, arrow, rectangle, ellipse, inline text (scroll to resize), highlighter
- 8-color palette + custom color, three stroke widths, full undo/redo, delete selected
- Local OCR (Tesseract) with an inline result panel and one-click copy
- Copy to clipboard (Enter / Ctrl+C), save as PNG/JPG, cancel with Escape
- Settings panel: rebind hotkey, default save folder, image format, OCR language, launch at login
- Cross-platform: macOS, Windows, Linux

### macOS
- Needs only Screen Recording + Input Monitoring to work; Accessibility is optional
  (enables hotkey suppression, so the shortcut doesn't also reach the focused app).
  A tray **Permissions…** window shows each permission's status with a button to grant it.
- Fixed a macOS 26 crash (SIGTRAP) on hotkey rebind: pynput called Text Input Source
  APIs off the main thread, which newer macOS traps; that unused call is neutralized.

### Editor
- A frame edit only begins after the cursor moves past a small threshold, so a stray
  click on the border or dim area never nudges, collapses, or moves the frame.

### Security
- Settings file is type-validated on load; OCR language is bounded before reaching Tesseract
- macOS login-item plist is XML-escaped
- No network access, no shell execution, no deserialization of untrusted data
