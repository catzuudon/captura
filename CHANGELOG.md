# Changelog

All notable changes to Captura are documented here. This project follows
[Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH.

## [1.1.1] — 2026-09-10

### Security
- **Pillow 12.2.0 → 12.3.0**, clearing all 13 open Dependabot alerts (10 high,
  3 moderate) — every one of them was Pillow. Worth stating the real exposure:
  Captura's only Pillow entry point is `Image.open()` on a PNG that Qt itself
  just serialized from a screen capture (`app/ocr.py`), so the affected
  codepaths (PDF, JPEG2000, TGA, EPS, BDF/PCF fonts, GD, ImageCms) are never
  reached and the input is never attacker-supplied. Bumped as hygiene, not as
  an emergency.

### Added
- **Download statistics.** `scripts/collect_stats.py` plus a daily workflow
  snapshot per-release, per-platform download counts into `stats/downloads.csv`
  with a rolled-up `stats/summary.json`. GitHub reports only a running total and
  keeps no history, so a trend can't be reconstructed after the fact — it has to
  be recorded as it goes. README gained release/downloads/license badges.
  Captura still reports nothing about itself: there is no telemetry, so this
  measures downloads, never installs or upgrades.

### Changed
- platformdirs 4.10.0 → 4.11.7 (config path verified unchanged), pyinstaller
  6.20.0 → 6.22.2.
- GitHub Actions brought current: checkout v4→v7, setup-python v5→v7,
  upload-artifact v4→v7 with download-artifact v4→v8 (the pairing its own docs
  specify), codeql-action v3→v4, action-gh-release v2→v3. upload-artifact v4
  was heading for deprecation, which would eventually have broken releases.
- `pynput` stays pinned at 1.8.2 and is now commented as such: `app/hotkey.py`
  patches its private internals (macOS TIS neutralization, event-tap handle
  capture), so a bump needs those re-verified rather than assumed.

## [1.1.0] — 2026-09-10

### Added
- **Esc closes the Settings and Permissions windows.** While recording a new
  shortcut, the first Esc still cancels the recording; a second one closes the
  window.

### Fixed
- **macOS: the hotkey no longer goes dead after sleep/wake or a cold boot.**
  macOS disables an app's event tap behind its back (across sleep/wake and
  after a tap timeout) and refuses to create one at all when the app launches
  at login before the permission system is ready — in every case pynput still
  reported a healthy listener, so the hotkey silently stopped working until
  Captura was relaunched. A watchdog now checks the tap every 5s, re-arms it
  when macOS switches it off, and rebuilds the listener after a wake or when
  the tap was never created (retrying with backoff while permissions settle).

### Docs
- Website: added a **macOS permissions** card to the first-launch help, listing
  which of the three permissions are required and which is optional — the
  previous cards only covered getting past Gatekeeper, not what to grant after.
- README: documented the self-healing hotkey listener and the Esc shortcut, and
  refreshed the checksum example (it still named 1.0.0).

## [1.0.3] — 2026-06-21

### Changed
- macOS menu-bar icon is now a monochrome template that the system tints to
  match the bar (instead of the blue glyph, which stood out). Only the macOS
  tray changed — the app icon, Windows tray, and website are unchanged.

### Fixed
- Windows: the dim overlay no longer lingers after copying a capture. It was
  torn down on the editor's deferred destruction, which Windows processes a
  cycle late; it now closes the instant the editor closes.

### Docs
- Clearer macOS first-launch steps (Sequoia "Open Anyway" flow + a quarantine-
  clearing command) since the old right-click-Open path no longer applies.

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
