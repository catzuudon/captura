# Captura — architecture &amp; implementation notes

Minimalist tray screenshot tool. Core areas: tray + global hotkey + overlay capture, the editor (annotation tools + undo/redo + copy/save + frame resize/move), OCR via Tesseract with an inline result panel, the settings panel (hotkey rebind via `hotkey_from_qt`, save dir, format, OCR language, launch-at-login per OS in `app/platform/`), and PyInstaller builds (icon + version from `app.__version__`).

## Settings (Phase 4)

- `SettingsPanel` lives in `app/settings.py`; every change applies + saves immediately (no OK button). Hotkey recording grabs the keyboard; `hotkey_from_qt` (app/hotkey.py) maps Qt events to pynput syntax — on macOS Qt's ControlModifier is the Cmd key (swapped), handled there.
- OCR language dropdown shows **friendly names** (`_LANGUAGE_NAMES`) with the Tesseract code in itemData; helper models (`_NON_LANGUAGES` = osd/snum/equ/dpi) are hidden; unknown installed codes still show by raw code. Checkbox checkmark is `assets/check.svg` injected into the QSS via `ASSETS_DIR`.
- Launch-at-login: macOS LaunchAgent plist / Windows HKCU Run key / Linux autostart .desktop, dispatched via `platform.set_launch_on_startup`; command from `platform.launch_command()` (frozen-aware).
- main.py keeps one panel instance in `panel_ref`; tray Settings raises it.

## OCR (Phase 3)

- `app/ocr.py` runs pytesseract on `QThreadPool` (never the UI thread); results come back via queued signals on an `OcrTask` handle the editor must keep referenced.
- OCR uses `EditorScene.original_image` (the raw capture, annotations excluded).
- Tesseract discovery: PATH first, then per-OS candidates from `app/platform/` (`tesseract_paths()`); missing binary shows an inline message with `tesseract_install_hint()` in the result panel — never a dialog.
- Result panel (`app/editor/ocr_panel.py`) is a frameless always-on-top window docked below the toolbar, text pre-selected, one Copy Text button. Closed with the editor.

## Editor architecture (Phase 2)

- Flow: selection → `CaptureController._on_selection` opens `EditorWindow` (fullscreen frameless QGraphicsView). `Toolbar` and `OcrPanel` are **plain child widgets inside the editor**, not separate windows — every separate-window variant (Qt.Tool, plain Window, "child window" parenting) eventually got buried or hidden by macOS z-order/activation behavior; a child widget paints above the viewport unconditionally and shares the editor's keyboard focus. Their `dock_to` methods work in editor-local (== screen-local) coordinates.
- `EditorScene` holds the capture as a background pixmap (DPR = physical/logical scale); every annotation is a QGraphicsItem tracked in `scene.annotations` with a QUndoStack (AddItem/MoveItems commands use the "first redo is a no-op" pattern).
- Tools are stateless-ish classes in `editor/tools.py` (press/move/release on scene coords); select mode = tool None (default scene behaviour, items movable only then). Text items commit on focus-out (discarded if empty); scroll while editing adjusts font size.
- `render_flattened()` renders the scene at full physical resolution; the editor's 1px border lives in `drawForeground` (view-level) so it is never flattened into output.
- `CaptureController._editors` keeps references to `WA_DeleteOnClose` editor windows — without it they'd be garbage-collected on show.

## Commands

- Run: `.venv/bin/python main.py` (venv is Python 3.12, deps in requirements.txt)
- Self-test (synthetic input, exercises capture + editor end-to-end): `.venv/bin/python selftest.py`

## Architecture rules

- All UI is PyQt6; no blocking calls on the UI thread (pynput and OCR run off-thread; cross-thread communication via queued Qt signals only).
- OS-specific code lives only in `app/platform/` (`windows.py` / `macos.py` / `linux.py`, dispatched in its `__init__`).
- Coordinates: Qt widgets use logical pixels, mss images are physical pixels. Each `ScreenOverlay` crops selections from its own frozen per-screen image (scale = image width / widget width), so logical→physical mapping never crosses screens — this is what keeps mixed-DPI multi-monitor correct. Don't introduce global-coordinate math.
- **Rotated displays:** mss reports a rotated (e.g. portrait) monitor in its *native* (landscape) orientation, so its width/height come back transposed — grabbing that region overshoots into the neighbouring display. `capture._grab_region` compares Qt's orientation (correct/presented) against mss's and swaps the grab dims when they disagree (orientation-only compare = DPI-independent). mss returns correctly-oriented *content* once the region is right, so no QImage rotation is needed. Verified live on a portrait external monitor.
- Hotkey strings use pynput `GlobalHotKeys` syntax (e.g. `<ctrl>+<print_screen>`), stored in settings JSON (platformdirs user config dir). On macOS the hotkey is **suppressed** so it doesn't leak to the focused app (e.g. Finder turning Cmd+Ctrl+A into Make Alias): `HotkeyListener` passes `darwin_intercept` (creates an *active* event tap), `_on_activate` sets `_fired` before `_handle_message` returns, and the intercept — which runs right after, same event — returns `None` to drop the completing keystroke (returns the event otherwise). Windows/Linux don't suppress yet (default PrintScreen hotkeys don't collide).
- UI philosophy is non-negotiable: no popups, no confirmations, no notifications, icon-only buttons. Errors surface inline, never as dialogs.

## Bundling checkpoint (pre-Phase-5 findings)

- `scripts/build_macos.sh` / `scripts/build_windows.bat` produce rough PyInstaller builds (~88MB; PyQt6 dominates). macOS bundle launched clean on first try.
- Asset lookups go through `app/paths.py` (`sys._MEIPASS` aware) — don't reintroduce `__file__`-relative asset paths.
- The bundled .app needs its **own** Screen Recording + Input Monitoring grants, separate from the terminal's — and **every rebuild re-signs the bundle, so the grant must be repeated**. `platform.ensure_screen_capture_access()` preflights and triggers the OS prompt (capture silently returns only the wallpaper without it).
- Capture session model: one at a time; overlays switch to `hold_dim()` (passive gray backdrop) behind the editor and close when it closes. Clicking the dim area refocuses the editor.
- **The "stroke anchored at (0,0)" bug** (looked like macOS event corruption for several rounds) was actually a Qt round-trip quirk: `QGraphicsPathItem` silently drops a path containing only a MoveTo, and `lineTo` on the resulting empty path anchors at (0,0). `PenTool` therefore keeps its `QPainterPath` as tool state and never reads it back via `item.path()`. Selftest asserts pen path geometry, not just annotation counts — keep it that way.
- Defense-in-depth that remains (harmless, verified): tool positions come from `QCursor.pos()` instead of event coords (`EditorScene._corrected_pos`; disabled via `CAPTURA_SYNTHETIC_INPUT=1`, which the selftest sets); strokes can't start outside the frame; first-drag-segment jumps >150px re-anchor. `CAPTURA_DEBUG=1` logs events + committed path geometry to `$TMPDIR/captura-debug.log`.
- Editor region model: the `EditorWindow` is a **static fullscreen** frameless window (geometry = screen.geometry(), set once and NEVER changed afterwards — macOS does not reliably apply window *size* changes during a live mouse drag; position changes worked, size changes silently froze, which caused multiple rounds of resize bugs). `EditorScene.sceneRect` = the full screen (identity mapping: viewport == scene == screen-local logical coords); `scene.region` = the capture frame. Frame resize/move/dim/border/handles are **pure repaints** via `_set_region` + `drawForeground` (dim outside region, border + 8 handles; view-level, never flattened). Flatten/OCR derive from `scene.region`. Corner zones are ±16px **in select mode only** (slim ±6px bands while a drawing tool is active); stale-drag self-healing in mousePress/mouseMove. In select mode a drag starting in the **dim area outside the frame draws a fresh selection** (`_new_select_origin`/`_apply_new_select`) — this is how you re-frame to the screen border or full-screen without the border resize zones getting in the way (resize zones cover the screen edge when the region touches it). **No `grabMouse()`** — the fullscreen window keeps the cursor inside so the implicit grab suffices, and an explicit grab steals clicks meant for the floating toolbar (broke tool switching entirely). The dim-hold overlay on the editor's own screen sits invisibly behind the fullscreen editor (kept for other screens). Flatten/OCR derive from sceneRect, so they always match the visible frame.
- Phase 5 done: app icon generated by `scripts/make_icons.py` (icon.svg → .icns/.ico, dark rounded backdrop), version stamped from `app.__version__`, `LSUIElement` set (tray-only). Tesseract is **not** bundled — documented per-OS install instead (inline hint when missing). `activate_app()` objc workaround kept (harmless when bundled).
- Remaining for public distribution (not blocking personal use): a real Apple Developer signing certificate + notarization (ends the per-rebuild permission re-grant), and a Windows code-signing cert (avoids SmartScreen warnings).

## Gotchas already handled

- DPI: `platform.setup()` sets the PassThrough rounding policy **before** QApplication exists; keep it that way.
- Windows 11 Snipping Tool may own PrintScreen — `app/platform/windows.py` reads `PrintScreenKeyForSnippingEnabled` and falls back to Ctrl+PrintScreen.
- `QSystemTrayIcon` does not own its context menu; `TrayIcon` keeps a reference.
- Overlays avoid `showFullScreen()` (macOS Space animation); they are frameless windows sized to the screen geometry.
- PyQt6 aborts the process (`qFatal`) if a Python exception escapes a slot — every slot/timer callback must be exception-guarded.
- **macOS 26 SIGTRAP on hotkey (re)start:** pynput's listener enters `keycode_context()` on its background thread, calling Text Input Source APIs that macOS 26 traps off-main-thread (`_dispatch_assert_queue_fail`). Crash fired on listener restart (e.g. rebinding the hotkey) once the GUI app was fully TSM-connected. `hotkey._neutralize_macos_tis()` replaces that contextmanager with a no-op at import — the listener never reads the context (only the unused keyboard Controller does). Repro needs a fully-initialized GUI app (window shown + `activate_app()` + processEvents), not a bare script.
- macOS prints "This process is not trusted!" from C-level stderr during pynput startup; `HotkeyListener.start()` suppresses it by redirecting fd 2 briefly. (Now also avoided in the common case: the passive listener used without Accessibility doesn't trip the trust check.)
- **macOS permissions (3):** Screen Recording (capture) + Input Monitoring (hotkey) are **required** and auto-prompted; Accessibility is **optional**, only for hotkey *suppression* (the `darwin_intercept` active tap needs it). `HotkeyListener._make_listener` uses the active tap **only if `platform.has_accessibility()`**, else a passive listener (hotkey works, no suppression) — so the app needs just 2 permissions to function. macOS never auto-prompts for Accessibility; tray → "Permissions…" calls `platform.request_permissions()` (prompts each, opens Settings panes for missing ones) and restarts the listener if Accessibility was just granted. Permission helpers live in `app/platform/macos.py` (ctypes: CGPreflight/Request, IOHIDCheckAccess/RequestAccess, AXIsProcessTrusted[WithOptions]).
