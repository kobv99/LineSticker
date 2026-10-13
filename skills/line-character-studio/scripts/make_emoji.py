#!/usr/bin/env python3
"""LINE emoji set: 180x180 transparent PNGs named 001.png..., plus tab.png (96x74), and a flat ZIP.

Usage: make_emoji.py SRC_DIR OUT_DIR ZIP_PATH PREVIEW.png
SRC_DIR: trimmed transparent head-*.png / emo-*.png. Files named in ORDER come first (most-used first),
any other head-*/emo-* files follow alphabetically. LINE allows 8-40 emoji per set.
"""
import sys
from archive_utils import write_flat_zip
from pathlib import Path

from PIL import Image, ImageDraw

from make_theme import place, trim

# most-used first (LINE: "order your emoji with your most frequently used emoji near the top")
ORDER = ["head-happy", "head-laughing", "emo-love", "emo-thumbs", "emo-ok", "emo-wai", "emo-cry", "head-wink",
         "emo-blush", "emo-sweat", "head-surprised", "emo-shocked", "emo-thinking", "emo-angry", "emo-wave",
         "emo-kiss", "emo-stars", "emo-party", "emo-cool", "emo-tongue", "emo-sleepy", "emo-dizzy", "emo-sick",
         "emo-facepalm"]


def validate_emoji_image(path: Path, tab: bool = False) -> None:
    """Validate output independently of Python optimization flags."""
    with Image.open(path) as im:
        want = (96, 74) if tab else (180, 180)
        if im.format != "PNG" or im.size != want or im.mode != "RGBA":
            raise ValueError(f"{path.name}: expected RGBA PNG {want}, got {im.mode} {im.size}")
        minimum, maximum = im.getchannel("A").getextrema()
        if minimum != 0 or maximum == 0:
            raise ValueError(f"{path.name}: must have artwork and transparent pixels")
    if path.stat().st_size > 1_000_000:
        raise ValueError(f"{path.name}: exceeds 1 MB")


def main(src, out, zip_path, preview):
    src, out = Path(src), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stems = [s for s in ORDER if (src / f"{s}.png").exists()]
    stems += sorted(p.stem for p in src.glob("*.png") if p.stem.startswith(("head-", "emo-")) and p.stem not in stems)
    if not 8 <= len(stems) <= 40:
        sys.exit(f"LINE emoji sets need 8-40 images, found {len(stems)}")
    names = []
    for i, stem in enumerate(stems, 1):
        art = trim(Image.open(src / f"{stem}.png").convert("RGBA"))
        # LINE recommends no margins: art fills the square, 3px white edge keeps it visible on dark chats
        place(art, (180, 180), (0, 0, 180, 180), border=3).save(out / f"{i:03d}.png", optimize=True)
        names.append(f"{i:03d}.png")
    tab_src = src / "head-happy.png" if (src / "head-happy.png").exists() else src / f"{stems[0]}.png"
    tab = trim(Image.open(tab_src).convert("RGBA"))
    place(tab, (96, 74), (0, 0, 96, 74), border=2).save(out / "tab.png", optimize=True)
    names.append("tab.png")
    for n in names:
        validate_emoji_image(out / n, tab=n == "tab.png")
    write_flat_zip([out / n for n in names], Path(zip_path), max_bytes=19_999_999)
    # preview: grid at full size on light + dark, plus a mock message with inline emoji
    cols, cell = 8, 196
    rows = (len(stems) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell * 2 + 60, rows * cell + 170), (243, 245, 249))
    for half, bg in enumerate([(140, 171, 216), (30, 30, 30)]):
        x0 = 20 + half * (cols * cell + 20)
        ImageDraw.Draw(sheet).rectangle((x0, 20, x0 + cols * cell, 20 + rows * cell), fill=bg)
        for i in range(len(stems)):
            e = Image.open(out / f"{i + 1:03d}.png")
            sheet.paste(e, (x0 + (i % cols) * cell + 8, 28 + (i // cols) * cell), e)
    y = rows * cell + 50
    d = ImageDraw.Draw(sheet)
    d.rounded_rectangle((20, y, 900, y + 100), 40, fill=(255, 255, 255))
    x = 50
    font = __import__("theme_preview").F(34)
    for part in ["See you soon", 1, 4, " thanks", 6, 3]:
        if isinstance(part, int):
            e = Image.open(out / f"{part:03d}.png").resize((64, 64), Image.LANCZOS)
            sheet.paste(e, (x, y + 18), e)
            x += 66
        else:
            d.text((x, y + 50), part, font=font, fill=(20, 24, 33), anchor="lm")
            x += int(d.textlength(part, font=font)) + 8
    sheet.save(preview, optimize=True)
    print(len(names), "files ->", zip_path)


if __name__ == "__main__":
    main(*sys.argv[1:5])
