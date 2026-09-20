from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx

from bootstrap.pins import RAPIDOCR_MODELS

_RETRY_STATUSES = {429, 500, 502, 503, 504}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    dest: Path,
    sha256: str | None = None,
    timeout: float = 120.0,
    *,
    retries: int = 5,
    client: httpx.Client | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (sha256 is None or sha256_file(dest) == sha256):
        print(f"reuse {dest.name}")
        return dest
    print(f"download {url}")
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    delay = 2.0
    last_error: Exception | None = None
    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        for attempt in range(max(retries, 1)):
            retry_after = False
            retry_status = 0
            try:
                with http.stream("GET", url) as response:
                    if response.status_code in _RETRY_STATUSES:
                        last_error = httpx.HTTPStatusError(
                            f"{response.status_code} {url}",
                            request=response.request,
                            response=response,
                        )
                        response.read()
                        retry_after = True
                        retry_status = response.status_code
                    else:
                        response.raise_for_status()
                        with tmp.open("wb") as handle:
                            for chunk in response.iter_bytes():
                                handle.write(chunk)
                if retry_after:
                    print(f"  retry {retry_status} {dest.name} ({attempt + 1}/{retries})")
                    time.sleep(delay)
                    delay = min(delay * 2, 32)
                    continue
                tmp.replace(dest)
                if sha256 and sha256_file(dest) != sha256:
                    dest.unlink(missing_ok=True)
                    raise RuntimeError(f"Checksum mismatch for {dest.name}")
                return dest
            except httpx.RequestError as exc:
                last_error = exc
                print(f"  retry {exc.__class__.__name__} {dest.name} ({attempt + 1}/{retries})")
                time.sleep(delay)
                delay = min(delay * 2, 32)
            finally:
                tmp.unlink(missing_ok=True)
        raise last_error or RuntimeError(f"Failed to download {url}")
    finally:
        if owns_client:
            http.close()


def download_rapidocr(models_dir: Path) -> None:
    for name, meta in RAPIDOCR_MODELS.items():
        download_file(meta["url"], models_dir / name, meta["sha256"])
