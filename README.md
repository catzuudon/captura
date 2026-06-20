# Captura

A minimalist screenshot utility that gets out of your way. Press a key, select a region, annotate if you need to, and copy — no popups, no confirmations, no noise. Built-in OCR pulls text from anything on screen. Runs quietly in your tray.

Think Lightshot, but cleaner, faster, and smarter.

## Features

- **Instant capture** — global hotkey freezes and dims the screen; drag to select with live dimensions
- **Adjustable frame** — after selecting, drag any edge to resize or drag the inside to move the frame anywhere; nothing is final until you copy or save
- **Annotation tools** — pen, line, arrow, rectangle, ellipse, inline text (scroll to resize while typing), highlighter; 8-color palette + custom, three stroke widths, full undo/redo, Delete removes selected marks
- **OCR** — one click extracts text from the capture (Tesseract, fully local); result appears inline with a copy button
- **Fast output** — Enter or Ctrl+C copies the flattened image and closes everything; Save writes PNG/JPG; Escape cancels without a trace
- **Settings** — compact panel from the tray: rebind the hotkey, default save folder, image format, OCR language, launch at login, optional update check

Default hotkeys: **PrintScreen** on Windows (Ctrl+PrintScreen if Snipping Tool owns the key — detected automatically), **Cmd+Shift+7** on macOS, **PrintScreen** on Linux. Rebind in Settings.

## Download

Grab the latest build for your platform from the [Releases page](../../releases):

| Platform | File |
|----------|------|
| macOS    | `Captura-<version>-macos.dmg` — open it, drag Captura to Applications |
| Windows  | `Captura-<version>-windows-setup.exe` — run the installer |
| Linux    | `Captura-<version>-linux-x86_64.tar.gz` — extract, run `./Captura/Captura` |

### macOS permissions

Captura uses up to three macOS permissions (System Settings → Privacy & Security):

| Permission | Needed for | Required? |
|------------|-----------|-----------|
| **Screen Recording** | capturing pixels | Yes — prompted on first capture |
| **Input Monitoring** | the global hotkey | Yes — prompted when the app starts |
| **Accessibility** | stopping the hotkey from also reaching the focused app (e.g. Finder turning Cmd+Ctrl+A into "Make Alias") | Optional |

The two required permissions are prompted automatically. **Accessibility is optional** — without it the hotkey still works, it just also passes through to whatever app is focused. macOS never prompts for Accessibility on its own, so Captura offers a **tray → Permissions…** item that requests all three and opens the right Settings panes for any that are missing. After granting a permission, you may need to relaunch (macOS applies some grants only on next launch).

> First launch shows "Captura can't be opened because Apple cannot check it for malicious software." This is expected — the app is open-source and not signed with a paid Apple certificate. Right-click the app → **Open** → **Open**, or allow it under System Settings → Privacy & Security → **Open Anyway**.

### Windows

The installer and app are unsigned, so SmartScreen may show "Windows protected your PC." Click **More info → Run anyway**. (This goes away once the project has a code-signing certificate.)

### Verifying downloads

Each release lists a SHA-256 checksum. To confirm a download wasn't tampered with:

```sh
shasum -a 256 Captura-1.0.0-macos.dmg        # macOS/Linux
certutil -hashfile Captura-1.0.0-windows-setup.exe SHA256   # Windows
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
