from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse, urlunparse

_PRODUCT_SLUG_RE = re.compile(r"/Products/Singles/[^/]+/([^/?#]+)", re.I)
_SLUG_CODE_RE = re.compile(r"-([A-Za-z0-9]*[A-Za-z])(\d+)$")
PROMO_SLUG_CODES = (
    "XYPR",
    "SWSH",
    "SM-P",
    "SV-P",
    "XY-P",
    "SVP",
    "S-P",
    "M-P",
)
_PROMO_SLUG_RE = re.compile(
    r"-(" + "|".join(re.escape(code) for code in PROMO_SLUG_CODES) + r")(\d+)$",
    re.I,
)
_PRICE_TAIL_RE = re.compile(r"From\s+[\d.,]+\s*€.*$", re.I)
_LATIN_SLUG_RE = re.compile(r"[a-z0-9]+")
_PROTECTED_PROVENANCE = {"helper-map", "manifest-url"}
JA_COLLECTOR_PROVENANCE = "ja-collector"
_LISTING_SET_COLLECTOR_RE = re.compile(
    r"\(([A-Za-z][A-Za-z0-9.\-]*)\s+([^)]+)\)"
)
_WEAK_LATIN_NAME_SLUGS = frozenset(
    {"ex", "gx", "v", "vmax", "vstar", "lv", "lvx", "break", "tag"}
)
_LOCALIZED_EXPANSION_RE = re.compile(
    r"(?:"
    r"-idth|"
    r"-jp|"
    r"-ja|"
    r"-indonesian(?:-promos)?|"
    r"-simplified-chinese(?:-promos?)?|"
    r"-traditional-chinese(?:-promos?)?"
    r")$",
    re.I,
)
_PROMO_SET_EXPANSIONS = {
    "swshp": {"swsh-black-star-promos"},
    "s-p": {"sword-shield-promos"},
    "svp": {"svp-black-star-promos", "sv-black-star-promos"},
    "smp": {"sm-black-star-promos"},
    "xyp": {"xy-black-star-promos"},
    "sv-p": {"sv-promos", "scarlet-violet-promos"},
    "m-p": {"m-p-promos", "mega-promos"},
}

CARDMARKET_LOCALES = {"en", "de", "fr", "es", "it"}
LANGUAGE_DIRS = {"en", "ja", "zh-cn", "zh-tw", "ko", "fr", "de", "es", "it", "pt"}


def parse_product_id(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def cardmarket_locale(language: str | None) -> str:
    raw = (language or "en").lower()
    if raw in CARDMARKET_LOCALES:
        return raw
    return "en"


def cardmarket_slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("&", " ").replace("'", "")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text)
    return text.strip("-")


def collector_digits(collector_number: str) -> str:
    head = (collector_number or "").split("/")[0].strip()
    return re.sub(r"\D", "", head)


def cardmarket_singles_url(
    *,
    name: str,
    expansion: str,
    set_code: str,
    collector_number: str = "",
    language: str | None = "en",
) -> str | None:
    """Canonical Cardmarket product page: /Singles/{expansion}/{Name}-{CODE}{number}."""
    expansion_slug = cardmarket_slug(expansion)
    name_slug = cardmarket_slug(name)
    code = re.sub(r"[^A-Za-z0-9]", "", set_code or "").upper()
    number = collector_digits(collector_number)
    if not expansion_slug or not name_slug or not code or not number:
        return None
    locale = cardmarket_locale(language)
    return (
        f"https://www.cardmarket.com/{locale}/Pokemon/Products/Singles/"
        f"{expansion_slug}/{name_slug}-{code}{number}"
    )


def is_verified_singles_url(url: str | None) -> bool:
    raw = (url or "").strip()
    if not raw.startswith("https://"):
        return False
    host = urlparse(raw).netloc.lower()
    path = urlparse(raw).path
    if host not in {"www.cardmarket.com", "cardmarket.com"}:
        return False
    return "/Products/Singles/" in path and path.rstrip("/").count("/") >= 6


@dataclass(frozen=True)
class CardmarketMapping:
    product_id: int | None
    url: str | None
    verified: bool
    provenance: str
    verified_at: str | None = None

    def public_url(self) -> str | None:
        if self.verified and self.url:
            return self.url
        return None


def cardmarket_product_url(
    product_id: object = None,
    *,
    provider_id: str | None = None,
    name: str | None = None,
    set_name: str | None = None,
    language: str | None = "en",
    expansion: str | None = None,
    set_code: str | None = None,
    collector_number: str | None = None,
) -> str | None:
    del product_id, provider_id
    return cardmarket_singles_url(
        name=name or "",
        expansion=expansion or set_name or "",
        set_code=set_code or "",
        collector_number=collector_number or "",
        language=language,
    )


def mapping_from_payload(
    payload: dict[str, Any], *, language: str | None = "en"
) -> CardmarketMapping:
    product_id = extract_cardmarket_id(payload)
    pricing = payload.get("pricing") if isinstance(payload, dict) else None
    if isinstance(pricing, dict):
        market = pricing.get("cardmarket")
        if isinstance(market, dict) and isinstance(market.get("url"), str):
            candidate = market["url"].strip()
            if is_verified_singles_url(candidate):
                return CardmarketMapping(
                    product_id=product_id,
                    url=candidate,
                    verified=True,
                    provenance="tcgdex-singles-url",
                    verified_at=datetime_now(),
                )
    return CardmarketMapping(
        product_id=product_id,
        url=None,
        verified=False,
        provenance="tcgdex-id" if product_id else "none",
        verified_at=None,
    )


def mapping_from_manifest(card: dict[str, Any]) -> CardmarketMapping:
    language = str(card.get("language") or "en")
    product_id = parse_product_id(card.get("cardmarket_id"))
    raw = card.get("cardmarket_url")
    if isinstance(raw, str) and raw.strip():
        url = raw.strip()
        verified = is_verified_singles_url(url)
        return CardmarketMapping(
            product_id=product_id,
            url=url,
            verified=verified,
            provenance="manifest-url" if verified else "manifest-unverified",
            verified_at=datetime_now() if verified else None,
        )
    generated = cardmarket_singles_url(
        name=str(card.get("name") or ""),
        expansion=str(card.get("cardmarket_expansion") or ""),
        set_code=str(card.get("cardmarket_set_code") or ""),
        collector_number=str(card.get("collector_number") or ""),
        language=language,
    )
    return CardmarketMapping(
        product_id=product_id,
        url=generated,
        verified=False,
        provenance="generated-singles" if generated else "none",
        verified_at=None,
    )


def url_from_manifest_card(card: dict[str, Any]) -> tuple[int | None, str | None]:
    mapping = mapping_from_manifest(card)
    return mapping.product_id, mapping.url


def fields_from_payload(
    payload: dict[str, Any], *, language: str | None = "en"
) -> tuple[int | None, str | None]:
    mapping = mapping_from_payload(payload, language=language)
    return mapping.product_id, mapping.public_url()


def mapping_from_row(row: Any) -> CardmarketMapping:
    if isinstance(row, dict):
        keys = set(row)
        get = row.get
    else:
        try:
            keys = set(row.keys())
        except Exception:
            keys = set()
        get = lambda key, default=None: row[key] if key in keys else default  # noqa: E731
    url = str(get("cardmarket_url") or "") or None
    product_id = parse_product_id(get("cardmarket_id"))
    verified = bool(int(get("cardmarket_verified") or 0)) if "cardmarket_verified" in keys else False
    provenance = str(get("cardmarket_provenance") or "") or "unknown"
    verified_at = str(get("cardmarket_verified_at") or "") or None
    if not verified and is_verified_singles_url(url) and "cardmarket_verified" not in keys:
        verified = True
        provenance = "legacy-singles"
    return CardmarketMapping(
        product_id=product_id,
        url=url,
        verified=verified,
        provenance=provenance,
        verified_at=verified_at,
    )


def url_for_row(row: sqlite3.Row) -> str | None:
    return mapping_from_row(row).public_url()


def cardmarket_search_url(
    name: str,
    collector_number: str = "",
    *,
    language: str | None = "en",
) -> str | None:
    query = " ".join(
        part.strip()
        for part in (name, collector_number)
        if part and str(part).strip()
    )
    if not query:
        return None
    locale = cardmarket_locale(language)
    return (
        "https://www.cardmarket.com/"
        f"{locale}/Pokemon/Products/Search?searchString={quote_plus(query)}"
    )


def extract_cardmarket_id(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    pricing = payload.get("pricing")
    if isinstance(pricing, dict):
        market = pricing.get("cardmarket")
        if isinstance(market, dict):
            found = parse_product_id(market.get("idProduct"))
            if found:
                return found
    third = payload.get("thirdParty")
    if isinstance(third, dict):
        found = parse_product_id(third.get("cardmarket"))
        if found:
            return found
    for variant in payload.get("variants_detailed") or []:
        if not isinstance(variant, dict):
            continue
        nested = extract_cardmarket_id(variant)
        if nested:
            return nested
        nested_third = variant.get("thirdParty")
        if isinstance(nested_third, dict):
            found = parse_product_id(nested_third.get("cardmarket"))
            if found:
                return found
    return None


def datetime_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalize_product_url(url: str | None) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    parts = urlparse(raw)
    path = (parts.path or "").rstrip("/")
    host = (parts.netloc or "").lower()
    if "cardmarket.com" in host and path:
        return urlunparse(("https", "www.cardmarket.com", path, "", "", ""))
    if path:
        return f"{parts.scheme}://{parts.netloc}{path}" if parts.netloc else raw.split("#")[0].split("?")[0]
    return raw.split("#")[0].split("?")[0]


def is_job_url(url: str | None) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if "prices.pokemontcg.io/cardmarket/" in lowered:
        return True
    parts = urlparse(raw)
    host = (parts.netloc or "").lower()
    if host not in {"www.cardmarket.com", "cardmarket.com"}:
        return False
    bits = [bit for bit in (parts.path or "").split("/") if bit]
    if len(bits) < 6:
        return False
    return (
        bits[1].lower() == "pokemon"
        and bits[2].lower() == "products"
        and bits[3].lower() == "singles"
        and bool(bits[4] and bits[5])
    )


def is_expansion_list_url(url: str | None) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    parts = urlparse(raw)
    host = (parts.netloc or "").lower()
    if host not in {"www.cardmarket.com", "cardmarket.com"}:
        return False
    bits = [bit for bit in (parts.path or "").split("/") if bit]
    return (
        len(bits) == 5
        and bits[1].lower() == "pokemon"
        and bits[2].lower() == "products"
        and bits[3].lower() == "singles"
        and bool(bits[4])
    )


class MappingError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def helper_maps_path(data_dir: Path) -> Path:
    return Path(data_dir) / "cardmarket-maps.json"


def _read_helper_maps(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = helper_maps_path(data_dir)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, dict):
        return {}
    return {
        str(card_id): item
        for card_id, item in cards.items()
        if isinstance(item, dict)
    }


def _write_helper_maps(data_dir: Path, cards: dict[str, dict[str, Any]]) -> None:
    path = helper_maps_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"cards": cards}, indent=2) + "\n")
    tmp.replace(path)


def apply_helper_maps(conn: sqlite3.Connection, data_dir: Path) -> int:
    updated = 0
    for card_id, item in _read_helper_maps(data_dir).items():
        url = str(item.get("cardmarket_url") or item.get("url") or "")
        if not is_verified_singles_url(url):
            continue
        mapping = CardmarketMapping(
            product_id=parse_product_id(item.get("cardmarket_id")),
            url=normalize_product_url(url) or url,
            verified=True,
            provenance=str(item.get("provenance") or "helper-map"),
            verified_at=str(item.get("verified_at") or datetime_now()),
        )
        cursor = conn.execute(
            """
            UPDATE cards
            SET cardmarket_id = COALESCE(?, cardmarket_id),
                cardmarket_url = ?,
                cardmarket_verified = 1,
                cardmarket_provenance = ?,
                cardmarket_verified_at = ?
            WHERE id = ?
            """,
            (
                mapping.product_id,
                mapping.url,
                mapping.provenance,
                mapping.verified_at,
                card_id,
            ),
        )
        updated += int(cursor.rowcount or 0)
    return updated


def map_card_product(
    conn: sqlite3.Connection,
    data_dir: Path,
    card_id: str,
    url: str,
    product_id: object = None,
    *,
    provenance: str = "helper-map",
    commit: bool = True,
) -> dict[str, Any]:
    key = (card_id or "").strip()
    product = normalize_product_url(url)
    if not key:
        raise MappingError("Need a catalogue card id")
    if not is_verified_singles_url(product):
        raise MappingError("Need a Cardmarket Singles product URL")
    row = conn.execute("SELECT * FROM cards WHERE id = ?", (key,)).fetchone()
    if row is None:
        raise MappingError("Unknown card", status_code=404)
    mapping = CardmarketMapping(
        product_id=parse_product_id(product_id) or parse_product_id(row["cardmarket_id"]),
        url=product,
        verified=True,
        provenance=provenance or "helper-map",
        verified_at=datetime_now(),
    )
    conn.execute(
        """
        UPDATE cards
        SET cardmarket_id = COALESCE(?, cardmarket_id),
            cardmarket_url = ?,
            cardmarket_verified = 1,
            cardmarket_provenance = ?,
            cardmarket_verified_at = ?
        WHERE id = ?
        """,
        (
            mapping.product_id,
            mapping.url,
            mapping.provenance,
            mapping.verified_at,
            key,
        ),
    )
    stored = _read_helper_maps(data_dir)
    stored[key] = {
        "card_id": key,
        "cardmarket_url": mapping.url,
        "cardmarket_id": mapping.product_id,
        "verified_at": mapping.verified_at,
        "provenance": mapping.provenance,
    }
    _write_helper_maps(data_dir, stored)
    if commit:
        conn.commit()
    return {
        "card_id": key,
        "name": str(row["name"] or ""),
        "url": mapping.url,
        "cardmarket_id": mapping.product_id,
        "verified": True,
        "provenance": mapping.provenance,
    }


def is_official_catalogue_id(card_id: str) -> bool:
    ident = str(card_id or "")
    return ":" in ident and not ident.startswith(("extra-", "cm-"))


def official_cover_for_listing(
    conn: sqlite3.Connection, url: str, name: str = ""
) -> sqlite3.Row | None:
    """Official TCGdex print that already covers this Cardmarket SKU (including V2 siblings)."""
    product = normalize_product_url(url) or url
    if not is_verified_singles_url(product):
        return None
    owner = conn.execute(
        """
        SELECT * FROM cards
        WHERE cardmarket_url = ?
        """,
        (product,),
    ).fetchone()
    if owner is not None and is_official_catalogue_id(str(owner["id"])):
        return owner
    coded = singles_code_and_number(product)
    expansion = _expansion_from_url(product)
    if coded and expansion:
        _code, number = coded
        slug_number = str(number).lstrip("0") or "0"
        padded = slug_number.zfill(3)
        rows = conn.execute(
            """
            SELECT * FROM cards
            WHERE (has_image = 1 OR remote_image_url LIKE 'https://%')
              AND (
                collector_number = ?
                OR collector_number = ?
                OR collector_number LIKE ?
                OR collector_number LIKE ?
              )
            """,
            (slug_number, padded, f"{slug_number}/%", f"{padded}/%"),
        ).fetchall()
        hits: list[sqlite3.Row] = []
        for row in rows:
            if not is_official_catalogue_id(str(row["id"])):
                continue
            if not set_fits_expansion(
                str(row["set_id"] or ""),
                str(row["set_name"] or ""),
                expansion,
            ):
                continue
            hits.append(row)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            named = [
                row
                for row in hits
                if name_fits_product_slug(
                    latin_name_slug(str(row["name"] or "")),
                    product_slug(product).lower(),
                )
            ]
            if len(named) == 1:
                return named[0]
            if named:
                return named[0]
            return hits[0]
    unique = _unique_card_for_product(conn, product, name)
    if unique is not None and is_official_catalogue_id(str(unique["id"])):
        return unique
    return None


def unmatched_listing_id(url: str) -> str:
    slug = product_slug(url).lower()
    safe = re.sub(r"[^a-z0-9._-]+", "-", slug).strip("-") or "listing"
    return f"cm-{safe[:96]}"


def _listing_image_host_ok(src: str) -> bool:
    host = urlparse(src).netloc.lower()
    return host.endswith("cardmarket.com") or host.endswith(".cardmarket.com")


def save_listing_image_url(conn: sqlite3.Connection, url: str, image_url: str) -> str:
    product = normalize_product_url(url) or url
    src = str(image_url or "").strip()
    if not src or not _listing_image_host_ok(src):
        return ""
    conn.execute(
        """
        UPDATE cardmarket_expansion_products
        SET listing_image_url = ?
        WHERE url = ?
        """,
        (src, product),
    )
    return src


def store_unmatched_product_image(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    url: str,
    image_url: str,
    name: str = "",
) -> dict[str, Any]:
    """Store the Cardmarket listing image URL next to the product URL. No image file."""
    del data_dir
    product = normalize_product_url(url)
    if not is_verified_singles_url(product):
        raise MappingError("Need a Cardmarket Singles product URL")
    src = str(image_url or "").strip()
    if not src or not _listing_image_host_ok(src):
        raise MappingError("Need a Cardmarket listing image URL")
    expansion = _expansion_from_url(product)
    label = (name or "").strip()
    stamp = datetime_now()
    conn.execute(
        """
        INSERT INTO cardmarket_expansion_products (
            url, expansion, name, source, page_url, card_id, matched,
            imported_at, listing_image_url
        ) VALUES (?, ?, ?, 'helper-image', ?, NULL, 0, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            listing_image_url = excluded.listing_image_url,
            name = CASE
                WHEN excluded.name != '' THEN excluded.name
                ELSE cardmarket_expansion_products.name
            END
        """,
        (product, expansion, label, product, stamp, src),
    )
    conn.commit()
    return {
        "stored": True,
        "reason": "url",
        "url": product,
        "image_url": src,
    }


def list_unmatched_products(
    conn: sqlite3.Connection,
    *,
    after: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Page Cardmarket URLs that still need a listing image URL (not official TCGdex)."""
    limit = min(max(int(limit or 50), 1), 200)
    cursor = str(after or "")
    total_row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM cardmarket_expansion_products
        WHERE (matched = 0 OR card_id IS NULL OR card_id = '')
          AND IFNULL(listing_image_url, '') = ''
        """
    ).fetchone()
    total = int(total_row["n"] if total_row is not None else 0)
    products: list[dict[str, str]] = []
    examined = cursor
    scanned = 0
    exhausted = False
    max_scan = 2000
    while len(products) < limit and scanned < max_scan:
        take = min(80, max_scan - scanned)
        rows = conn.execute(
            """
            SELECT url, name, expansion
            FROM cardmarket_expansion_products
            WHERE (matched = 0 OR card_id IS NULL OR card_id = '')
              AND IFNULL(listing_image_url, '') = ''
              AND url > ?
              AND url NOT IN (
                SELECT cardmarket_url FROM cards
                WHERE cardmarket_url IS NOT NULL AND cardmarket_url != ''
              )
            ORDER BY url
            LIMIT ?
            """,
            (examined, take),
        ).fetchall()
        if not rows:
            exhausted = True
            break
        for row in rows:
            scanned += 1
            url = normalize_product_url(str(row["url"] or "")) or str(row["url"] or "")
            examined = url or str(row["url"] or examined)
            if not is_verified_singles_url(url):
                continue
            if official_cover_for_listing(conn, url, str(row["name"] or "")) is not None:
                continue
            products.append(
                {
                    "url": url,
                    "name": str(row["name"] or ""),
                    "expansion": str(row["expansion"] or ""),
                }
            )
            if len(products) >= limit:
                break
        if len(rows) < take:
            exhausted = True
            break
    return {
        "total": total,
        "after": cursor,
        "examined": examined,
        "has_more": not exhausted,
        "products": products,
    }


def _expansion_from_url(url: str | None) -> str:
    parts = urlparse(url or "")
    bits = [bit for bit in (parts.path or "").split("/") if bit]
    if len(bits) >= 5:
        return bits[4]
    return ""


def product_slug(url: str | None) -> str:
    parts = urlparse(url or "")
    bits = [bit for bit in (parts.path or "").split("/") if bit]
    return bits[-1] if bits else ""


def set_fits_expansion(
    set_id: str,
    set_name: str,
    expansion: str,
    *,
    strict: bool = False,
) -> bool:
    exp = (expansion or "").lower()
    set_slug = cardmarket_slug(set_name or "").lower()
    if not exp:
        return False
    if _LOCALIZED_EXPANSION_RE.search(exp) and set_slug != exp:
        return False
    if set_slug == exp:
        return True
    allowed = _PROMO_SET_EXPANSIONS.get((set_id or "").lower())
    if allowed and exp in allowed:
        return True
    if strict:
        return False
    if set_slug and (set_slug in exp or exp in set_slug):
        return True
    return False


def latin_name_slug(name: str) -> str | None:
    """Name slug usable for unique-link. CJK leftovers like 'ex'/'vmax' are ignored."""
    slug = cardmarket_slug(name).lower()
    if not slug:
        return None
    letters = "".join(_LATIN_SLUG_RE.findall(slug))
    if len(letters) < 3:
        return None
    if slug in _WEAK_LATIN_NAME_SLUGS or letters in _WEAK_LATIN_NAME_SLUGS:
        return None
    return slug


def listing_set_collector(name: str) -> tuple[str, str] | None:
    """Set code and collector as written in a Cardmarket label, e.g. (s8a 014)."""
    text = _PRICE_TAIL_RE.sub("", str(name or "")).strip()
    match = None
    for match in _LISTING_SET_COLLECTOR_RE.finditer(text):
        pass
    if match is None:
        return None
    set_id = match.group(1).strip()
    collector = match.group(2).strip()
    if not set_id or not collector:
        return None
    return set_id, collector


def name_fits_product_slug(name_slug: str | None, product_path: str) -> bool:
    """True when the card name is a hyphen-bounded token in the listing slug."""
    if not name_slug or not product_path:
        return False
    return f"-{name_slug}-" in f"-{product_path.lower()}-"


def product_sku_key(url: str | None) -> tuple[str, str, str] | None:
    product = normalize_product_url(url) or url
    if not is_verified_singles_url(product):
        return None
    coded = singles_code_and_number(product)
    expansion = _expansion_from_url(product)
    if not coded or not expansion:
        return None
    code, number = coded
    return expansion.lower(), code.upper(), str(number)


def clean_product_label(name: str, url: str) -> str:
    text = _PRICE_TAIL_RE.sub("", name or "").strip()
    slug = product_slug(url)
    if text and slug and slug.lower() not in text.lower().replace(" ", "-"):
        return f"{text} ({slug})"
    return text or slug


def grouped_expansion_skus(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str, str], list[sqlite3.Row]]:
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    rows = conn.execute(
        """
        SELECT url, name, expansion, card_id, matched
        FROM cardmarket_expansion_products
        ORDER BY url
        """
    ).fetchall()
    for row in rows:
        key = product_sku_key(str(row["url"] or ""))
        if key is None:
            continue
        groups.setdefault(key, []).append(row)
    return groups


def ambiguous_sku_keys(
    conn: sqlite3.Connection,
) -> set[tuple[str, str, str]]:
    return {key for key, rows in grouped_expansion_skus(conn).items() if len(rows) >= 2}


def _variant_label_from_card(row: sqlite3.Row | None) -> str | None:
    if row is None:
        return None
    raw = row["variants_json"] if "variants_json" in row.keys() else ""
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    label = str(payload.get("variant_label") or "").strip()
    return label or None


def variants_for_key(
    conn: sqlite3.Connection,
    key: tuple[str, str, str],
    *,
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] | None = None,
    owners: dict[str, sqlite3.Row] | None = None,
) -> list[dict[str, Any]]:
    grouped = groups if groups is not None else grouped_expansion_skus(conn)
    if owners is None:
        owners = {
            str(row["cardmarket_url"] or ""): row
            for row in conn.execute(
                """
                SELECT id, variants_json, cardmarket_url
                FROM cards
                WHERE cardmarket_url IS NOT NULL AND TRIM(cardmarket_url) != ''
                """
            ).fetchall()
        }
    variants: list[dict[str, Any]] = []
    for row in grouped.get(key, []):
        url = str(row["url"] or "")
        owner = owners.get(url)
        label = _variant_label_from_card(owner) or clean_product_label(
            str(row["name"] or ""), url
        )
        variants.append(
            {
                "url": url,
                "slug": product_slug(url),
                "label": label,
                "card_id": str(owner["id"]) if owner is not None else None,
            }
        )
    return variants


def _card_owners(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        str(row["cardmarket_url"] or ""): row
        for row in conn.execute(
            """
            SELECT id, variants_json, cardmarket_url
            FROM cards
            WHERE cardmarket_url IS NOT NULL AND TRIM(cardmarket_url) != ''
            """
        ).fetchall()
    }


def variants_for_row(
    conn: sqlite3.Connection,
    row: Any,
    *,
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] | None = None,
    owners: dict[str, sqlite3.Row] | None = None,
) -> list[dict[str, Any]]:
    grouped = groups if groups is not None else grouped_expansion_skus(conn)
    owned = owners if owners is not None else _card_owners(conn)
    stored = mapping_from_row(row).url
    if stored:
        key = product_sku_key(stored)
        if key is not None:
            variants = variants_for_key(conn, key, groups=grouped, owners=owned)
            return variants if len(variants) >= 2 else []
    name_slug = latin_name_slug(str(_row_value(row, "name") or ""))
    number = collector_digits(str(_row_value(row, "collector_number") or "")).lstrip(
        "0"
    ) or "0"
    set_id = str(_row_value(row, "set_id") or "")
    set_name = str(_row_value(row, "set_name") or "")
    if not name_slug:
        return []
    found: list[tuple[str, str, str]] = []
    for key, products in grouped.items():
        expansion, _code, sku_number = key
        if sku_number != number or not set_fits_expansion(set_id, set_name, expansion):
            continue
        if any(
            name_fits_product_slug(
                name_slug, product_slug(str(item["url"] or "")).lower()
            )
            for item in products
        ):
            found.append(key)
    if len(found) != 1:
        return []
    variants = variants_for_key(conn, found[0], groups=grouped, owners=owned)
    return variants if len(variants) >= 2 else []


def apply_variants_to_candidate(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] | None = None,
    owners: dict[str, sqlite3.Row] | None = None,
) -> None:
    card_id = str(item.get("card_id") or "")
    row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    variants = (
        variants_for_row(conn, row, groups=groups, owners=owners)
        if row is not None
        else []
    )
    item["cardmarket_variants"] = variants
    if len(variants) >= 2:
        item["cardmarket_url"] = None
        item["cardmarket_prices"] = []


def _clear_auto_product_url(conn: sqlite3.Connection, card_id: str, url: str) -> None:
    conn.execute(
        """
        UPDATE cards
        SET cardmarket_url = NULL,
            cardmarket_verified = 0,
            cardmarket_provenance = NULL,
            cardmarket_verified_at = NULL
        WHERE id = ?
        """,
        (card_id,),
    )
    conn.execute(
        """
        UPDATE cardmarket_expansion_products
        SET card_id = NULL, matched = 0
        WHERE url = ?
        """,
        (url,),
    )


def clear_ambiguous_auto_links(conn: sqlite3.Connection) -> int:
    """Drop helper-expansion URLs when that SKU identity has 2+ Cardmarket products."""
    ambiguous = ambiguous_sku_keys(conn)
    if not ambiguous:
        return 0
    cleared = 0
    rows = conn.execute(
        """
        SELECT id, cardmarket_url, cardmarket_provenance
        FROM cards
        WHERE cardmarket_url IS NOT NULL AND TRIM(cardmarket_url) != ''
        """
    ).fetchall()
    for row in rows:
        url = str(row["cardmarket_url"] or "")
        key = product_sku_key(url)
        provenance = str(row["cardmarket_provenance"] or "")
        if (
            key not in ambiguous
            or provenance in _PROTECTED_PROVENANCE
            or provenance == JA_COLLECTOR_PROVENANCE
        ):
            continue
        _clear_auto_product_url(conn, str(row["id"]), url)
        cleared += 1
    return cleared


def clear_mismatched_auto_links(conn: sqlite3.Connection) -> int:
    """Drop helper-expansion URLs that are a different language set or a wrong name."""
    cleared = 0
    rows = conn.execute(
        """
        SELECT id, name, set_id, set_name, cardmarket_url, cardmarket_provenance
        FROM cards
        WHERE cardmarket_url IS NOT NULL AND TRIM(cardmarket_url) != ''
        """
    ).fetchall()
    for row in rows:
        provenance = str(row["cardmarket_provenance"] or "")
        if (
            provenance in _PROTECTED_PROVENANCE
            or provenance == JA_COLLECTOR_PROVENANCE
            or provenance != "helper-expansion"
        ):
            continue
        url = str(row["cardmarket_url"] or "")
        expansion = _expansion_from_url(url)
        name_ok = name_fits_product_slug(
            latin_name_slug(str(row["name"] or "")),
            product_slug(url),
        )
        set_ok = set_fits_expansion(
            str(row["set_id"] or ""),
            str(row["set_name"] or ""),
            expansion,
        )
        if name_ok and set_ok:
            continue
        _clear_auto_product_url(conn, str(row["id"]), url)
        cleared += 1
    return cleared


def resolve_variant_choice(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    scanned_card_id: str,
    url: str,
) -> dict[str, Any]:
    """Map a user-picked listing onto the owning extra, or Save onto the scanned print.

    If several SKUs share the identity and none is owned yet, store the choice on the
    scan only so a metal/UPC listing cannot overwrite the pack print.
    """
    product = normalize_product_url(url) or url
    if not is_verified_singles_url(product):
        raise MappingError("Need a Cardmarket Singles product URL")
    owner = conn.execute(
        """
        SELECT id FROM cards
        WHERE cardmarket_url = ?
        """,
        (product,),
    ).fetchone()
    if owner is not None:
        return {
            "card_id": str(owner["id"]),
            "url": product,
            "mapped": False,
        }
    key = product_sku_key(product)
    grouped = grouped_expansion_skus(conn)
    group = grouped.get(key, []) if key is not None else []
    owners = _card_owners(conn)
    sibling_owned = any(
        owners.get(str(row["url"] or "")) is not None
        and str(row["url"] or "") != product
        for row in group
    )
    if len(group) >= 2 and not sibling_owned:
        return {
            "card_id": scanned_card_id,
            "url": product,
            "mapped": False,
        }
    mapped = map_card_product(
        conn,
        data_dir,
        scanned_card_id,
        product,
        provenance="helper-map",
    )
    return {
        "card_id": str(mapped["card_id"]),
        "url": product,
        "mapped": True,
    }


def unmatched_cards_by_collector(
    conn: sqlite3.Connection,
) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    rows = conn.execute(
        """
        SELECT * FROM cards
        WHERE cardmarket_verified = 0
           OR cardmarket_url IS NULL
           OR cardmarket_url = ''
        """
    ).fetchall()
    for row in rows:
        number = collector_digits(str(row["collector_number"] or "")).lstrip("0") or "0"
        grouped.setdefault(number, []).append(row)
    return grouped


def unmatched_cards_by_name(
    conn: sqlite3.Connection,
) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    rows = conn.execute(
        """
        SELECT * FROM cards
        WHERE cardmarket_verified = 0
           OR cardmarket_url IS NULL
           OR cardmarket_url = ''
        """
    ).fetchall()
    for row in rows:
        name = latin_name_slug(str(row["name"] or ""))
        if name:
            grouped.setdefault(name, []).append(row)
    return grouped


def _drop_indexed_card(
    cards_by_number: dict[str, list[sqlite3.Row]], card_id: str, number: str
) -> None:
    bucket = cards_by_number.get(number)
    if not bucket:
        return
    cards_by_number[number] = [row for row in bucket if str(row["id"]) != card_id]


def _drop_indexed_name(
    cards_by_name: dict[str, list[sqlite3.Row]], card_id: str, name_slug: str | None
) -> None:
    if not name_slug:
        return
    bucket = cards_by_name.get(name_slug)
    if not bucket:
        return
    cards_by_name[name_slug] = [row for row in bucket if str(row["id"]) != card_id]


def _unique_card_for_uncoded_product(
    conn: sqlite3.Connection,
    product: str,
    *,
    cards_by_name: dict[str, list[sqlite3.Row]] | None = None,
) -> sqlite3.Row | None:
    expansion_slug = _expansion_from_url(product).lower()
    path = product_slug(product).lower()
    if not expansion_slug or not path or latin_name_slug(path) != path:
        return None
    if cards_by_name is not None:
        rows = cards_by_name.get(path, [])
    else:
        rows = [
            row
            for row in conn.execute(
                """
                SELECT * FROM cards
                WHERE cardmarket_verified = 0
                   OR cardmarket_url IS NULL
                   OR cardmarket_url = ''
                """
            ).fetchall()
            if latin_name_slug(str(row["name"] or "")) == path
        ]
    hits = [
        row
        for row in rows
        if set_fits_expansion(
            str(row["set_id"] or ""),
            str(row["set_name"] or ""),
            expansion_slug,
            strict=True,
        )
    ]
    if len(hits) != 1:
        return None
    return hits[0]


def _unique_card_for_product(
    conn: sqlite3.Connection,
    url: str,
    name_hint: str = "",
    *,
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] | None = None,
    cards_by_number: dict[str, list[sqlite3.Row]] | None = None,
    cards_by_name: dict[str, list[sqlite3.Row]] | None = None,
) -> sqlite3.Row | None:
    del name_hint
    product = normalize_product_url(url) or url
    if not is_verified_singles_url(product):
        return None
    key = product_sku_key(product)
    if key is None:
        return _unique_card_for_uncoded_product(
            conn, product, cards_by_name=cards_by_name
        )
    grouped = groups if groups is not None else grouped_expansion_skus(conn)
    if len(grouped.get(key, [])) >= 2:
        return None
    coded = singles_code_and_number(product)
    if not coded:
        return None
    _code, number = coded
    expansion_slug = key[0]
    product_path = product_slug(product).lower()
    slug_number = str(number).lstrip("0") or "0"
    if not product_path or not slug_number:
        return None
    hits: list[sqlite3.Row] = []
    rows = (
        cards_by_number.get(slug_number, [])
        if cards_by_number is not None
        else conn.execute(
            """
            SELECT * FROM cards
            WHERE cardmarket_verified = 0
               OR cardmarket_url IS NULL
               OR cardmarket_url = ''
            """
        ).fetchall()
    )
    for row in rows:
        card_name = latin_name_slug(str(row["name"] or ""))
        if not name_fits_product_slug(card_name, product_path):
            continue
        card_number = collector_digits(str(row["collector_number"] or "")).lstrip(
            "0"
        ) or "0"
        if card_number != slug_number:
            continue
        if not set_fits_expansion(
            str(row["set_id"] or ""),
            str(row["set_name"] or ""),
            expansion_slug,
        ):
            continue
        hits.append(row)
    if len(hits) != 1:
        return None
    return hits[0]


def _touch_expansion_crawl(
    conn: sqlite3.Connection,
    *,
    expansion: str = "",
    expansion_id: str = "",
    complete: bool = False,
) -> None:
    slug = str(expansion or "").strip()
    ident = str(expansion_id or "").strip()
    keys = [key for key in (ident, slug) if key]
    if not keys:
        return
    stamp = datetime_now()
    products = 0
    if slug:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM cardmarket_expansion_products WHERE expansion = ?",
            (slug,),
        ).fetchone()
        products = int(row["n"] if row is not None else 0)
    for key in keys:
        conn.execute(
            """
            INSERT INTO cardmarket_expansion_crawls (
                key, expansion, expansion_id, products, complete, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                expansion = COALESCE(NULLIF(excluded.expansion, ''), cardmarket_expansion_crawls.expansion),
                expansion_id = COALESCE(NULLIF(excluded.expansion_id, ''), cardmarket_expansion_crawls.expansion_id),
                products = MAX(cardmarket_expansion_crawls.products, excluded.products),
                complete = CASE
                    WHEN excluded.complete > 0 THEN 1
                    ELSE cardmarket_expansion_crawls.complete
                END,
                updated_at = excluded.updated_at
            """,
            (key, slug, ident, products, 1 if complete else 0, stamp),
        )


def _backfill_expansion_crawls(conn: sqlite3.Connection) -> None:
    grouped = conn.execute(
        """
        SELECT expansion, COUNT(*) AS products, MAX(rowid) AS last_row
        FROM cardmarket_expansion_products
        WHERE expansion IS NOT NULL AND TRIM(expansion) != ''
        GROUP BY expansion
        """
    ).fetchall()
    if not grouped:
        return
    latest = max(grouped, key=lambda row: int(row["last_row"] or 0))
    latest_slug = str(latest["expansion"] or "")
    for row in grouped:
        slug = str(row["expansion"] or "")
        if not slug:
            continue
        marked = conn.execute(
            "SELECT complete FROM cardmarket_expansion_crawls WHERE key = ?",
            (slug,),
        ).fetchone()
        already_done = bool(marked["complete"]) if marked is not None else False
        done = already_done or slug != latest_slug
        _touch_expansion_crawl(conn, expansion=slug, complete=done)
    conn.commit()


def list_expansion_crawls(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    _backfill_expansion_crawls(conn)
    rows = conn.execute(
        """
        SELECT key, expansion, expansion_id, products, complete, updated_at
        FROM cardmarket_expansion_crawls
        ORDER BY updated_at DESC
        """
    ).fetchall()
    return [
        {
            "key": str(row["key"] or ""),
            "expansion": str(row["expansion"] or ""),
            "expansion_id": str(row["expansion_id"] or ""),
            "products": int(row["products"] or 0),
            "complete": bool(row["complete"]),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in rows
    ]


def mark_expansion_complete(
    conn: sqlite3.Connection,
    *,
    expansion: str = "",
    expansion_id: str = "",
    page_url: str = "",
) -> dict[str, Any]:
    slug = str(expansion or "").strip() or _expansion_from_url(page_url)
    ident = str(expansion_id or "").strip()
    url_slug = _expansion_from_url(page_url)
    _touch_expansion_crawl(conn, expansion=slug, expansion_id=ident, complete=True)
    if url_slug and url_slug != slug:
        _touch_expansion_crawl(conn, expansion=url_slug, expansion_id=ident, complete=True)
    conn.commit()
    return {
        "expansion": slug,
        "expansion_id": ident,
        "complete": True,
        "stored": 0,
        "linked": 0,
        "unmatched": 0,
        "products": 0,
        "source": "crawl",
    }


def import_expansion_products(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    page_url: str,
    products: list[dict[str, Any]],
    source: str = "page",
    replace: bool = False,
) -> dict[str, Any]:
    stamp = datetime_now()
    expansion = _expansion_from_url(page_url)
    stored_n = 0
    linked: list[dict[str, str]] = []
    unmatched: list[str] = []
    seen: set[str] = set()
    for item in products:
        raw = item.get("url") if isinstance(item, dict) else item
        name = str(item.get("name") or "") if isinstance(item, dict) else ""
        product = normalize_product_url(str(raw or ""))
        if not product or product in seen or not is_verified_singles_url(product):
            continue
        seen.add(product)
        if not expansion:
            expansion = _expansion_from_url(product)
        row = _unique_card_for_product(conn, product, name)
        card_id = str(row["id"]) if row is not None else None
        matched = 0
        if row is not None:
            map_card_product(
                conn,
                data_dir,
                card_id or "",
                product,
                provenance="helper-expansion",
                commit=False,
            )
            matched = 1
            linked.append({"card_id": card_id or "", "url": product})
        else:
            unmatched.append(product)
        conn.execute(
            """
            INSERT INTO cardmarket_expansion_products (
                url, expansion, name, source, page_url, card_id, matched, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                expansion = excluded.expansion,
                name = COALESCE(excluded.name, cardmarket_expansion_products.name),
                source = excluded.source,
                page_url = excluded.page_url,
                card_id = COALESCE(excluded.card_id, cardmarket_expansion_products.card_id),
                matched = CASE
                    WHEN excluded.matched > cardmarket_expansion_products.matched
                    THEN excluded.matched
                    ELSE cardmarket_expansion_products.matched
                END,
                imported_at = excluded.imported_at
            """,
            (
                product,
                expansion,
                name,
                source if source in {"page", "crawl"} else "page",
                normalize_product_url(page_url) or page_url,
                card_id,
                matched,
                stamp,
            ),
        )
        stored_n += 1
    removed = 0
    if replace and expansion and seen:
        for row in conn.execute(
            "SELECT url FROM cardmarket_expansion_products WHERE expansion = ?",
            (expansion,),
        ).fetchall():
            url = str(row["url"] or "")
            if url and url not in seen:
                conn.execute("DELETE FROM cardmarket_expansion_products WHERE url = ?", (url,))
                removed += 1
    _touch_expansion_crawl(conn, expansion=expansion or "", complete=bool(replace and seen))
    clear_ambiguous_auto_links(conn)
    conn.commit()
    dump_dir = Path(data_dir) / "expansion-imports"
    dump_dir.mkdir(parents=True, exist_ok=True)
    dump_path = dump_dir / f"{expansion or 'set'}-{source}-{stamp.replace(':', '').replace('+', '')}.json"
    dump_path.write_text(
        json.dumps(
            {
                "page_url": page_url,
                "source": source,
                "expansion": expansion,
                "imported_at": stamp,
                "products": list(seen),
                "linked": linked,
                "unmatched": unmatched,
            },
            indent=2,
        )
        + "\n"
    )
    return {
        "expansion": expansion,
        "source": source,
        "products": len(seen),
        "stored": stored_n,
        "linked": len(linked),
        "unmatched": len(unmatched),
        "links": linked,
        "unmatched_urls": unmatched[:20],
        "removed": removed,
        "replaced": bool(replace and seen),
        "dump": str(dump_path),
    }


def expansion_imports_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "expansion-imports"


def ingest_expansion_dumps(conn: sqlite3.Connection, data_dir: Path) -> int:
    dump_dir = expansion_imports_dir(data_dir)
    if not dump_dir.is_dir():
        return 0
    added = 0
    for path in sorted(dump_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        page_url = str(payload.get("page_url") or "")
        source = str(payload.get("source") or "page")
        if source not in {"page", "crawl"}:
            source = "page"
        expansion = str(payload.get("expansion") or _expansion_from_url(page_url))
        imported_at = str(payload.get("imported_at") or datetime_now())
        for item in payload.get("products") or []:
            if isinstance(item, dict):
                raw = item.get("url")
                name = str(item.get("name") or "")
            else:
                raw = item
                name = ""
            product = normalize_product_url(str(raw or ""))
            if not product or not is_verified_singles_url(product):
                continue
            if not expansion:
                expansion = _expansion_from_url(product)
            cursor = conn.execute(
                """
                INSERT INTO cardmarket_expansion_products (
                    url, expansion, name, source, page_url, card_id, matched, imported_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 0, ?)
                ON CONFLICT(url) DO NOTHING
                """,
                (
                    product,
                    expansion,
                    name,
                    source,
                    normalize_product_url(page_url) or page_url,
                    imported_at,
                ),
            )
            added += int(cursor.rowcount or 0)
    return added


def link_stored_expansion_products(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    codes: set[str] | frozenset[str] | None = None,
) -> dict[str, int]:
    wanted = {code.upper() for code in codes} if codes is not None else None
    rows = conn.execute(
        """
        SELECT url, name
        FROM cardmarket_expansion_products
        WHERE matched = 0 OR card_id IS NULL OR card_id = ''
        ORDER BY url
        """
    ).fetchall()
    print(f"unique-link unmatched products {len(rows)}", flush=True)
    groups = grouped_expansion_skus(conn)
    cards_by_number = unmatched_cards_by_collector(conn)
    cards_by_name = unmatched_cards_by_name(conn)
    linked = 0
    unmatched = 0
    skipped_variants = 0
    considered = 0
    for row in rows:
        url = str(row["url"] or "")
        coded = singles_code_and_number(url)
        if wanted is not None and (
            coded is None or coded[0].upper() not in wanted
        ):
            continue
        considered += 1
        if considered == 1 or considered % 2000 == 0:
            print(
                f"  {considered} considered, linked {linked}, "
                f"variant-sku skipped {skipped_variants}",
                flush=True,
            )
        key = product_sku_key(url)
        if key is not None and len(groups.get(key, [])) >= 2:
            skipped_variants += 1
            unmatched += 1
            continue
        hit = _unique_card_for_product(
            conn,
            url,
            str(row["name"] or ""),
            groups=groups,
            cards_by_number=cards_by_number,
            cards_by_name=cards_by_name,
        )
        if hit is None:
            unmatched += 1
            continue
        card_id = str(hit["id"])
        map_card_product(
            conn,
            data_dir,
            card_id,
            url,
            provenance="helper-expansion",
            commit=False,
        )
        conn.execute(
            """
            UPDATE cardmarket_expansion_products
            SET card_id = ?, matched = 1
            WHERE url = ?
            """,
            (card_id, url),
        )
        number = coded[1] if coded else collector_digits(
            str(hit["collector_number"] or "")
        )
        _drop_indexed_card(cards_by_number, card_id, str(number).lstrip("0") or "0")
        _drop_indexed_name(cards_by_name, card_id, latin_name_slug(str(hit["name"] or "")))
        linked += 1
    print(
        f"  done considered {considered}, linked {linked}, "
        f"variant-sku skipped {skipped_variants}",
        flush=True,
    )
    return {
        "linked": linked,
        "unmatched": unmatched,
        "skipped_variants": skipped_variants,
        "considered": considered,
    }


def link_japanese_listing_codes(
    conn: sqlite3.Connection,
    data_dir: Path,
) -> dict[str, int]:
    """Attach unique (set collector) Singles URLs to Japanese prints only."""
    ja_by_key: dict[tuple[str, str], list[sqlite3.Row]] = {}
    rows = conn.execute(
        """
        SELECT id, name, set_id, collector_number, language,
               cardmarket_url, cardmarket_provenance, cardmarket_verified
        FROM cards
        WHERE language = 'ja' AND id LIKE 'ja:%'
        """
    ).fetchall()
    for row in rows:
        set_id = str(row["set_id"] or "").strip()
        collector = str(row["collector_number"] or "").strip()
        if not set_id or not collector:
            continue
        ja_by_key.setdefault((set_id.lower(), collector), []).append(row)

    products_by_key: dict[tuple[str, str], list[sqlite3.Row]] = {}
    products = conn.execute(
        """
        SELECT url, name, card_id, matched
        FROM cardmarket_expansion_products
        WHERE matched = 0 OR card_id IS NULL OR card_id = ''
        ORDER BY url
        """
    ).fetchall()
    skipped = 0
    for product in products:
        url = str(product["url"] or "")
        if not is_verified_singles_url(url):
            skipped += 1
            continue
        parsed = listing_set_collector(str(product["name"] or ""))
        if parsed is None:
            skipped += 1
            continue
        set_id, collector = parsed
        products_by_key.setdefault((set_id.lower(), collector), []).append(product)

    linked = 0
    replaced = 0
    already = 0
    ambiguous = 0
    for key, candidates in products_by_key.items():
        cards = ja_by_key.get(key, [])
        if len(cards) != 1 or len(candidates) != 1:
            if cards and candidates:
                ambiguous += 1
            continue
        card = cards[0]
        product = candidates[0]
        url = normalize_product_url(str(product["url"] or "")) or str(product["url"] or "")
        provenance = str(card["cardmarket_provenance"] or "")
        if provenance in _PROTECTED_PROVENANCE:
            skipped += 1
            continue
        current = str(card["cardmarket_url"] or "").strip()
        if current == url:
            conn.execute(
                """
                UPDATE cardmarket_expansion_products
                SET card_id = ?, matched = 1
                WHERE url = ?
                """,
                (str(card["id"]), url),
            )
            already += 1
            continue
        if current:
            conn.execute(
                """
                UPDATE cardmarket_expansion_products
                SET card_id = NULL, matched = 0
                WHERE url = ?
                  AND (card_id = ? OR card_id IS NULL OR card_id = '')
                """,
                (current, str(card["id"])),
            )
            replaced += 1
        conn.execute(
            """
            UPDATE cards
            SET cardmarket_url = ?,
                cardmarket_verified = 1,
                cardmarket_provenance = ?,
                cardmarket_verified_at = ?
            WHERE id = ?
            """,
            (url, JA_COLLECTOR_PROVENANCE, datetime_now(), str(card["id"])),
        )
        conn.execute(
            """
            UPDATE cardmarket_expansion_products
            SET card_id = ?, matched = 1
            WHERE url = ?
            """,
            (str(card["id"]), url),
        )
        linked += 1
    print(
        f"ja-collector linked {linked}, replaced {replaced}, "
        f"already {already}, ambiguous {ambiguous}, skipped {skipped}",
        flush=True,
    )
    return {
        "linked": linked,
        "replaced": replaced,
        "already": already,
        "ambiguous": ambiguous,
        "skipped": skipped,
    }


def apply_cardmarket_links(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    codes: set[str] | frozenset[str] | None = None,
) -> dict[str, int]:
    """Write helper maps and stored set-list URLs onto catalogue cards."""
    dumps = ingest_expansion_dumps(conn, data_dir)
    maps = apply_helper_maps(conn, data_dir)
    mismatched = clear_mismatched_auto_links(conn)
    expansion = link_stored_expansion_products(conn, data_dir, codes=codes)
    cleared = clear_ambiguous_auto_links(conn)
    ja_codes = link_japanese_listing_codes(conn, data_dir)
    conn.commit()
    return {
        "dumps": dumps,
        "helper_maps": maps,
        "expansion_linked": expansion["linked"],
        "expansion_unmatched": expansion["unmatched"],
        "skipped_variants": expansion["skipped_variants"],
        "considered": expansion["considered"],
        "mismatched_cleared": mismatched,
        "ambiguous_cleared": cleared,
        "ja_collector_linked": ja_codes["linked"],
        "ja_collector_replaced": ja_codes["replaced"],
    }


def _decode_prices(raw: Any) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def snapshot_record(conn: sqlite3.Connection, url: str | None) -> dict[str, Any] | None:
    key = normalize_product_url(url)
    if not key:
        return None
    row = conn.execute(
        "SELECT * FROM cardmarket_snapshots WHERE url = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    keys = set(row.keys())
    prices = _decode_prices(row["prices_json"])
    return {
        "url": key,
        "prices": prices,
        "fetched_at": str(row["fetched_at"] or "") or None,
        "observed_at": str(row["observed_at"] or "") if "observed_at" in keys else None,
        "parser_version": str(row["parser_version"] or "") if "parser_version" in keys else None,
        "sampled_offer_count": (
            int(row["sampled_offer_count"])
            if "sampled_offer_count" in keys and row["sampled_offer_count"] is not None
            else len(prices)
        ),
        "submission_id": str(row["submission_id"] or "") if "submission_id" in keys else None,
        "empty": not prices,
    }


def snapshot_prices(conn: sqlite3.Connection, url: str | None) -> list[dict[str, Any]]:
    record = snapshot_record(conn, url)
    return list(record["prices"]) if record else []


def write_snapshot(
    conn: sqlite3.Connection,
    url: str,
    prices: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
    parser_version: str | None = None,
    sampled_offer_count: int | None = None,
    submission_id: str | None = None,
    allow_empty: bool = False,
    commit: bool = True,
) -> str:
    if not prices and not allow_empty:
        raise ValueError("Need at least one price")
    key = normalize_product_url(url) or url
    stamp = observed_at or datetime_now()
    existing = snapshot_record(conn, key)
    existing_observed = str((existing or {}).get("observed_at") or "")
    if existing_observed and existing_observed > stamp:
        return key
    conn.execute(
        """
        INSERT INTO cardmarket_snapshots (
            url, prices_json, fetched_at, observed_at, parser_version,
            sampled_offer_count, submission_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            prices_json = excluded.prices_json,
            fetched_at = excluded.fetched_at,
            observed_at = excluded.observed_at,
            parser_version = excluded.parser_version,
            sampled_offer_count = excluded.sampled_offer_count,
            submission_id = excluded.submission_id
        """,
        (
            key,
            json.dumps(prices),
            datetime_now(),
            stamp,
            parser_version,
            sampled_offer_count if sampled_offer_count is not None else len(prices),
            submission_id,
        ),
    )
    if commit:
        conn.commit()
    return key


def save_snapshot(
    conn: sqlite3.Connection, url: str, prices: list[dict[str, Any]]
) -> str:
    return write_snapshot(conn, url, prices, commit=True)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        keys = row.keys()
    except Exception:
        return default
    if key not in keys:
        return default
    return row[key]


def _positive_amount(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return amount if amount > 0 else None
    return None


def prices_from_market(market: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Cardmarket From / Trend / 7-day average (latest published guide)."""
    if not isinstance(market, dict):
        return []
    currency = str(market.get("unit") or "EUR")
    prices: list[dict[str, Any]] = []
    for label, key, holo_key in (
        ("From", "low", "low-holo"),
        ("Trend", "trend", "trend-holo"),
        ("7-day", "avg7", "avg7-holo"),
    ):
        amount = _positive_amount(market.get(key)) or _positive_amount(
            market.get(holo_key)
        )
        if amount is None:
            continue
        prices.append(
            {"label": label, "amount": round(amount, 2), "currency": currency}
        )
    return prices[:3]


def singles_code_and_number(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    match = _PRODUCT_SLUG_RE.search(url)
    if not match:
        return None
    slug = match.group(1)
    promo = _PROMO_SLUG_RE.search(slug)
    coded = promo or _SLUG_CODE_RE.search(slug)
    if not coded:
        return None
    letters, digits = coded.group(1), coded.group(2)
    if len(digits) > 3:
        letters += digits[:-3]
        digits = digits[-3:]
    number = digits.lstrip("0") or "0"
    return letters, number


def tcgdex_price_targets(row: Any) -> list[tuple[str, str]]:
    language = str(_row_value(row, "language") or "en").lower()
    provider = str(_row_value(row, "provider_id") or _row_value(row, "id") or "")
    pid = provider.split(":")[-1]
    set_id = str(_row_value(row, "set_id") or "")
    collector = collector_digits(str(_row_value(row, "collector_number") or ""))
    url = str(_row_value(row, "cardmarket_url") or "")
    seen: list[tuple[str, str]] = []

    def add(lang: str, card_id: str) -> None:
        item = (lang, card_id)
        if card_id and item not in seen:
            seen.append(item)

    parsed = singles_code_and_number(url)
    if parsed:
        code, number = parsed
        add(language, f"{code}-{number}")
        add(language, f"{code.lower()}-{number}")
        add(language, f"{code.upper()}-{number}")
    if pid and not pid.startswith("extra-"):
        add(language, pid)
    if set_id and collector:
        number = collector.lstrip("0") or collector
        add(language, f"{set_id}-{number}")
        add(language, f"{set_id.lower()}-{number}")
        add(language, f"{set_id.upper()}-{number}")
    return seen


def _market_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    pricing = payload.get("pricing")
    if not isinstance(pricing, dict):
        return None
    market = pricing.get("cardmarket")
    return market if isinstance(market, dict) else None


def _prices_from_cache(data_dir: Path, language: str, card_id: str) -> list[dict[str, Any]]:
    path = data_dir / "cache" / "cards" / language / f"{card_id}.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return prices_from_market(_market_from_payload(payload))


def prices_for_row(
    row: Any, *, data_dir: Path | None = None, catalog: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    url = None
    try:
        url = url_for_row(row)
    except Exception:
        url = str(_row_value(row, "cardmarket_url") or "") or None
    if catalog is not None:
        stored = snapshot_prices(catalog, url)
        if stored:
            return stored
    if data_dir is None:
        return []
    for language, tcgdex_id in tcgdex_price_targets(row):
        found = _prices_from_cache(data_dir, language, tcgdex_id)
        if found:
            return found
    return []


def _language_from_cache_path(path: Path, cache_root: Path) -> str:
    try:
        relative = path.relative_to(cache_root)
    except ValueError:
        return "en"
    if relative.parts and relative.parts[0].lower() in LANGUAGE_DIRS:
        return relative.parts[0].lower()
    return "en"


def _update_official(
    conn: sqlite3.Connection,
    mapping: CardmarketMapping,
    provider_id: str,
    language: str,
) -> int:
    prefixed = f"{language}:{provider_id}"
    cursor = conn.execute(
        """
        UPDATE cards
        SET cardmarket_id = ?,
            cardmarket_url = ?,
            cardmarket_verified = ?,
            cardmarket_provenance = ?,
            cardmarket_verified_at = ?
        WHERE language = ?
          AND (id = ? OR id = ? OR provider_id = ?)
        """,
        (
            mapping.product_id,
            mapping.url,
            int(mapping.verified),
            mapping.provenance,
            mapping.verified_at,
            language,
            provider_id,
            prefixed,
            provider_id,
        ),
    )
    return int(cursor.rowcount or 0)


def apply_extra_manifest(conn: sqlite3.Connection, extra_dir: Path) -> int:
    path = extra_dir / "manifest.json"
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    updated = 0
    for card in payload.get("cards") or []:
        if not isinstance(card, dict) or not card.get("id"):
            continue
        mapping = mapping_from_manifest(card)
        if not mapping.url and mapping.product_id is None:
            continue
        cursor = conn.execute(
            """
            UPDATE cards
            SET cardmarket_id = ?,
                cardmarket_url = ?,
                cardmarket_verified = ?,
                cardmarket_provenance = ?,
                cardmarket_verified_at = ?
            WHERE id = ?
            """,
            (
                mapping.product_id,
                mapping.url,
                int(mapping.verified),
                mapping.provenance,
                mapping.verified_at,
                str(card["id"]),
            ),
        )
        updated += int(cursor.rowcount or 0)
    return updated


def sync_cardmarket_links(data_dir: Path, conn: sqlite3.Connection) -> int:
    updated = 0
    cache_root = data_dir / "cache" / "cards"
    if cache_root.is_dir():
        for path in sorted(cache_root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            language = _language_from_cache_path(path, cache_root)
            mapping = mapping_from_payload(payload, language=language)
            if mapping.product_id is None and not mapping.url:
                continue
            provider_id = str(payload.get("id") or path.stem)
            updated += _update_official(conn, mapping, provider_id, language)

    extra_dir = Path(os.environ.get("EXTRA_CARDS_DIR", "/extra-cards"))
    updated += apply_extra_manifest(conn, extra_dir)
    updated += apply_helper_maps(conn, data_dir)
    conn.commit()
    return updated

