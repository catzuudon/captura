"""Opt-in update check against the public GitHub releases API.

Disabled by default. When the user enables it, Captura makes one anonymous
HTTPS request to the repository's ``releases/latest`` endpoint and compares the
published tag to the running version. It sends nothing about the user or their
machine beyond an ordinary HTTP request, stores nothing, and never downloads or
installs anything — a newer version only surfaces a link to the releases page.
Every failure (offline, rate-limited, malformed response) is swallowed silently.
"""
from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from app import __version__

_REPO = "catzuudon/captura"
_LATEST_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
_RELEASES_PAGE = f"https://github.com/{_REPO}/releases/latest"
_TIMEOUT = 6  # seconds


def releases_url() -> str:
    return _RELEASES_PAGE


def _parse_version(tag: str) -> tuple[int, ...]:
    """Lenient numeric parse: 'v1.2.3' / '1.2.3-beta' -> (1, 2, 3)."""
    parts: list[int] = []
    for chunk in tag.strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


class UpdateCheck(QObject):
    """Handle for one check. ``update_available`` fires on the UI thread only
    when a newer release exists; up-to-date or failed checks emit nothing."""

    update_available = pyqtSignal(str)  # latest version, e.g. "1.0.2"


class _Runnable(QRunnable):
    def __init__(self, check: UpdateCheck) -> None:
        super().__init__()
        self._check = check

    def run(self) -> None:
        try:
            request = urllib.request.Request(
                _LATEST_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"Captura/{__version__}",
                },
            )
            # nosec: URL is a fixed https constant — no user input, no other scheme.
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                if response.status != 200:
                    return
                data = json.loads(response.read().decode("utf-8"))
            tag = data.get("tag_name")
            if isinstance(tag, str) and is_newer(tag, __version__):
                self._check.update_available.emit(tag.strip().lstrip("vV"))
        except (URLError, ValueError, OSError, TimeoutError):
            pass  # offline, rate-limited, or malformed — stay silent by design


def check_for_updates() -> UpdateCheck:
    """Start an async check; keep the returned handle referenced while it runs."""
    check = UpdateCheck()
    QThreadPool.globalInstance().start(_Runnable(check))
    return check
