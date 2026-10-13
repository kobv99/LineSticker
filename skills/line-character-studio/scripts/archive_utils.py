"""Safe, flat and atomically published LINE ZIP archives."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import zipfile


def write_flat_zip(files: list[Path], output: Path, max_bytes: int | None = None) -> None:
    output = Path(output)
    filenames = [p.name for p in files]
    if len(filenames) != len(set(filenames)) or any(not p.is_file() for p in files):
        raise ValueError("ZIP inputs must exist and have unique flat filenames")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".line-studio-", suffix=".zip", dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, arcname=path.name)
        if max_bytes is not None and os.path.getsize(temporary) > max_bytes:
            raise ValueError(f"ZIP exceeds {max_bytes} bytes")
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
