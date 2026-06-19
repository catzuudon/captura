"""JSON-backed settings + the compact settings panel."""
from __future__ import annotations

import json
import re
import traceback
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_config_dir
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import platform as platform_setup
from app.hotkey import hotkey_from_qt, pretty_hotkey
from app.paths import ASSETS_DIR

if TYPE_CHECKING:
    from app.hotkey import HotkeyListener

# Friendly names for the common Tesseract language codes. Anything installed
# but not listed still appears (by its raw code), so custom packs work.
_LANGUAGE_NAMES = {
    "eng": "English", "fil": "Filipino", "tgl": "Tagalog", "spa": "Spanish",
    "fra": "French", "deu": "German", "ita": "Italian", "por": "Portuguese",
    "nld": "Dutch", "rus": "Russian", "ukr": "Ukrainian", "pol": "Polish",
    "tur": "Turkish", "ara": "Arabic", "heb": "Hebrew", "hin": "Hindi",
    "ben": "Bengali", "tha": "Thai", "vie": "Vietnamese", "ind": "Indonesian",
    "msa": "Malay", "jpn": "Japanese", "kor": "Korean",
    "chi_sim": "Chinese (Simplified)", "chi_tra": "Chinese (Traditional)",
    "ces": "Czech", "swe": "Swedish", "dan": "Danish", "fin": "Finnish",
    "nor": "Norwegian", "ell": "Greek", "ron": "Romanian", "hun": "Hungarian",
}
# Tesseract ships helper models that are not selectable languages.
_NON_LANGUAGES = {"osd", "snum", "equ", "dpi"}

_CONFIG_DIR = Path(user_config_dir("Captura", appauthor=False))
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

# Tesseract language spec: codes, "+"-combined, optional "script/" prefix.
# Bounds the value that reaches pytesseract's command line.
_SAFE_LANG = re.compile(r"^[A-Za-z0-9_+/-]{1,64}$")


@dataclass
class Settings:
    hotkey: str = ""
    save_dir: str = ""
    image_format: str = "png"
    ocr_language: str = "eng"
    launch_on_startup: bool = False

    @classmethod
    def load(cls) -> "Settings":
        data: dict = {}
        try:
            raw = json.loads(_CONFIG_FILE.read_text("utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, ValueError):
            pass
        # Coerce each field to its declared type, dropping anything malformed.
        # The config file is local, but validating keeps a corrupted or
        # tampered file from injecting unexpected types into the app.
        clean: dict = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            # f.type is a string here ("bool"/"str") due to PEP 563 annotations.
            if f.type == "bool" and isinstance(value, bool):
                clean[f.name] = value
            elif f.type == "str" and isinstance(value, str):
                clean[f.name] = value
        settings = cls(**clean)
        if not settings.hotkey:
            settings.hotkey = platform_setup.default_hotkey()
        settings.image_format = "jpg" if settings.image_format.lower() in ("jpg", "jpeg") else "png"
        if not settings.save_dir or not Path(settings.save_dir).expanduser().is_absolute():
            settings.save_dir = str(Path.home() / "Pictures")
        if not _SAFE_LANG.match(settings.ocr_language):
            settings.ocr_language = "eng"
        return settings

    def save(self) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2), "utf-8")


_PANEL_STYLE = """
QWidget#settings { background: #232323; }
QLabel { color: #9a9a9a; font-size: 12px; }
QLabel#title { color: #f0f0f0; font-size: 16px; font-weight: 600; }
QLabel#subtitle { color: #888; font-size: 11px; }
QFrame#sep { background: #383838; max-height: 1px; min-height: 1px; border: none; }
QPushButton[control="true"], QComboBox {
    background: #333333; color: #ececec; border: 1px solid #4a4a4a;
    border-radius: 6px; padding: 0 10px; min-height: 28px; font-size: 12px;
    text-align: left;
}
QPushButton[control="true"]:hover, QComboBox:hover { background: #3c3c3c; border-color: #5a5a5a; }
QPushButton[recording="true"] { border-color: #4f7dff; color: #9fc0ff; background: #1e2740; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #9a9a9a; margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: #333333; color: #ececec; border: 1px solid #4a4a4a;
    border-radius: 6px; padding: 4px; outline: none;
    selection-background-color: #4f7dff; selection-color: #ffffff;
}
QComboBox QLineEdit { background: transparent; color: #ececec; border: none; }
QCheckBox { color: #cfcfcf; font-size: 12px; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #5a5a5a; background: #333333;
}
QCheckBox::indicator:checked {
    background: #4f7dff; border-color: #4f7dff; image: url(%(check)s);
}
QLabel#status { color: #e0a060; font-size: 11px; }
""" % {"check": (ASSETS_DIR / "check.svg").as_posix()}

_CONTROL_WIDTH = 190


class SettingsPanel(QWidget):
    """The one compact settings panel. Every change applies immediately."""

    def __init__(self, settings: Settings, hotkey_listener: HotkeyListener) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self._settings = settings
        self._listener = hotkey_listener
        self._recording = False

        self.setObjectName("settings")
        self.setStyleSheet(_PANEL_STYLE)
        self.setWindowTitle("Captura Settings")
        self.setFixedWidth(380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(4)

        title = QLabel("Settings")
        title.setObjectName("title")
        subtitle = QLabel("Changes apply and save automatically")
        subtitle.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        separator = QFrame()
        separator.setObjectName("sep")
        outer.addSpacing(12)
        outer.addWidget(separator)
        outer.addSpacing(14)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)

        self._hotkey_btn = self._control_button(
            pretty_hotkey(settings.hotkey), "Click, then press the new shortcut (Esc cancels)"
        )
        self._hotkey_btn.clicked.connect(self._start_recording)
        form.addRow(self._field_label("Shortcut"), self._hotkey_btn)

        self._dir_btn = self._control_button(self._short_dir(), settings.save_dir)
        self._dir_btn.clicked.connect(self._pick_dir)
        form.addRow(self._field_label("Save to"), self._dir_btn)

        self._format_box = QComboBox()
        self._format_box.addItems(["PNG", "JPG"])
        self._format_box.setCurrentText(settings.image_format.upper())
        self._format_box.setFixedWidth(_CONTROL_WIDTH)
        self._format_box.currentTextChanged.connect(self._set_format)
        form.addRow(self._field_label("Format"), self._format_box)

        self._lang_box = QComboBox()
        self._lang_box.setFixedWidth(_CONTROL_WIDTH)
        self._populate_languages()
        self._lang_box.currentIndexChanged.connect(self._set_language)
        form.addRow(self._field_label("OCR language"), self._lang_box)

        outer.addLayout(form)
        outer.addSpacing(16)

        self._startup_box = QCheckBox("Launch Captura at login")
        self._startup_box.setChecked(settings.launch_on_startup)
        self._startup_box.toggled.connect(self._set_startup)
        outer.addWidget(self._startup_box)

        self._status = QLabel("")
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        self._status.hide()
        outer.addSpacing(6)
        outer.addWidget(self._status)

    def _field_label(self, text: str) -> QLabel:
        return QLabel(text)

    def _control_button(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("control", "true")
        btn.setToolTip(tooltip)
        btn.setFixedWidth(_CONTROL_WIDTH)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # -- helpers ---------------------------------------------------------------

    def _short_dir(self) -> str:
        path = Path(self._settings.save_dir)
        try:
            return "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def _save(self) -> None:
        try:
            self._settings.save()
            self._status.hide()
        except OSError as exc:
            self._show_status(f"Could not save settings: {exc}")

    def _show_status(self, message: str) -> None:
        self._status.setText(message)
        self._status.show()

    def _populate_languages(self) -> None:
        """Fill the dropdown with friendly language names (code stored as data).

        Helper models (osd/snum/…) are hidden; unknown installed codes still
        appear by their raw code so custom language packs remain selectable."""
        codes: list[str] = []
        try:
            import pytesseract

            from app import ocr

            cmd = ocr.find_tesseract()
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
                codes = [
                    c for c in pytesseract.get_languages(config="")
                    if c not in _NON_LANGUAGES
                ]
        except Exception:
            pass
        if not codes:
            codes = [self._settings.ocr_language or "eng"]

        def friendly(code: str) -> str:
            return _LANGUAGE_NAMES.get(code, code)

        codes = sorted(set(codes), key=lambda c: friendly(c).lower())
        self._lang_box.blockSignals(True)
        for code in codes:
            self._lang_box.addItem(friendly(code), code)
        idx = self._lang_box.findData(self._settings.ocr_language)
        self._lang_box.setCurrentIndex(idx if idx >= 0 else 0)
        self._lang_box.blockSignals(False)

    # -- hotkey recording --------------------------------------------------------

    def _start_recording(self) -> None:
        self._recording = True
        self._hotkey_btn.setText("Press shortcut…")
        self._hotkey_btn.setProperty("recording", "true")
        self._restyle(self._hotkey_btn)
        self.grabKeyboard()

    def _stop_recording(self) -> None:
        self._recording = False
        self._hotkey_btn.setText(pretty_hotkey(self._settings.hotkey))
        self._hotkey_btn.setProperty("recording", "false")
        self._restyle(self._hotkey_btn)
        self.releaseKeyboard()

    @staticmethod
    def _restyle(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._stop_recording()
            return
        hotkey = hotkey_from_qt(event)
        if hotkey is None:
            return  # modifier-only or unusable; keep listening
        self._settings.hotkey = hotkey
        self._save()
        try:
            self._listener.set_hotkey(hotkey)
        except Exception:
            traceback.print_exc()
            self._show_status("Shortcut saved; it takes effect on next launch.")
        self._stop_recording()

    def closeEvent(self, event) -> None:
        if self._recording:
            self._stop_recording()
        super().closeEvent(event)

    # -- field slots ---------------------------------------------------------

    def _pick_dir(self) -> None:
        try:
            path = QFileDialog.getExistingDirectory(
                self, "Default save folder", self._settings.save_dir
            )
            if path:
                self._settings.save_dir = path
                self._dir_btn.setText(self._short_dir())
                self._dir_btn.setToolTip(path)
                self._save()
        except Exception:
            traceback.print_exc()

    def _set_format(self, text: str) -> None:
        self._settings.image_format = text.lower()
        self._save()

    def _set_language(self, index: int) -> None:
        code = self._lang_box.itemData(index)
        if code:
            self._settings.ocr_language = code
            self._save()

    def _set_startup(self, enabled: bool) -> None:
        try:
            platform_setup.set_launch_on_startup(enabled)
        except OSError as exc:
            traceback.print_exc()
            self._startup_box.blockSignals(True)
            self._startup_box.setChecked(not enabled)
            self._startup_box.blockSignals(False)
            self._show_status(f"Could not update login item: {exc}")
            return
        self._settings.launch_on_startup = enabled
        self._save()
