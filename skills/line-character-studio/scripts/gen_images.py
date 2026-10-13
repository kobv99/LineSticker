#!/usr/bin/env python3
"""Generate images using OpenAI Images API with bounded retry and safe local outputs.

Usage:
    python gen_images.py --prompts prompts.json --out output/
    python gen_images.py --prompts prompts.json --out output/ --image reference.png

Credentials: OPENAI_API_KEY or local .env created by set_api_key.py.
Never pass credentials through CLI arguments or chat.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import io
import json
import mimetypes
import os
from pathlib import Path
import random
import re
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from PIL import Image

SKILL_DIR = Path(__file__).resolve().parent.parent
VALID_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def resolve_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    env = SKILL_DIR / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.partition("=")[2].strip().strip('"').strip("'")
    raise RuntimeError("No API key. Run scripts/set_api_key.py in your own local terminal.")


def load_prompts(path: str) -> list[tuple[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        entries = list(data.items())
    elif isinstance(data, list):
        entries = [(item["name"], item["prompt"]) for item in data]
    else:
        raise ValueError("prompts JSON must be an object or list")
    if not entries:
        raise ValueError("prompt list is empty")
    seen = set()
    for name, prompt in entries:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name):
            raise ValueError("prompt names must be safe filename stems (ASCII letters, digits, _, -, .)")
        if name.lower() in seen:
            raise ValueError(f"duplicate output name: {name}")
        seen.add(name.lower())
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"empty prompt: {name}")
    return entries


def request_json(request: urllib.request.Request, *, attempts: int = MAX_ATTEMPTS,
                 sleep=time.sleep) -> dict:
    """Retry only rate limits/transient HTTP failures. No retries on billing/auth errors.

    POST retries can be billed twice if a server accepted a request but failed afterwards;
    the caller should keep generation concurrency modest.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read(4096)
            try:
                details = json.loads(body).get("error") or {}
                code = details.get("code") or details.get("type") or "unknown_error"
            except (ValueError, AttributeError, TypeError):
                code = "unknown_error"
            code = str(code)[:100]
            if (exc.code not in RETRYABLE_STATUS or
                code in {"insufficient_quota", "billing_hard_limit_reached"} or
                attempt == attempts - 1):
                raise RuntimeError(f"Images API HTTP {exc.code} ({code})") from None
            retry_after = (exc.headers or {}).get("Retry-After")
            try:
                delay = max(0.0, min(60.0, float(retry_after)))
            except (TypeError, ValueError):
                delay = min(30.0, (2 ** attempt) + random.random())
            sleep(delay)
    raise RuntimeError("unreachable retry state")


def post_json(url: str, payload: dict, key: str) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
    return request_json(request)


def post_multipart(url: str, fields: dict, files: list[tuple[str, str]], key: str) -> dict:
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, path in files:
        file = Path(path)
        media_type = mimetypes.guess_type(file.name)[0] or "image/png"
        safe_name = file.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                       f'filename="{safe_name}"\r\nContent-Type: {media_type}\r\n\r\n').encode()
                      + file.read_bytes() + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(url, data=b"".join(chunks),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return request_json(request)


def save_png(destination: Path, data: str) -> None:
    raw = base64.b64decode(data, validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG":
            raise ValueError("Images API did not return a PNG")
        image.verify()
    fd, temporary = tempfile.mkstemp(prefix=".image-", suffix=".png", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run_one(name: str, prompt: str, options: argparse.Namespace, key: str) -> str:
    try:
        if options.image:
            fields = {"model": options.model, "prompt": prompt, "size": options.size,
                      "quality": options.quality, "n": str(options.n)}
            if options.background:
                fields["background"] = options.background
            files = ([("image[]", path) for path in options.image] if len(options.image) > 1
                     else [("image", options.image[0])])
            if options.mask:
                files.append(("mask", options.mask))
            result = post_multipart("https://api.openai.com/v1/images/edits", fields, files, key)
        else:
            payload = {"model": options.model, "prompt": prompt, "size": options.size,
                       "quality": options.quality, "n": options.n}
            if options.background:
                payload["background"] = options.background
            result = post_json("https://api.openai.com/v1/images/generations", payload, key)
        images = result.get("data", [])
        if len(images) != options.n:
            raise ValueError(f"expected {options.n} images, received {len(images)}")
        outputs = []
        for index, image in enumerate(images):
            suffix = "" if options.n == 1 else f"_{index + 1}"
            destination = Path(options.out) / f"{name}{suffix}.png"
            save_png(destination, image["b64_json"])
            outputs.append(str(destination))
        return "OK   " + ", ".join(outputs)
    except Exception as exc:
        # Never print the API key or request headers in error output.
        details = str(exc).replace(key, "[REDACTED]")
        return f"ERR  {name}: {details}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--mask")
    parser.add_argument("--base", default="")
    parser.add_argument("--model", default=os.environ.get("LINE_STUDIO_IMAGE_MODEL", "gpt-image-2"))
    parser.add_argument("--size", default="1024x1024", choices=sorted(VALID_SIZES))
    parser.add_argument("--quality", default="high", choices=["low", "medium", "high", "auto"])
    parser.add_argument("--background", choices=["transparent", "opaque", "auto"])
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    if not (1 <= options.n <= 10 and 1 <= options.workers <= 16):
        parser.error("--n must be 1..10 and --workers must be 1..16")
    if options.mask and not options.image:
        parser.error("--mask requires --image")
    try:
        prompts = load_prompts(options.prompts)
        key = resolve_key()
        Path(options.out).mkdir(parents=True, exist_ok=True)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.error(str(exc))
    print(f"{len(prompts)} prompt(s) -> {options.out} "
          f"[{options.model} {options.size} {options.quality}]")
    failures = 0
    with cf.ThreadPoolExecutor(max_workers=options.workers) as executor:
        jobs = [executor.submit(run_one, name, options.base + prompt, options, key)
                for name, prompt in prompts]
        for job in cf.as_completed(jobs):
            line = job.result()
            failures += line.startswith("ERR")
            print(line, flush=True)
    if failures:
        parser.exit(1, f"{failures} of {len(prompts)} generation requests failed\n")


if __name__ == "__main__":
    main()
