from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from bootstrap.pins import RAPIDOCR_MODELS


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, dest: Path, sha256: str | None = None, timeout: float = 120.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (sha256 is None or sha256_file(dest) == sha256):
        print(f"reuse {dest.name}")
        return dest
    print(f"download {url}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
        response.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".partial")
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
        tmp.replace(dest)
    if sha256 and sha256_file(dest) != sha256:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {dest.name}")
    return dest


def download_rapidocr(models_dir: Path) -> None:
    for name, meta in RAPIDOCR_MODELS.items():
        download_file(meta["url"], models_dir / name, meta["sha256"])
