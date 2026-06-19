"""pytesseract wrapper: text extraction off the UI thread."""
from __future__ import annotations

import io
import re
import shutil
from pathlib import Path

import pytesseract
from PIL import Image
from PyQt6.QtCore import QBuffer, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage

from app import platform as platform_setup


class TesseractMissingError(RuntimeError):
    pass


# pytesseract passes ``lang`` as one argv token (no shell), so this can't
# inject a separate flag — but bounding it at the subprocess boundary keeps
# the value sane regardless of how it was set.
_SAFE_LANG = re.compile(r"^[A-Za-z0-9_+/-]{1,64}$")


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in platform_setup.tesseract_paths():
        if Path(candidate).exists():
            return candidate
    return None


def _qimage_to_pil(image: QImage) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data())))


def extract_text(image: QImage, lang: str = "eng") -> str:
    """Blocking extraction — call from a worker thread, not the UI thread."""
    cmd = find_tesseract()
    if cmd is None:
        raise TesseractMissingError(
            f"Tesseract is not installed — {platform_setup.tesseract_install_hint()}"
        )
    if not _SAFE_LANG.match(lang):
        lang = "eng"
    pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract.image_to_string(_qimage_to_pil(image), lang=lang).strip()


class OcrTask(QObject):
    """Handle for one async extraction; signals fire on the UI thread."""

    finished = pyqtSignal(str)  # extracted text (may be empty)
    failed = pyqtSignal(str)  # short inline message


class _OcrRunnable(QRunnable):
    def __init__(self, task: OcrTask, image: QImage, lang: str) -> None:
        super().__init__()
        self._task = task
        self._image = image
        self._lang = lang

    def run(self) -> None:
        try:
            self._task.finished.emit(extract_text(self._image, self._lang))
        except TesseractMissingError as exc:
            self._task.failed.emit(str(exc))
        except Exception as exc:
            self._task.failed.emit(f"Text extraction failed: {exc}")


def extract_text_async(image: QImage, lang: str = "eng") -> OcrTask:
    """Run OCR on the global thread pool; returns the task handle.

    The caller must keep a reference to the returned task while it runs.
    """
    task = OcrTask()
    QThreadPool.globalInstance().start(_OcrRunnable(task, image.copy(), lang))
    return task
