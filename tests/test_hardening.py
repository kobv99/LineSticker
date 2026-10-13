"""Regression tests for packaging, image handling, model retries and credential policy."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import sys
import urllib.error
import zipfile

import pytest
from PIL import Image, ImageDraw

import archive_utils
import clean_png
import finalize_theme
import font_utils
import gen_images
import make_emoji
from tools import build_skill


def test_clean_rejects_invisible_png(tmp_path):
    art = tmp_path / "empty.png"
    Image.new("RGBA", (30, 30), (255, 255, 255, 0)).save(art)
    with pytest.raises(ValueError, match="no visible pixels"):
        clean_png.clean(art, tmp_path / "out")
    assert not (tmp_path / "out" / art.name).exists()


def test_clean_rejects_bad_cut_bottom(tmp_path):
    art = tmp_path / "art.png"
    Image.new("RGBA", (30, 30), "red").save(art)
    with pytest.raises(ValueError, match="cut_bottom"):
        clean_png.clean(art, tmp_path / "out", -1)


def test_clean_writes_trimmed_png(tmp_path):
    art = tmp_path / "art.png"
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((95, 95, 105, 105), fill=(20, 30, 40, 255))
    im.save(art)
    clean_png.clean(art, tmp_path / "out")
    out = Image.open(tmp_path / "out" / "art.png")
    assert out.width < 200 and out.height < 200


def test_archive_limit_and_atomic_replace(tmp_path):
    art = tmp_path / "01.png"
    art.write_bytes(b"something to zip")
    output = tmp_path / "package.zip"
    output.write_bytes(b"original")
    with pytest.raises(ValueError, match="ZIP exceeds"):
        archive_utils.write_flat_zip([art], output, max_bytes=50)
    assert output.read_bytes() == b"original"


def test_theme_valid_zip_and_exact_count(tmp_path):
    theme = tmp_path / "theme"
    theme.mkdir()
    for name, dims in finalize_theme.EXPECTED.items():
        Image.new("RGB", dims, "white").save(theme / name)
    assert len(finalize_theme.EXPECTED) == 62
    archive = tmp_path / "theme.zip"
    finalize_theme.main(str(theme), str(archive))
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == set(finalize_theme.EXPECTED)
    Image.new("RGB", (4, 4)).save(theme / "extra.png")
    with pytest.raises(SystemExit):
        finalize_theme.main(str(theme), str(tmp_path / "invalid.zip"))
    assert not (tmp_path / "invalid.zip").exists()


def test_theme_opaque_check_catches_palette_transparency(tmp_path):
    art = tmp_path / "ios_thumbnail.png"
    im = Image.new("P", (200, 284))
    im.putpalette([255, 255, 255] * 256)
    im.save(art, transparency=0)
    assert "has transparency" in finalize_theme.check(art, (200, 284))


@pytest.mark.parametrize("size,color", [((179, 180), (255, 0, 0, 255)),
                                        ((180, 180), (255, 0, 0, 255)),
                                        ((180, 180), (0, 0, 0, 0))])
def test_emoji_validation_rejects_invalid_outputs(tmp_path, size, color):
    art = tmp_path / "001.png"
    Image.new("RGBA", size, color).save(art)
    with pytest.raises(ValueError):
        make_emoji.validate_emoji_image(art)


def test_emoji_packaging_and_preview(tmp_path, monkeypatch):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    for n in range(8):
        Image.new("RGBA", (40, 40), "red").save(src / f"emo-test{n}.png")
    def fake_place(art, canvas, box, border=0):
        im = Image.new("RGBA", canvas)
        ImageDraw.Draw(im).rectangle((5, 5, 25, 25), fill="red")
        return im
    monkeypatch.setattr(make_emoji, "place", fake_place)
    archive, preview = tmp_path / "emoji.zip", tmp_path / "preview.png"
    make_emoji.main(src, out, archive, preview)
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == 9
        assert "001.png" in z.namelist() and "tab.png" in z.namelist()
    assert preview.is_file()


def test_prompt_names_cannot_escape_output(tmp_path):
    prompt_file = tmp_path / "prompts.json"
    prompt_file.write_text(json.dumps({"../secret": "paint a star"}), encoding="utf-8")
    with pytest.raises(ValueError, match="filename"):
        gen_images.load_prompts(str(prompt_file))


def test_retry_429_then_success(monkeypatch):
    attempts = []
    def fake_urlopen(req, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate limited",
                                         {"Retry-After": "0"},
                                         io.BytesIO(b'{"error":{"code":"rate_limit_exceeded"}}'))
        return io.BytesIO(b'{"data":[{"b64_json":"ok"}]}')
    monkeypatch.setattr(gen_images.urllib.request, "urlopen", fake_urlopen)
    sleeps = []
    result = gen_images.request_json(urllib.request.Request("https://example.invalid/"),
                                     attempts=3, sleep=sleeps.append)
    assert len(attempts) == 2 and sleeps == [0.0] and result["data"]


def test_retry_never_retries_quota(monkeypatch):
    attempts = []
    def denied(req, timeout):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 429, "quota", {},
                                     io.BytesIO(b'{"error":{"code":"insufficient_quota"}}'))
    monkeypatch.setattr(gen_images.urllib.request, "urlopen", denied)
    with pytest.raises(RuntimeError, match="insufficient_quota"):
        gen_images.request_json(urllib.request.Request("https://example.invalid/"),
                                attempts=4, sleep=lambda _: None)
    assert len(attempts) == 1


def test_save_png_rejects_bad_data_without_overwriting(tmp_path):
    dst = tmp_path / "image.png"
    dst.write_bytes(b"known old version")
    with pytest.raises(Exception):
        gen_images.save_png(dst, base64.b64encode(b"not a PNG").decode())
    assert dst.read_bytes() == b"known old version"


def test_thai_shaping_and_glyph_support(tmp_path, monkeypatch):
    font = tmp_path / "thai.ttf"
    font.write_bytes(b"fake font file used for candidate testing")
    monkeypatch.setenv("LINE_STUDIO_FONT", str(font))
    monkeypatch.setattr(font_utils.features, "check", lambda _: False)
    with pytest.raises(RuntimeError, match="libraqm"):
        font_utils.resolve_font_for_text("ก")
    monkeypatch.setattr(font_utils.features, "check", lambda _: True)
    monkeypatch.setattr(font_utils, "font_codepoints", lambda path, index=0: frozenset({ord("ก")}))
    assert font_utils.resolve_font_for_text("ก")[0] == str(font)
    with pytest.raises(ValueError, match="glyphs"):
        font_utils.resolve_font_for_text("ข")


def test_skill_archive_excludes_secrets_and_is_deterministic(tmp_path):
    skill = tmp_path / "skills" / "line-character-studio"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Skill", encoding="utf-8")
    (skill / "run.py").write_text("print('ok')", encoding="utf-8")
    (skill / ".env").write_text("OPENAI_API_KEY=SECRET", encoding="utf-8")
    (skill / "__pycache__").mkdir()
    (skill / "__pycache__" / "oops.py").write_text("bad", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    first, second = tmp_path / "first.skill", tmp_path / "second.skill"
    build_skill.build(first, skill)
    build_skill.build(second, skill)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert "line-character-studio/SKILL.md" in names
        assert "line-character-studio/LICENSE" in names
        assert not any("env" in n or "__pycache__" in n for n in names)
