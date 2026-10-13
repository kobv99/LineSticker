"""Cross-platform font discovery and glyph/shaping preflight for sticker captions."""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from PIL import features

CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Thonburi.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "C:/Windows/Fonts/tahomabd.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


@lru_cache(maxsize=64)
def font_codepoints(path: str, index: int = 0) -> frozenset[int]:
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise RuntimeError("Install fonttools (pip install -r requirements.txt) for Thai glyph checks") from exc
    font = TTFont(path, fontNumber=index, lazy=True)
    try:
        return frozenset(font.getBestCmap() or {})
    finally:
        font.close()


def resolve_font_for_text(text: str = "") -> tuple[str, int]:
    """Return (font path, collection index); never silently replace a requested font."""
    needs_thai = any("\u0e00" <= char <= "\u0e7f" for char in text)
    if needs_thai and not features.check("raqm"):
        raise RuntimeError("Thai captions need Pillow compiled with libraqm/HarfBuzz shaping")

    explicit = os.environ.get("LINE_STUDIO_FONT")
    paths = [explicit] if explicit else CANDIDATES
    require_glyphs = needs_thai or any(ord(ch) > 127 for ch in text)
    needed = {ord(ch) for ch in text if not ch.isspace()} if require_glyphs else set()
    for candidate in paths:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.is_file():
            continue
        if needed and not needed.issubset(font_codepoints(str(path))):
            continue
        return str(path), 0

    if explicit:
        raise ValueError("LINE_STUDIO_FONT is unavailable or lacks required glyphs; choose a compatible licensed font")
    raise FileNotFoundError("No installed font supports this text; set LINE_STUDIO_FONT to a licensed font")
