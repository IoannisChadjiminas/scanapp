"""Public card-art mirror: TCGdex artwork copied into an R2 bucket behind Cloudflare's CDN.

The catalogue keeps handing out TCGdex URLs until a card's art has been
uploaded; a mirrored card gets the same path on the CDN host, so clients that
swap ``high.webp`` for ``low.webp`` keep working. Only TCGdex art is mirrored:
Cardmarket product photos and locally supplied reference images stay where
they are. See docs/card-image-cdn.md.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

TCGDEX_ASSETS_HOST = "assets.tcgdex.net"
QUALITIES = ("high", "low")
# Card art never changes once published; let every cache keep it for a year.
CACHE_CONTROL = "public, max-age=31536000, immutable"
CONTENT_TYPE = "image/webp"
REGISTRY_RELOAD_SECONDS = 60.0

_QUALITY_FILES = frozenset(f"{quality}.webp" for quality in QUALITIES)


def mirror_object_base(remote_image_url: Any) -> str | None:
    """``en/sv/sv03.5/001`` for a TCGdex ``high.webp``/``low.webp`` URL, else None."""
    parts = urlsplit(str(remote_image_url or "").strip())
    if parts.scheme != "https" or parts.hostname != TCGDEX_ASSETS_HOST:
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 2 or segments[-1] not in _QUALITY_FILES:
        return None
    if any(segment in {".", ".."} for segment in segments):
        return None
    return "/".join(segments[:-1])


def tcgdex_source_url(object_base: str, quality: str) -> str:
    return f"https://{TCGDEX_ASSETS_HOST}/{object_base}/{quality}.webp"


def cdn_image_url(base_url: str, object_base: str, quality: str = "high") -> str:
    return f"{base_url.rstrip('/')}/{object_base}/{quality}.webp"


def is_webp(data: bytes) -> bool:
    return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


# --- registry -----------------------------------------------------------------
# A small sqlite file on the data volume records which cards are mirrored. The
# catalogue itself is read-only under the PlanetScale backend, so the record
# cannot live in the cards table.


def open_registry(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mirrored_images (
            card_id TEXT PRIMARY KEY,
            object_base TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def load_mirrored(path: Path) -> Mapping[str, str]:
    if not path.is_file():
        return MappingProxyType({})
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT card_id, object_base FROM mirrored_images").fetchall()
    except sqlite3.Error:
        return MappingProxyType({})
    finally:
        conn.close()
    return MappingProxyType({str(card_id): str(base) for card_id, base in rows})


class CardImageCdn:
    """Answers which public URL, if any, replaces a card's TCGdex URL.

    The registry is re-read when its file changes, checked at most once a
    minute, so a mirror run shows up without restarting the API.
    """

    def __init__(self, base_url: str, registry_path: Path, *, clock: Callable[[], float] = time.monotonic):
        self.base_url = str(base_url or "").strip().rstrip("/")
        self._path = Path(registry_path)
        self._clock = clock
        self._mirrored: Mapping[str, str] = MappingProxyType({})
        self._mtime: int | None = None
        self._checked: float | None = None
        self.refresh(force=True)

    @property
    def enabled(self) -> bool:
        return self.base_url.startswith("https://")

    def __len__(self) -> int:
        return len(self._mirrored)

    def refresh(self, *, force: bool = False) -> None:
        now = self._clock()
        if not force and self._checked is not None and now - self._checked < REGISTRY_RELOAD_SECONDS:
            return
        self._checked = now
        try:
            mtime: int | None = self._path.stat().st_mtime_ns
        except OSError:
            mtime = None
        if mtime == self._mtime and not force:
            return
        self._mtime = mtime
        self._mirrored = load_mirrored(self._path)

    def url_for(self, card_id: Any, remote_image_url: Any) -> str | None:
        if not self.enabled:
            return None
        self.refresh()
        base = self._mirrored.get(str(card_id))
        if base is None:
            return None
        # The catalogue moved this card's art since it was mirrored: the copy
        # is stale, so the live TCGdex file wins until the next mirror run.
        if mirror_object_base(remote_image_url) != base:
            return None
        quality = str(remote_image_url).rsplit("/", 1)[-1].removesuffix(".webp")
        return cdn_image_url(self.base_url, base, quality)


def load_card_image_cdn(settings: Any) -> CardImageCdn | None:
    base_url = str(getattr(settings, "card_image_cdn_base_url", "") or "").strip()
    if not base_url:
        return None
    return CardImageCdn(base_url, settings.card_image_mirror_sqlite)


# --- mirror job ---------------------------------------------------------------


class ObjectStore(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str, CacheControl: str) -> Any: ...


def r2_client(settings: Any) -> ObjectStore:
    """S3 client for the configured R2 bucket. boto3 is a runtime-only import."""
    r2 = settings.card_image_r2()
    if r2 is None:
        raise RuntimeError("CARD_IMAGE_R2_* is not configured")
    import boto3  # noqa: PLC0415  (only the mirror job needs it)

    return boto3.client(
        "s3",
        endpoint_url=f"https://{r2['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=r2["access_key_id"],
        aws_secret_access_key=r2["secret_access_key"],
        region_name="auto",
    )


class DryRunStore:
    """Counts what a real run would upload."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str, CacheControl: str) -> None:  # noqa: N803
        self.keys.append(Key)


def http_fetcher(client: Any, *, timeout: float = 60.0) -> Callable[[str], bytes]:
    def fetch(url: str) -> bytes:
        response = client.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        return bytes(response.content)

    return fetch


@dataclass
class MirrorReport:
    candidates: int = 0
    uploaded: int = 0
    already_mirrored: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(vars(self))


def _local_high(row: Any) -> Path | None:
    """The bootstrap's reference file is TCGdex's own high.webp; reuse it."""
    if not int(row["has_image"] or 0):
        return None
    path = Path(str(row["image_path"] or ""))
    if path.suffix.lower() != ".webp" or not path.is_file():
        return None
    return path


def mirror_card_images(
    catalog: Any,
    settings: Any,
    *,
    store: ObjectStore,
    bucket: str,
    fetch: Callable[[str], bytes],
    limit: int | None = None,
    language: str | None = None,
    gap_s: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> MirrorReport:
    """Upload high and low art for every TCGdex card not yet in the registry.

    Resumable: a card is recorded only after both files are stored, and a
    second run skips recorded cards whose art has not moved.
    """
    report = MirrorReport()
    registry = open_registry(settings.card_image_mirror_sqlite)
    try:
        mirrored = {
            str(row["card_id"]): str(row["object_base"])
            for row in registry.execute("SELECT card_id, object_base FROM mirrored_images")
        }
        query = (
            "SELECT id, language, remote_image_url, image_path, has_image FROM cards"
            f" WHERE remote_image_url LIKE 'https://{TCGDEX_ASSETS_HOST}/%'"
        )
        params: tuple[Any, ...] = ()
        if language:
            query += " AND language = ?"
            params = (language,)
        rows = catalog.execute(query + " ORDER BY id", params).fetchall()
        done = 0
        for row in rows:
            base = mirror_object_base(row["remote_image_url"])
            if base is None:
                continue
            card_id = str(row["id"])
            if mirrored.get(card_id) == base:
                report.already_mirrored += 1
                continue
            if limit is not None and done >= limit:
                break
            done += 1
            report.candidates += 1
            try:
                uploaded_sha = _mirror_one(row, base, store=store, bucket=bucket, fetch=fetch)
            except Exception as exc:  # noqa: BLE001  one bad card must not end the run
                report.failed += 1
                log(f"skip {card_id}: {type(exc).__name__}")
            else:
                registry.execute(
                    "INSERT OR REPLACE INTO mirrored_images VALUES (?, ?, ?, ?)",
                    (card_id, base, uploaded_sha, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
                registry.commit()
                mirrored[card_id] = base
                report.uploaded += 1
                log(f"mirrored {card_id}")
            if gap_s > 0:
                sleep(gap_s)
    finally:
        registry.close()
    return report


def _mirror_one(row: Any, base: str, *, store: ObjectStore, bucket: str, fetch: Callable[[str], bytes]) -> str:
    local = _local_high(row)
    high = local.read_bytes() if local is not None else fetch(tcgdex_source_url(base, "high"))
    if not is_webp(high):
        if local is None:
            raise ValueError("high.webp is not a WebP file")
        high = fetch(tcgdex_source_url(base, "high"))
        if not is_webp(high):
            raise ValueError("high.webp is not a WebP file")
    low = fetch(tcgdex_source_url(base, "low"))
    if not is_webp(low):
        raise ValueError("low.webp is not a WebP file")
    for quality, body in (("high", high), ("low", low)):
        store.put_object(
            Bucket=bucket,
            Key=f"{base}/{quality}.webp",
            Body=body,
            ContentType=CONTENT_TYPE,
            CacheControl=CACHE_CONTROL,
        )
    return hashlib.sha256(high).hexdigest()
