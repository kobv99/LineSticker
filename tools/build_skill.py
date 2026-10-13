#!/usr/bin/env python3
"""Deterministic, credential-free Claude .skill packaging from current source."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "line-character-studio"
OUTPUT = ROOT / "dist" / "line-character-studio.skill"
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".png", ".jpg", ".jpeg"}
BLOCKED_NAMES = {".env", ".git", "__pycache__", ".DS_Store"}


def archive_inputs(skill_dir: Path = SKILL) -> list[tuple[str, bytes]]:
    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError("SKILL.md missing")
    entries = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(skill_dir).parts
        if any(p in BLOCKED_NAMES or p.startswith(".") for p in parts):
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        arcname = (Path("line-character-studio") / path.relative_to(skill_dir)).as_posix()
        entries.append((arcname, path.read_bytes()))
    if (skill_dir.parent.parent / "LICENSE").is_file():
        entries.append(("line-character-studio/LICENSE", (skill_dir.parent.parent / "LICENSE").read_bytes()))
    return sorted(entries)


def build(output: Path = OUTPUT, skill_dir: Path = SKILL) -> Path:
    entries = archive_inputs(skill_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt packaged skill")
        names = archive.namelist()
        if "line-character-studio/SKILL.md" not in names:
            raise ValueError("Missing SKILL.md in output")
        if any("/.env" in name or "__pycache__" in name for name in names):
            raise ValueError("Credential or cache file leaked into skill archive")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.output)
    print(f"Built and verified {result} ({result.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
