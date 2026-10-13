#!/usr/bin/env python3
"""Verify and store the OpenAI API key entered ONLY in the user's own terminal.

Use --check to validate existing environment or local key. Never paste a key into chat.
On POSIX, temporary and destination credentials are written with mode 0600.
On Windows filesystem permissions must be managed through account/OS ACLs.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request

ENV = Path(__file__).resolve().parent.parent / ".env"


def stored_key() -> str | None:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def verify(key: str) -> tuple[bool, str]:
    req = urllib.request.Request("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            models = json.load(response).get("data", [])
        image_models = sorted(model["id"] for model in models if model.get("id", "").startswith("gpt-image"))
        return True, f"key accepted; image models listed: {', '.join(image_models) or 'none'}"
    except urllib.error.HTTPError as exc:
        return False, f"OpenAI rejected the key (HTTP {exc.code})"
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, "could not reach OpenAI to verify the key"


def save_local_key(key: str, destination: Path = ENV) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".line-studio-key-", dir=destination.parent)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(f"OPENAI_API_KEY={key}\n")
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verify existing credentials")
    args = parser.parse_args()
    if args.check:
        key = stored_key()
        if not key:
            parser.exit(1, "NO KEY STORED\n")
    else:
        if not os.isatty(0):
            parser.exit(2, "Credential setup requires an interactive local terminal\n")
        key = getpass.getpass("OpenAI API key (hidden input): ").strip()
        if not key.startswith("sk-"):
            parser.exit(2, "Invalid key format; nothing saved\n")
    ok, status = verify(key)
    if not ok:
        parser.exit(1, f"Not saved: {status}\n")
    if args.check:
        print(status)
    else:
        save_local_key(key)
        print(f"Key saved locally at {ENV}; {status}")
        if os.name == "nt":
            print("On Windows, ensure your account ACL restricts access to the .env file.")


if __name__ == "__main__":
    main()
