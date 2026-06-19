"""Shared visual theme — the dark glass + blue accent look from the website.

Keeping the palette in one place lets the editor frame, toolbar, OCR panel,
overlay, and settings all share the same identity (and makes re-tinting a
one-line change).
"""
from __future__ import annotations

# Brand accent (the blue used across the site and app chrome).
ACCENT = "#4f7dff"
ACCENT_RGB = (79, 125, 255)

# Surfaces (dark glass): deepest background → raised panel → hover.
BG = "#0b0b0e"
SURFACE = "#101013"
SURFACE_RAISED = "#161619"
BORDER = "rgba(255, 255, 255, 0.08)"
BORDER_SOFT = "rgba(255, 255, 255, 0.06)"

# Text.
TEXT = "#f4f4f6"
TEXT_MUTED = "#9a9aa2"
TEXT_DIM = "#6f6f78"

# Feedback.
SUCCESS = "#5fcf80"

# Annotation quick-colors (mirrors the site's swatch row): white, blue, red,
# yellow, green — plus a few extras for the full palette.
QUICK_COLORS = ["#f4f4f6", ACCENT, "#ff5c5c", "#ffd23f", "#38d39f"]
EXTRA_COLORS = ["#ff9f43", "#af52de", "#1a1a1e"]
DEFAULT_COLOR = "#ff5c5c"  # red reads well over most screenshots
