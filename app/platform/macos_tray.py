"""Native macOS menu-bar item (NSStatusItem + NSMenu) via pyobjc.

Why not QSystemTrayIcon: on macOS 27, AppKit drives controls through gesture
recognizers, so ``NSApp.currentEvent`` is often not a mouse event when the
status-item click callback runs. Qt ≤ 6.11.2 calls ``-[NSEvent clickCount]``
on it unconditionally, which asserts and aborts the whole process — the
"click the menu-bar icon and the app closes" bug. Qt has fixed this upstream
(qtbase 6192d9edd0, 2026-07-30) but no released Qt or PyQt6 carries it yet.

Owning the status item here means Qt never registers its observers on it, so
the crashing code path cannot run regardless of Qt version. pyobjc is already
bundled (pynput depends on it), so this costs nothing at packaging time.

Must be constructed on the main thread. Menu actions are dispatched by AppKit
on the main thread inside Qt's own event loop, so callbacks may touch Qt.
"""
from __future__ import annotations

import traceback
from typing import Callable

import objc
from AppKit import (
    NSImage,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSData, NSObject
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PyQt6.QtGui import QIcon

_ICON_POINTS = 18  # menu-bar glyph size in points; rendered at 2x for Retina


class _MenuTarget(NSObject):
    """The Objective-C object NSMenuItem sends its action to."""

    def initWithCallbacks_(self, callbacks):
        self = objc.super(_MenuTarget, self).init()
        if self is None:
            return None
        self._callbacks = dict(callbacks)  # tag -> python callable
        return self

    def fire_(self, sender):  # selector "fire:"
        callback = self._callbacks.get(sender.tag())
        if callback is None:
            return
        try:
            callback()
        except Exception:
            # PyQt aborts on an exception escaping a slot; AppKit would swallow
            # this one silently instead, which is worse. Log it.
            traceback.print_exc()


class MacStatusItem:
    """A menu-bar icon with a fixed action list plus two mutable lines.

    ``actions`` is an ordered list of (label, callback); a label of ``"-"``
    inserts a separator. The *update* line (hidden until ``set_update``) sits
    before the last action, and the *warning* line (hidden until
    ``set_warning``) sits at the very top, disabled, as a plain status readout.
    """

    def __init__(self, icon_svg: str, tooltip: str, actions: list[tuple[str, Callable[[], None]]],
                 update_callback: Callable[[], None]) -> None:
        self._menu = NSMenu.alloc().initWithTitle_("Captura")
        # Enabled state is set explicitly below; don't let AppKit re-derive it.
        self._menu.setAutoenablesItems_(False)

        callbacks: dict[int, Callable[[], None]] = {}
        self._warning = self._item("", tag=0)
        self._warning.setEnabled_(False)
        self._warning.setHidden_(True)
        self._menu.addItem_(self._warning)
        self._warning_sep = NSMenuItem.separatorItem()
        self._warning_sep.setHidden_(True)
        self._menu.addItem_(self._warning_sep)

        tag = 1
        for index, (label, callback) in enumerate(actions):
            if index == len(actions) - 1:
                # Update line + its separator, just above the final (Quit) item.
                self._update_sep = NSMenuItem.separatorItem()
                self._update_sep.setHidden_(True)
                self._menu.addItem_(self._update_sep)
                self._update = self._item("", tag=tag)
                self._update.setHidden_(True)
                callbacks[tag] = update_callback
                self._menu.addItem_(self._update)
                tag += 1
            if label == "-":
                self._menu.addItem_(NSMenuItem.separatorItem())
                continue
            item = self._item(label, tag=tag)
            callbacks[tag] = callback
            self._menu.addItem_(item)
            tag += 1

        # Target must outlive the menu items; keep a strong reference.
        self._target = _MenuTarget.alloc().initWithCallbacks_(callbacks)
        for item in self._menu.itemArray():
            if not item.isSeparatorItem():
                item.setTarget_(self._target)

        self._image = _template_image(icon_svg)
        self._status_item = None
        self._tooltip = tooltip
        self._visible = False

    def _item(self, label: str, tag: int) -> NSMenuItem:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, "fire:", "")
        item.setTag_(tag)
        return item

    # -- public API (mirrors what tray.py needs) -------------------------------

    def show(self) -> None:
        if self._status_item is not None:
            return
        bar = NSStatusBar.systemStatusBar()
        self._status_item = bar.statusItemWithLength_(NSVariableStatusItemLength)
        button = self._status_item.button()
        button.setImage_(self._image)
        button.setToolTip_(self._tooltip)
        self._status_item.setMenu_(self._menu)
        self._visible = True

    def is_visible(self) -> bool:
        return self._visible

    def set_tooltip(self, text: str) -> None:
        self._tooltip = text
        if self._status_item is not None:
            self._status_item.button().setToolTip_(text)

    def set_update(self, label: str | None) -> None:
        shown = bool(label)
        self._update.setTitle_(label or "")
        self._update.setHidden_(not shown)
        self._update_sep.setHidden_(not shown)

    def set_warning(self, text: str | None) -> None:
        shown = bool(text)
        self._warning.setTitle_(text or "")
        self._warning.setHidden_(not shown)
        self._warning_sep.setHidden_(not shown)


def _template_image(svg_path: str) -> NSImage:
    """Render the SVG through Qt at 2x and hand AppKit a template NSImage.

    Going through Qt keeps the single SVG asset as the source of truth and
    sidesteps NSImage's inconsistent SVG sizing; ``setTemplate_`` lets the
    system tint it to match the menu bar (light or dark)."""
    pixmap = QIcon(svg_path).pixmap(QSize(_ICON_POINTS * 2, _ICON_POINTS * 2))
    raw = QByteArray()
    buffer = QBuffer(raw)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    png = bytes(raw)
    image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(png, len(png)))
    image.setSize_((_ICON_POINTS, _ICON_POINTS))
    image.setTemplate_(True)
    return image
