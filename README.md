# Captura

[![Latest release](https://img.shields.io/github/v/release/catzuudon/captura?label=release&color=4f7dff)](https://github.com/catzuudon/captura/releases/latest)
[![Total downloads](https://img.shields.io/github/downloads/catzuudon/captura/total?label=downloads&color=4f7dff)](https://github.com/catzuudon/captura/releases)
[![Latest downloads](https://img.shields.io/github/downloads/catzuudon/captura/latest/total?label=downloads%40latest&color=4f7dff)](https://github.com/catzuudon/captura/releases/latest)
[![License](https://img.shields.io/github/license/catzuudon/captura?color=4f7dff)](LICENSE)

A minimalist screenshot utility that gets out of your way. Press a key, select a region, annotate if you need to, and copy — no popups, no confirmations, no noise. Built-in OCR pulls text from anything on screen. Runs quietly in your tray.

Think Lightshot, but cleaner, faster, and smarter.

## Features

- **Instant capture** — global hotkey freezes and dims the screen; drag to select with live dimensions
- **Adjustable frame** — after selecting, drag any edge to resize or drag the inside to move the frame anywhere; nothing is final until you copy or save
- **Annotation tools** — pen, line, arrow, rectangle, ellipse, inline text (scroll to resize while typing), highlighter; 8-color palette + custom, three stroke widths, full undo/redo, Delete removes selected marks
- **OCR** — one click extracts text from the capture (Tesseract, fully local); result appears inline with a copy button
- **Fast output** — Enter or Ctrl+C copies the flattened image and closes everything; Save writes PNG/JPG; Escape cancels without a trace
- **Settings** — compact panel from the tray: rebind the hotkey, default save folder, image format, OCR language, launch at login, optional update check. Every change applies and saves immediately; **Esc** closes the panel (while recording a shortcut, the first Esc cancels the recording instead)

Default hotkeys: **PrintScreen** on Windows (Ctrl+PrintScreen if Snipping Tool owns the key — detected automatically), **Cmd+Shift+7** on macOS, **PrintScreen** on Linux. Rebind in Settings.

On macOS the global hotkey uses Carbon's `RegisterEventHotKey`, the same mechanism menu-bar apps use. Unlike an event tap it keeps working when another app holds **Secure Keyboard Entry** (Signal, 1Password, a password field), survives sleep/wake, and needs no Input Monitoring or Accessibility — just Screen Recording for the capture itself.

## Download

Grab the latest build for your platform from the [Releases page](../../releases):

| Platform | File |
|----------|------|
| macOS    | `Captura-<version>-macos.dmg` — open it, drag Captura to Applications |
| Windows  | `Captura-<version>-windows-setup.exe` — run the installer |
| Linux    | `Captura-<version>-linux-x86_64.tar.gz` — extract, run `./Captura/Captura` |

### macOS permissions

Captura needs **one** macOS permission (System Settings → Privacy & Security):

| Permission | Needed for | Required? |
|------------|-----------|-----------|
| **Screen Recording** | capturing pixels | Yes — prompted on first capture |

That's it since 1.1.4 — the global hotkey uses Carbon `RegisterEventHotKey`, which needs neither Input Monitoring nor Accessibility. After granting Screen Recording you may need to relaunch once (macOS applies the grant on next launch). The **tray → Permissions…** window shows the live grant state.

> **First launch is blocked by macOS.** You'll see *"Apple could not verify 'Captura' is free of malware…"* — expected for an open-source app not signed with a paid Apple certificate. To allow it:
>
> 1. Double-click Captura once (the block appears) and click **Done**.
> 2. Open **System Settings → Privacy & Security**, scroll to the **Security** section. You'll see *"Captura was blocked…"* with an **Open Anyway** button — click it, then confirm with **Open Anyway** and your password/Touch ID.
>
> (On older macOS, right-click the app → **Open** → **Open** also works.) If macOS still refuses, run this once in Terminal to clear the download quarantine:
>
> ```sh
> xattr -dr com.apple.quarantine /Applications/Captura.app
> ```

### Windows

The installer and app are unsigned, so SmartScreen may show "Windows protected your PC." Click **More info → Run anyway**. (This goes away once the project has a code-signing certificate.)

### Verifying downloads

Each release lists a SHA-256 checksum. To confirm a download wasn't tampered with:

```sh
shasum -a 256 Captura-1.1.0-macos.dmg        # macOS/Linux
certutil -hashfile Captura-1.1.0-windows-setup.exe SHA256   # Windows
```

Compare the output against the checksum on the release page.

## OCR engine

The downloaded installers **bundle Tesseract** (English + orientation data), so OCR works out of the box — no separate install.

For **other languages**, run Captura from source with a full Tesseract install and pick the language in Settings → OCR language. Install Tesseract and the language packs you want:

- macOS: `brew install tesseract tesseract-lang`
- Windows: [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) (select extra languages during setup)
- Linux: `sudo apt install tesseract-ocr tesseract-ocr-<lang>`

When run from source, the app auto-detects a system Tesseract and shows inline guidance in the result panel if it's missing.

## Build from source

```sh
# Python 3.11+
python3 -m venv .venv
.venv/bin/pip install -r requirements-build.txt          # Windows: .venv\Scripts\pip

# run from source
.venv/bin/python main.py

# build an installer
scripts/build_macos.sh && scripts/make_dmg.sh   # macOS → dist/Captura-<v>-macos.dmg
scripts\build_windows.bat                        # Windows → dist\Captura\ (then Inno Setup, see scripts/captura.iss)
scripts/build_linux.sh                           # Linux → dist/Captura-<v>-linux-x86_64.tar.gz
```

Releases for all three platforms are built automatically by GitHub Actions on a version tag — see [docs/RELEASING.md](docs/RELEASING.md). Versioning follows [SemVer](https://semver.org).

## Development

- Run: `.venv/bin/python main.py`
- Self-test (synthetic input, exercises capture → editor → OCR → settings end-to-end): `.venv/bin/python selftest.py`
- Input debugging: `CAPTURA_DEBUG=1` logs events to `$TMPDIR/captura-debug.log`
- Regenerate app icons from `assets/icon.svg`: `.venv/bin/python scripts/make_icons.py`

```
main.py            entry point
app/
  hotkey.py        pynput listener bridged to a Qt signal + hotkey mapping
  capture.py       mss capture + capture flow controller
  overlay.py       dim overlay + region selector
  editor/
    editor.py      editor window over the captured region (resize/move frame)
    toolbar.py     floating icon toolbar + color palette
    tools.py       annotation tool classes
    canvas.py      QGraphicsScene wrapper, undo stack
    ocr_panel.py   inline OCR result panel
  ocr.py           pytesseract wrapper (off-thread)
  tray.py          system tray icon/menu
  settings.py      JSON config (platformdirs) + settings panel
  platform/        OS-specific code, isolated (DPI, hotkey defaults,
                   permissions, login items, Tesseract discovery)
assets/            icons
scripts/           build + icon generation
```

## Download statistics

The badges above are live counts from GitHub. Because GitHub reports only a
*running total* per asset and keeps no history, a daily workflow
(`.github/workflows/stats.yml`) snapshots the numbers into
[`stats/downloads.csv`](stats/downloads.csv) — one row per asset per day, plus
a rolled-up [`stats/summary.json`](stats/summary.json). Difference two dated
rows to get a rate; the raw column is cumulative.

Run it on demand with `python3 scripts/collect_stats.py`.

What this can and can't tell you:

- ✅ Downloads per release and per platform, and how those totals move over time.
- ❌ **Whether anyone actually updated.** Captura has no telemetry and reports
  nothing back — deliberately, since it promises no network connections by
  default. Rising downloads on a new version alongside a flat older one is the
  closest honest proxy for adoption.
- ❌ Who or where. No identities, no geography, no referrers.

## Privacy & security

Captura runs entirely on your machine. **By default it makes no network connections** — nothing is uploaded, phoned home, or tracked. Captures and OCR text go only to your clipboard or a file you choose.

- OCR is local (Tesseract, bundled); images never leave the device.
- Settings live in your user config directory and are type-validated on load.
- No shell execution, no `eval`, no deserialization of untrusted data.

The **only** optional network use is an **update check, off by default** (Settings → *Check for updates*). When you turn it on, Captura makes one anonymous request to GitHub's public releases API to compare versions — it sends nothing about you or your machine, stores nothing, and never downloads or installs anything; a newer version just shows a link in the tray menu.

Found a security issue? Please report it privately (see [SECURITY.md](SECURITY.md)) rather than opening a public issue.

## License

[MIT](LICENSE) — free to use, modify, and distribute.

Built with PyQt6, mss, pynput, Pillow, and Tesseract.
