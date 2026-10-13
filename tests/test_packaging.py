import importlib.util
from pathlib import Path
import zipfile
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "skills/line-character-studio/scripts/finalize_line.py"
spec = importlib.util.spec_from_file_location("finalize_line", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def png(path, size=(370, 320), valid=True):
    im = Image.new("RGBA", size)
    if valid:
        ImageDraw.Draw(im).rectangle((30, 30, min(100, size[0]-30), min(100, size[1]-30)), fill="red")
    im.save(path)

def fixture(tmp_path, count=8):
    src = tmp_path / "source"
    src.mkdir()
    for n in range(1, count + 1):
        png(src / f"{n:02d}.png")
    png(src / "main.png", (240, 240))
    png(src / "tab.png", (96, 74))
    return src, tmp_path / "out", tmp_path / "upload.zip"

def test_valid_zip(tmp_path):
    src, dest, z = fixture(tmp_path)
    mod.main(src, dest, z)
    with zipfile.ZipFile(z) as package:
        assert sorted(package.namelist()) == sorted([f"{n:02d}.png" for n in range(1, 9)] + ["main.png", "tab.png"])

def test_invalid_count(tmp_path):
    src, dest, z = fixture(tmp_path, 10)
    with pytest.raises(ValueError, match="invalid sticker count"):
        mod.main(src, dest, z)
    assert not z.exists()

def test_missing_number(tmp_path):
    src, dest, z = fixture(tmp_path)
    (src / "03.png").rename(src / "09.png")
    with pytest.raises(ValueError, match="numbering"):
        mod.main(src, dest, z)
    assert not z.exists()

def test_blank_alpha(tmp_path):
    src, dest, z = fixture(tmp_path)
    png(src / "02.png", valid=False)
    with pytest.raises(ValueError, match="blank sticker"):
        mod.main(src, dest, z)
    assert not z.exists()

def test_bad_main(tmp_path):
    src, dest, z = fixture(tmp_path)
    png(src / "main.png", (220, 220))
    with pytest.raises(ValueError, match="Validation failed"):
        mod.main(src, dest, z)
    assert not z.exists()
