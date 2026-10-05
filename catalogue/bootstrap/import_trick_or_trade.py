from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from app.db import connect, coverage, coverage_by_language, init_catalog
from bootstrap.catalogue import _write_catalogue_version, upsert_card


COLLECTIONS = {
    "Trick-or-Trade": ("tot22", "Trick or Trade 2022", "Trick-or-Trade-Collection"),
    "Trick-or-Trade-2023": (
        "tot23",
        "Trick or Trade 2023",
        "Trick-or-Trade-2023-Collection",
    ),
    "Trick-or-Trade-2024": (
        "tot24",
        "Trick or Trade 2024",
        "Trick-or-Trade-2024-Collection",
    ),
}
USER_AGENT = "Scanapp catalogue image audit/1.0"


def _read_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _collection_images(slug: str) -> list[dict[str, str]]:
    from html.parser import HTMLParser

    class Images(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.urls: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            url = dict(attrs).get("data-src") or ""
            if url.startswith("https://den-cards.pokellector.com/") and url.endswith(
                ".thumb.png"
            ):
                self.urls.append(url)

    parser = Images()
    parser.feed(_read_url(f"https://www.pokellector.com/{slug}/").decode("utf-8", "replace"))
    result = []
    for thumb_url in parser.urls:
        filename = thumb_url.rsplit("/", 1)[-1].removesuffix(".thumb.png")
        match = re.fullmatch(r"(.+)\.([^.]+)\.(\d+)\.(\d+)", filename)
        if not match:
            continue
        printed_name, source_set, collector, _source_card_id = match.groups()
        result.append(
            {
                "name": printed_name.replace("-", " "),
                "normalised_name": _normalise(printed_name),
                "source_set": source_set,
                "collector_number": str(int(collector)),
                "image_url": thumb_url.removesuffix(".thumb.png") + ".png",
            }
        )
    return result


def _products(conn: sqlite3.Connection, expansion: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT url, name, card_id, matched
        FROM cardmarket_expansion_products
        WHERE expansion = ?
        ORDER BY url
        """,
        (expansion,),
    ).fetchall()


def _candidate(product: Any, images: list[dict[str, str]]) -> dict[str, str] | None:
    label = str(product["name"] or "").split("From", 1)[0].strip()
    parts = re.fullmatch(r"(.+?)\s+\(([^()]*)\)", label)
    if not parts:
        return None
    name, product_code = parts.groups()
    number_match = re.search(r"(\d+)\s*$", product_code)
    if not number_match:
        return None
    number = str(int(number_match.group(1)))
    matches = [
        image
        for image in images
        if image["normalised_name"] == _normalise(name)
        and image["collector_number"] == number
    ]
    return matches[0] if len(matches) == 1 else None


def prepare(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    imports: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for expansion, (set_id, set_name, slug) in COLLECTIONS.items():
        images = _collection_images(slug)
        if len(images) != 30:
            raise RuntimeError(f"Expected 30 source scans for {slug}, got {len(images)}")
        products = _products(conn, expansion)
        if len(products) != 30:
            raise RuntimeError(f"Expected 30 Cardmarket products for {expansion}, got {len(products)}")
        for product in products:
            image = _candidate(product, images)
            if image is None:
                skipped.append(
                    {
                        "expansion": expansion,
                        "name": str(product["name"] or ""),
                        "url": str(product["url"] or ""),
                        "reason": "No unique exact name and collector-number match in the collection scan list.",
                    }
                )
                continue
            match = re.fullmatch(r"(.+?)\s+\(([^()]*)\).*", str(product["name"] or ""))
            assert match is not None
            display_name, card_code = match.groups()
            number_match = re.search(r"(\d+)\s*$", card_code)
            assert number_match is not None
            number = str(int(number_match.group(1)))
            source_key = _normalise(image["source_set"])
            card_id = f"en:{set_id}-{source_key}-{number}"
            imports.append(
                {
                    "card_id": card_id,
                    "provider_id": card_id,
                    "name": display_name,
                    "set_id": set_id,
                    "set_name": set_name,
                    "collector_number": number,
                    "source_set": image["source_set"],
                    "image_url": image["image_url"],
                    "url": str(product["url"]),
                    "product_name": str(product["name"]),
                }
            )
    target_ids = [item["card_id"] for item in imports]
    if len(target_ids) != len(set(target_ids)):
        raise RuntimeError("Duplicate target catalogue IDs in prepared import")
    return imports, skipped


def apply_import(data_dir: Path, conn: sqlite3.Connection, imports: list[dict[str, Any]]) -> None:
    images_dir = data_dir / "reference-images" / "en"
    images_dir.mkdir(parents=True, exist_ok=True)
    for item in imports:
        existing = conn.execute("SELECT id FROM cards WHERE id = ?", (item["card_id"],)).fetchone()
        if existing:
            raise RuntimeError(f"Refusing to overwrite existing card {item['card_id']}")

    for item in imports:
        source_bytes = _read_url(item["image_url"])
        path = images_dir / f"{item['card_id'].split(':', 1)[1]}.webp"
        temporary = path.with_suffix(".download")
        temporary.write_bytes(source_bytes)
        with Image.open(temporary) as image:
            image.convert("RGB").save(path, "WEBP", quality=95, method=6)
        temporary.unlink()
        item["image_path"] = str(path)
        item["image_sha256"] = __import__("hashlib").sha256(path.read_bytes()).hexdigest()

    try:
        for item in imports:
            upsert_card(
                conn,
                card_id=item["card_id"],
                provider_id=item["provider_id"],
                name=item["name"],
                set_id=item["set_id"],
                set_name=item["set_name"],
                collector_number=item["collector_number"],
                language="en",
                category=None,
                rarity=None,
                illustrator=None,
                variants_json=json.dumps(
                    {
                        "special_print": item["set_name"],
                        "printed_set": item["source_set"],
                        "stamp": "Halloween Pikachu",
                        "image_source": "Pokellector scan CDN; original-card stamp retained",
                    }
                ),
                image_path=item["image_path"],
                has_image=1,
                cardmarket_id=None,
                cardmarket_url=item["url"],
                cardmarket_verified=1,
                cardmarket_provenance="manual-image-review",
                cardmarket_verified_at=None,
                remote_image_url=item["image_url"],
            )
            conn.execute(
                """
                UPDATE cardmarket_expansion_products
                SET card_id = ?, matched = 1
                WHERE url = ?
                """,
                (item["card_id"], item["url"]),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise RuntimeError(f"Cardmarket product row disappeared: {item['url']}")
        cards_n, indexed_n, missing_n = coverage(conn)
        language_counts = {
            str(row["language"]): int(row["cards"])
            for row in coverage_by_language(conn)
        }
        _write_catalogue_version(
            data_dir,
            conn,
            languages=sorted(language_counts),
            allowed=set(),
            replace=False,
            imported=cards_n,
            indexed=indexed_n,
            missing=missing_n,
            per_language=language_counts,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        for item in imports:
            path = Path(str(item.get("image_path") or ""))
            if path.is_file():
                path.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import exact stamped Trick or Trade scans and bind their Cardmarket products."
    )
    parser.add_argument("--data-dir", default="/data")
    parser.add_argument("--apply", action="store_true", help="Write images, catalogue rows and URLs.")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    conn = connect(data_dir / "catalog.sqlite")
    init_catalog(conn)
    imports, skipped = prepare(conn)
    print(f"prepared {len(imports)} exact scan-to-product matches; skipped {len(skipped)}")
    for item in imports:
        print(f"  {item['card_id']} {item['name']} · {item['source_set']} {item['collector_number']} → {item['url']}")
    for item in skipped:
        print(f"  REVIEW {item['name']} → {item['url']} ({item['reason']})")
    if args.apply:
        backup = data_dir / "catalog.sqlite.before-trick-or-trade-import"
        if not backup.exists():
            destination = sqlite3.connect(backup)
            conn.backup(destination)
            destination.close()
            print(f"database backup: {backup}")
        apply_import(data_dir, conn, imports)
        print(f"imported and mapped {len(imports)} cards")
    else:
        print("dry run; pass --apply to import")
    conn.close()


if __name__ == "__main__":
    main()
