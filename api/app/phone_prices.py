"""The phone's daily price file: each phone-index card's Cardmarket trend.

A phone with no connection still recognises a card from its own picture
index, but the card's price and set come from the server. This file gives an
offline scan the same daily trend the app shows online (the Cardmarket price
file, `best_prices`' `cardmarket_file` source), plus the set name and image
address the index does not carry.

It is rebuilt after each import of Cardmarket's price file, for the rows of the
active phone index (`card_index.ids.txt`, then `card_index.prints.tsv`). The
file is gzip'd UTF-8, tab-separated, one card per line:

    #id	trend_cents	set_name	image_url
    en:sv1-1	605	Scarlet & Violet	https://…/high.webp

`trend_cents` is the trend in euro cents, empty when the card has none; an
empty `image_url` means the card has no image. Versions are the file's own
sha256, so a phone downloads it only when it changed.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("phone.prices")

FILE_NAME = "card_prices.tsv.gz"
HEADER = "#id\ttrend_cents\tset_name\timage_url\n"
_HEX = re.compile(r"^[0-9a-f]{64}$")
# Versions kept besides the active one, for phones mid-download.
KEEP_OLD = 2


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


def file_trend(trend: Any, trend_holo: Any, variants: dict[str, Any]) -> float | None:
    """The trend `best_prices` shows for one card from the price file.

    A printing sold only as a reverse holo is priced from the -holo column, as
    `_swap_holo` does; any other reads the plain trend, then the -holo one.
    """
    from app.price_sources import _holo_first

    first, second = (trend_holo, trend) if _holo_first(variants) else (trend, trend_holo)
    return _positive(first) or _positive(second)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").replace("\t", " ").split())


def index_ids(folder: Path) -> list[str]:
    """The phone index's card ids in row order, then its printings' ids."""
    ids = [line.strip() for line in (folder / "card_index.ids.txt").read_text(encoding="utf-8").splitlines()]
    ids = [card for card in ids if card]
    prints = folder / "card_index.prints.tsv"
    if prints.is_file():
        lines = prints.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("#id\t"):
            ids += [line.split("\t", 1)[0].strip() for line in lines[1:] if line.strip()]
    seen: set[str] = set()
    return [card for card in ids if not (card in seen or seen.add(card))]


def build_rows(catalog: sqlite3.Connection, ids: list[str]) -> tuple[list[str], int]:
    """One line per id the catalogue knows, and how many have a trend."""
    from app.card_images import display_image_url

    guide = {
        int(row[0]): (row[1], row[2])
        for row in catalog.execute("SELECT id_product, trend, trend_holo FROM cardmarket_guide")
    }
    from app.card_products import all_products

    local = all_products(catalog)
    wanted = set(ids)
    cards: dict[str, Any] = {}
    for row in catalog.execute("SELECT * FROM cards"):
        if row["id"] in wanted:
            cards[row["id"]] = row
    lines: list[str] = []
    priced = 0
    for card_id in ids:
        row = cards.get(card_id)
        if row is None:
            continue
        trend = None
        # The local answer for a card whose catalogue number is another's.
        product = local[card_id] if card_id in local else row["cardmarket_id"]
        if product and int(product) in guide:
            try:
                variants = json.loads(row["variants_json"] or "{}")
            except ValueError:
                variants = {}
            trend = file_trend(*guide[int(product)], variants if isinstance(variants, dict) else {})
        if trend is not None:
            priced += 1
        try:
            image = display_image_url(row, catalog) or ""
        except Exception:
            image = ""
        cents = "" if trend is None else str(round(trend * 100))
        lines.append(f"{card_id}\t{cents}\t{_clean(row['set_name'])}\t{_clean(image)}\n")
    return lines, priced


def _active_index(index_root: Path) -> tuple[str, Path]:
    from app.routes.card_index import _candidate

    version = (index_root / "ACTIVE").read_text().strip()
    folder, _, _ = _candidate(index_root, version)  # Checks the files' hashes.
    return version, folder


def _write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def build(catalog: sqlite3.Connection, index_root: Path, out_root: Path, *, guide_date: str | None = None) -> str:
    """Writes the price file for the active phone index; returns its version.

    The new version becomes active only once its folder is complete. Any
    failure leaves the previous version active.
    """
    index_version, folder = _active_index(index_root)
    lines, priced = build_rows(catalog, index_ids(folder))
    if not lines:
        raise ValueError("No phone index card is in the catalogue")
    raw = (HEADER + "".join(lines)).encode("utf-8")
    data = gzip.compress(raw, compresslevel=9, mtime=0)
    version = hashlib.sha256(data).hexdigest()
    out_root.mkdir(parents=True, exist_ok=True)
    target = out_root / version
    if not (target / "manifest.json").is_file():
        staging = out_root / f".{version}.{os.getpid()}.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        (staging / FILE_NAME).write_bytes(data)
        meta = {
            "version": version,
            "index_version": index_version,
            "guide_date": guide_date,
            "rows": len(lines),
            "priced": priced,
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "file": {"name": FILE_NAME, "bytes": len(data), "sha256": version},
        }
        (staging / "manifest.json").write_text(json.dumps(meta))
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    _write_atomic(out_root / "ACTIVE", version.encode())
    _prune(out_root, version)
    log.info("phone prices built version=%s rows=%s priced=%s bytes=%s", version[:12], len(lines), priced, len(data))
    return version


def _prune(out_root: Path, active: str) -> None:
    folders = sorted(
        (path for path in out_root.iterdir() if path.is_dir() and _HEX.fullmatch(path.name) and path.name != active),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in folders[KEEP_OLD:]:
        shutil.rmtree(path, ignore_errors=True)
    for path in out_root.iterdir():
        if path.name.startswith(".") and path.name.endswith(".tmp"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def read_active(out_root: Path) -> tuple[Path, dict]:
    """The active version's folder and manifest; raises when there is none."""
    version = (out_root / "ACTIVE").read_text().strip()
    return read_version(out_root, version)


def read_version(out_root: Path, version: str) -> tuple[Path, dict]:
    if not _HEX.fullmatch(version):
        raise ValueError("invalid version")
    root = out_root.resolve()
    if (root / version).is_symlink():
        raise ValueError("invalid folder")
    folder = (root / version).resolve()
    if folder.parent != root or not folder.is_dir():
        raise ValueError("invalid folder")
    meta = json.loads((folder / "manifest.json").read_text())
    file = folder / FILE_NAME
    if (not isinstance(meta, dict) or meta.get("version") != version or file.is_symlink()
            or not file.is_file() or file.stat().st_size != meta.get("file", {}).get("bytes")):
        raise ValueError("invalid version")
    return folder, meta


def refresh(catalog: sqlite3.Connection, settings: Any) -> str | None:
    """The nightly step, after the price file import. Never raises.

    `catalog` must see the full catalogue's `cards` (the app's catalogue
    connection, which holds the cloud catalogue) and the imported guide."""
    if not settings.card_prices_publish:
        return None
    try:
        row = catalog.execute("SELECT guide_date FROM cardmarket_guide_meta WHERE id = 1").fetchone()
        return build(catalog, settings.card_index_publish_dir, settings.card_prices_dir,
                     guide_date=row[0] if row else None)
    except Exception as exc:
        log.info("phone prices failed error=%s", type(exc).__name__)
        return None
