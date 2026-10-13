#!/usr/bin/env python3
"""Klaus MCP shell bridge. Emits JSON and delegates to existing local scripts.

This is not a separately registered MCP server or tool. The Klaus MCP shell
is the host-side transport. No shell interpolation is used.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "line-character-studio" / "scripts"
BUILD = ROOT / "tools" / "build_skill.py"
SCRIPT = {
    "generate": "gen_images.py",
    "clean": "clean_png.py",
    "compose-stickers": "make_stickers.py",
    "pack-stickers": "finalize_line.py",
    "preview-stickers": "sticker_preview.py",
    "build-theme": "make_theme.py",
    "pack-theme": "finalize_theme.py",
    "preview-theme": "theme_preview.py",
    "make-emoji": "make_emoji.py",
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="LineSticker bridge for Klaus MCP shell; emits JSON.")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("doctor", help="Check runtime, dependencies and key presence without API calls")
    gen = sub.add_parser("generate", help="Billable OpenAI image generation")
    gen.add_argument("--prompts", type=Path, required=True)
    gen.add_argument("--out", type=Path, required=True)
    gen.add_argument("--image", type=Path, action="append", default=[])
    gen.add_argument("--mask", type=Path)
    gen.add_argument("--size", choices=["1024x1024", "1024x1536", "1536x1024", "auto"], default="1024x1024")
    gen.add_argument("--quality", choices=["low", "medium", "high", "auto"], default="high")
    gen.add_argument("--background", choices=["transparent", "opaque", "auto"])
    gen.add_argument("--n", type=int, default=1)
    gen.add_argument("--workers", type=int, default=4)
    gen.add_argument("--model")
    gen.add_argument("--approve-cost", action="store_true",
                     help="Only after explicit user approval for this paid batch")
    gen.add_argument("--dry-run", action="store_true", help="Preview without billing")
    clean = sub.add_parser("clean")
    clean.add_argument("--out", type=Path, required=True)
    clean.add_argument("--images", type=Path, nargs="+", required=True)
    clean.add_argument("--cut-bottom", type=int)
    compose = sub.add_parser("compose-stickers")
    compose.add_argument("--spec", type=Path, required=True)
    compose.add_argument("--out", type=Path, required=True)
    pack = sub.add_parser("pack-stickers")
    pack.add_argument("--source", type=Path, required=True)
    pack.add_argument("--out-dir", type=Path, required=True)
    pack.add_argument("--zip", type=Path, required=True)
    preview = sub.add_parser("preview-stickers")
    preview.add_argument("--source", type=Path, required=True)
    preview.add_argument("--out", type=Path, required=True)
    preview.add_argument("--theme", choices=["light", "dark"], default="light")
    theme = sub.add_parser("build-theme")
    theme.add_argument("--source", type=Path, required=True)
    theme.add_argument("--out-dir", type=Path, required=True)
    theme.add_argument("--primary")
    theme.add_argument("--secondary")
    tp = sub.add_parser("pack-theme")
    tp.add_argument("--source", type=Path, required=True)
    tp.add_argument("--zip", type=Path, required=True)
    pv = sub.add_parser("preview-theme")
    pv.add_argument("--source", type=Path, required=True)
    pv.add_argument("--out", type=Path, required=True)
    pv.add_argument("--name", default="Chat")
    emoji = sub.add_parser("make-emoji")
    emoji.add_argument("--source", type=Path, required=True)
    emoji.add_argument("--out-dir", type=Path, required=True)
    emoji.add_argument("--zip", type=Path, required=True)
    emoji.add_argument("--preview", type=Path, required=True)
    sub.add_parser("build-skill", help="Rebuild optional Claude-compatible skill")
    return p


def doctor() -> dict:
    deps = {"Pillow": "PIL", "numpy": "numpy", "scipy": "scipy", "fonttools": "fontTools"}
    installed = {k: importlib.util.find_spec(v) is not None for k, v in deps.items()}
    key_present = bool(os.environ.get("OPENAI_API_KEY"))
    if not key_present:
        key_present = (SCRIPTS.parent / ".env").is_file()
    shaping = None
    if installed["Pillow"]:
        from PIL import features
        shaping = bool(features.check("raqm"))
    return {
        "ok": True, "action": "doctor",
        "python": sys.version.split()[0],
        "python_supported": sys.version_info >= (3, 10),
        "dependencies": installed, "dependencies_ready": all(installed.values()),
        "api_key_configured": key_present, "api_key_verified": False,
        "thai_shaping_available": shaping, "project_root": str(ROOT),
        "supports": sorted([*SCRIPT, "doctor", "build-skill"]),
        "note": "Key presence does not prove API permissions or credits; no network was contacted.",
    }


def planned_command(a: argparse.Namespace) -> tuple[list[str], list[str]]:
    args: list[str]
    outputs: list[str] = []
    if a.action == "generate":
        if not a.prompts.is_file():
            raise ValueError("prompts file not found")
        if not 1 <= a.n <= 10 or not 1 <= a.workers <= 16:
            raise ValueError("--n must be 1..10 and --workers must be 1..16")
        args = ["--prompts", str(a.prompts), "--out", str(a.out),
                "--size", a.size, "--quality", a.quality, "--n", str(a.n),
                "--workers", str(a.workers)]
        for image in a.image:
            args += ["--image", str(image)]
        if a.mask:
            args += ["--mask", str(a.mask)]
        if a.background:
            args += ["--background", a.background]
        if a.model:
            args += ["--model", a.model]
        outputs = [str(a.out)]
    elif a.action == "clean":
        args = [str(a.out)] + [str(i) for i in a.images]
        if a.cut_bottom is not None:
            args += ["--cut-bottom", str(a.cut_bottom)]
        outputs = [str(a.out)]
    elif a.action == "compose-stickers":
        args = [str(a.spec), str(a.out)]
        outputs = [str(a.out)]
    elif a.action == "pack-stickers":
        args = [str(a.source), str(a.out_dir), str(a.zip)]
        outputs = [str(a.out_dir), str(a.zip)]
    elif a.action == "preview-stickers":
        args = [str(a.source), str(a.out), a.theme]
        outputs = [str(a.out)]
    elif a.action == "build-theme":
        args = [str(a.source), str(a.out_dir)]
        for flag in ("primary", "secondary"):
            if getattr(a, flag):
                args += ["--" + flag, getattr(a, flag)]
        outputs = [str(a.out_dir)]
    elif a.action == "pack-theme":
        args = [str(a.source), str(a.zip)]
        outputs = [str(a.zip)]
    elif a.action == "preview-theme":
        args = [str(a.source), str(a.out), a.name]
        outputs = [str(a.out)]
    elif a.action == "make-emoji":
        args = [str(a.source), str(a.out_dir), str(a.zip), str(a.preview)]
        outputs = [str(a.out_dir), str(a.zip), str(a.preview)]
    elif a.action == "build-skill":
        return [sys.executable, str(BUILD)], [str(ROOT / "dist" / "line-character-studio.skill")]
    else:
        raise ValueError("unrecognized action")
    return [sys.executable, str(SCRIPTS / SCRIPT[a.action]), *args], outputs


def safe_log(message: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        message = message.replace(key, "[REDACTED]")
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", message)[-12000:]


def execute(a: argparse.Namespace) -> dict:
    if a.action == "doctor":
        return doctor()
    if a.action == "generate" and not (a.approve_cost or a.dry_run):
        return {"ok": False, "action": a.action, "exit_code": 2,
                "error": "Paid generation blocked. Obtain explicit user approval for this batch, then use --approve-cost, or --dry-run without billing."}
    command, outputs = planned_command(a)
    if a.action == "generate" and a.dry_run:
        return {"ok": True, "action": a.action, "dry_run": True,
                "billable": True, "approved": a.approve_cost,
                "inputs": {"prompts": str(a.prompts), "reference_count": len(a.image),
                           "image_count_per_prompt": a.n, "workers": a.workers},
                "outputs": outputs, "note": "No network calls or image generation occurred."}
    result = subprocess.run(command, cwd=ROOT, shell=False, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", check=False)
    return {"ok": result.returncode == 0, "action": a.action,
            "exit_code": result.returncode, "outputs": outputs,
            "stdout": safe_log(result.stdout.strip()), "stderr": safe_log(result.stderr.strip())}


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        result = execute(a)
    except (ValueError, FileNotFoundError, OSError) as error:
        result = {"ok": False, "action": a.action, "exit_code": 2,
                  "error": safe_log(str(error))}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else result.get("exit_code", 1) or 1


if __name__ == "__main__":
    raise SystemExit(main())
