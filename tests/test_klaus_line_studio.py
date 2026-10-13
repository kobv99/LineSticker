"""Klaus bridge: security gates, command contracts, and JSON output."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from tools import klaus_line_studio as bridge


def test_doctor_is_offline_and_returns_capabilities(monkeypatch, capsys):
    def must_not_run(*args, **kwargs):
        raise AssertionError("doctor must not spawn a process")
    monkeypatch.setattr(bridge.subprocess, "run", must_not_run)
    assert bridge.main(["doctor"]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["ok"] and response["action"] == "doctor"
    assert response["api_key_verified"] is False
    assert "dependencies" in response and "thai_shaping_available" in response


def test_paid_generation_is_blocked_without_approval(tmp_path, monkeypatch, capsys):
    prompts = tmp_path / "prompts.json"
    prompts.write_text('{"hello":"hello mascot"}', encoding="utf-8")
    monkeypatch.setattr(bridge.subprocess, "run",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("billable process started")))
    code = bridge.main(["generate", "--prompts", str(prompts), "--out", str(tmp_path / "out")])
    response = json.loads(capsys.readouterr().out)
    assert code == 2 and not response["ok"]
    assert "--approve-cost" in response["error"]


def test_generate_dry_run_never_calls_api(tmp_path, monkeypatch, capsys):
    prompts = tmp_path / "prompts.json"
    prompts.write_text('{"hello":"paint a star"}', encoding="utf-8")
    monkeypatch.setattr(bridge.subprocess, "run",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("process started")))
    assert bridge.main(["generate", "--prompts", str(prompts), "--out", str(tmp_path / "out"),
                        "--n", "2", "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] and result["inputs"]["image_count_per_prompt"] == 2
    assert "No network" in result["note"]


def test_paid_generation_uses_arg_list_and_user_approval(tmp_path, monkeypatch, capsys):
    prompts = tmp_path / "prompts.json"
    prompts.write_text('{"hello":"paint a star"}', encoding="utf-8")
    commands = []
    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="OK generated", stderr="")
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    assert bridge.main(["generate", "--prompts", str(prompts), "--out", str(tmp_path / "out"),
                        "--approve-cost", "--workers", "2"]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["ok"]
    argv, options = commands[0]
    assert options["shell"] is False
    assert "gen_images.py" in argv[1]
    assert "--approve-cost" not in argv
    assert "--workers" in argv
    assert "OK generated" in response["stdout"]


def test_sticker_packaging_argument_contract(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(bridge.subprocess, "run",
                        lambda argv, **kw: (calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", "")))
    src, out, zip_file = (tmp_path / part for part in ("build", "final", "upload.zip"))
    assert bridge.main(["pack-stickers", "--source", str(src), "--out-dir", str(out),
                        "--zip", str(zip_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert calls[0][-3:] == [str(src), str(out), str(zip_file)]
    assert str(zip_file) in result["outputs"]


def test_errors_preserve_exit_code_and_redact_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SUPERSECRET998877665544")
    monkeypatch.setattr(bridge.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(
                            argv, 17, "", "error: sk-SUPERSECRET998877665544"))
    result_code = bridge.main(["pack-theme", "--source", str(tmp_path / "theme"),
                               "--zip", str(tmp_path / "theme.zip")])
    result = json.loads(capsys.readouterr().out)
    assert result_code == 17 and not result["ok"]
    assert result["stderr"].count("[REDACTED]") == 1
    assert "SUPERSECRET" not in json.dumps(result)


def test_generation_with_missing_prompts_never_starts_process(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bridge.subprocess, "run",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("process started")))
    code = bridge.main(["generate", "--prompts", str(tmp_path / "absent.json"),
                        "--out", str(tmp_path / "out"), "--approve-cost"])
    result = json.loads(capsys.readouterr().out)
    assert code == 2 and "prompts file not found" in result["error"]


def test_preview_stickers_runs_with_platform_font(tmp_path):
    import sys
    from PIL import Image, ImageDraw
    script_dir = bridge.SCRIPTS
    sys.path.insert(0, str(script_dir))
    from sticker_preview import main as preview
    src = tmp_path / "stickers"
    src.mkdir()
    im = Image.new("RGBA", (150, 120), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((20, 20, 100, 100), fill="red")
    im.save(src / "01.png")
    output = tmp_path / "preview.png"
    preview(src, output, "dark")
    with Image.open(output) as final:
        assert final.width > 0 and final.height > 0


def test_real_bridge_sticker_zip_without_api(tmp_path, capsys):
    from PIL import Image, ImageDraw
    from zipfile import ZipFile
    src = tmp_path / "art"
    src.mkdir()
    for index in range(1, 9):
        image = Image.new("RGBA", (370, 320))
        ImageDraw.Draw(image).rectangle((60, 60, 180, 180), fill=(255, 10, 10, 255))
        image.save(src / f"{index:02d}.png")
    for name, size in (("main.png", (240, 240)), ("tab.png", (96, 74))):
        image = Image.new("RGBA", size)
        ImageDraw.Draw(image).ellipse((10, 10, 50, 50), fill=(0, 120, 200, 255))
        image.save(src / name)
    archive = tmp_path / "upload.zip"
    final = tmp_path / "final"
    assert bridge.main(["pack-stickers", "--source", str(src), "--out-dir", str(final),
                        "--zip", str(archive)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] and archive.is_file()
    with ZipFile(archive) as package:
        assert len(package.namelist()) == 10
        assert "main.png" in package.namelist()
        assert "08.png" in package.namelist()
