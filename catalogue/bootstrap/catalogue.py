from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import httpx

from app.cardmarket import apply_cardmarket_links, mapping_from_payload
from app.db import connect, coverage, coverage_by_language, init_catalog
from bootstrap.download import download_file
from bootstrap.pins import TCGDEX_ASSETS, TCGDEX_BASE, TPC_BASE

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_ENERGY_LOCAL_IDS = ("DAR", "FIG", "FIR", "GRA", "LIG", "MET", "PSY", "WAT")
_LISTING_FROM_RE = re.compile(r"\s*From\s+\d", re.I)
_SET_LOCK = threading.Lock()


def _sets_filter() -> set[str] | None:
    raw = os.environ.get("CATALOGUE_SETS", "base1,sv01,swsh3")
    if raw.strip().lower() == "all":
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def _languages() -> list[str]:
    raw = os.environ.get("TCGDEX_LANGUAGES") or os.environ.get("TCGDEX_LANGUAGE", "en")
    languages: list[str] = []
    for item in raw.split(","):
        code = item.strip().lower().replace("_", "-")
        if code and code not in languages:
            languages.append(code)
    return languages or ["en"]


def _image_url(base: str | None, quality: str) -> str | None:
    if not base:
        return None
    return f"{base}/{quality}.webp"


def infer_serie_id(set_id: str) -> str:
    match = re.match(r"^([A-Za-z]+)", str(set_id or "").strip())
    return match.group(1) if match else str(set_id or "").strip()


def serie_id_from_set(set_info: dict | None, set_id: str = "") -> str:
    info = set_info or {}
    serie = info.get("serie")
    if isinstance(serie, dict) and serie.get("id"):
        return str(serie["id"])
    if isinstance(serie, str) and serie.strip():
        return serie.strip()
    return infer_serie_id(set_id or str(info.get("id") or ""))


def cdn_image_base(language: str, serie_id: str, set_id: str, local_id: str) -> str:
    return f"{TCGDEX_ASSETS}/{language}/{serie_id}/{set_id}/{local_id}"


def cdn_image_url(
    language: str,
    serie_id: str,
    set_id: str,
    local_id: str,
    quality: str = "high",
) -> str:
    return f"{cdn_image_base(language, serie_id, set_id, local_id)}/{quality}.webp"


def cdn_base_from_url(url: str, quality: str) -> str:
    suffix = f"/{quality}.webp"
    if url.endswith(suffix):
        return url[: -len(suffix)]
    return url.rsplit("/", 1)[0]


def local_id_cdn_candidates(local_id: str) -> list[str]:
    raw = str(local_id or "").strip()
    tokens: list[str] = []

    def add(token: str) -> None:
        if token and token not in tokens:
            tokens.append(token)

    add(raw)
    if raw.isdigit():
        add(raw.zfill(3))
        add(raw.zfill(2))
        add(str(int(raw)))
    return tokens


def official_card_count(set_info: dict | None) -> int:
    counts = (set_info or {}).get("cardCount") or {}
    for key in ("official", "total", "normal"):
        try:
            value = int(counts.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def set_id_from_brief(brief: dict) -> str:
    set_info = brief.get("set")
    if isinstance(set_info, dict) and set_info.get("id"):
        return str(set_info["id"])
    provider_id = str(brief.get("id") or "")
    if "-" in provider_id:
        return provider_id.rsplit("-", 1)[0]
    return ""


def listing_card_name(label: str) -> str:
    text = _LISTING_FROM_RE.split(str(label or ""), maxsplit=1)[0].strip()
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text


def listing_name_for(conn, set_id: str, local_id: str) -> str | None:
    if conn is None or not set_id or not local_id:
        return None
    raw = str(local_id).strip()
    digits = raw.lstrip("0") or "0"
    numbers = {raw, digits}
    if raw.isdigit():
        numbers.add(raw.zfill(3))
    for sid in {set_id, set_id.lower(), set_id.upper()}:
        for number in numbers:
            row = conn.execute(
                """
                SELECT name FROM cardmarket_expansion_products
                WHERE name LIKE ?
                LIMIT 1
                """,
                (f"%({sid} {number})%",),
            ).fetchone()
            if row and row["name"]:
                name = listing_card_name(str(row["name"]))
                if name:
                    return name
    return None


def cdn_asset_exists(client: httpx.Client, url: str) -> bool:
    try:
        response = client.head(url)
    except httpx.RequestError:
        return False
    if response.status_code == 200:
        return True
    if response.status_code in {404, 410}:
        return False
    try:
        with client.stream("GET", url) as response:
            return response.status_code == 200
    except httpx.RequestError:
        return False


def first_cdn_image_url(
    client: httpx.Client,
    language: str,
    serie_id: str,
    set_id: str,
    local_id: str,
    quality: str = "high",
) -> str | None:
    if not (language and serie_id and set_id and local_id):
        return None
    for token in local_id_cdn_candidates(local_id):
        url = cdn_image_url(language, serie_id, set_id, token, quality)
        if cdn_asset_exists(client, url):
            return url
    return None


def ensure_set_payload(
    client: httpx.Client,
    language: str,
    set_id: str,
    sets: dict,
) -> dict:
    if not set_id:
        return {}
    with _SET_LOCK:
        cached = sets.get(set_id)
        if isinstance(cached, dict):
            serie = cached.get("serie")
            if isinstance(serie, dict) and serie.get("id"):
                return cached
            if isinstance(serie, str) and serie.strip():
                return cached
    payload = _get_json(client, f"{TCGDEX_BASE}/{language}/sets/{quote(set_id, safe='')}")
    if isinstance(payload, dict):
        with _SET_LOCK:
            sets[set_id] = payload
        return payload
    return cached if isinstance(cached, dict) else {}


def resolve_card_cdn_url(
    client: httpx.Client,
    language: str,
    card: dict,
    sets: dict,
    quality: str,
) -> str | None:
    existing = _image_url(card.get("image") if isinstance(card.get("image"), str) else None, quality)
    if existing:
        return existing
    provider_id = str(card.get("id") or "")
    set_info = card.get("set") if isinstance(card.get("set"), dict) else {}
    set_id = str(set_info.get("id") or set_id_from_brief(card) or "")
    local_id = str(
        card.get("localId")
        or (provider_id.rsplit("-", 1)[-1] if "-" in provider_id else "")
    )
    full = ensure_set_payload(client, language, set_id, sets)
    if full:
        set_info = {**full, **set_info, "id": set_id or full.get("id")}
        card["set"] = set_info
    serie = serie_id_from_set(set_info, set_id)
    url = first_cdn_image_url(client, language, serie, set_id, local_id, quality)
    if not url:
        return None
    card["image"] = cdn_base_from_url(url, quality)
    return url


def stub_card_from_brief(
    brief: dict,
    language: str,
    *,
    client: httpx.Client,
    sets: dict,
    quality: str,
) -> dict | None:
    provider_id = str(brief.get("id") or "")
    if not provider_id:
        return None
    set_info = brief.get("set") if isinstance(brief.get("set"), dict) else {}
    set_id = str(set_info.get("id") or set_id_from_brief(brief) or "")
    local_id = str(
        brief.get("localId")
        or (provider_id.rsplit("-", 1)[-1] if "-" in provider_id else "")
    )
    card = {
        "id": provider_id,
        "localId": local_id,
        "name": brief.get("name") or "Unknown",
        "image": None,
        "set": set_info or {"id": set_id},
        "category": brief.get("category"),
        "rarity": brief.get("rarity"),
        "illustrator": brief.get("illustrator"),
        "variants": brief.get("variants") or {},
    }
    if resolve_card_cdn_url(client, language, card, sets, quality) is None:
        return None
    return card


def discover_cdn_local_ids(
    client: httpx.Client,
    language: str,
    set_info: dict,
    quality: str = "high",
) -> list[str]:
    set_id = str(set_info.get("id") or "")
    serie = serie_id_from_set(set_info, set_id)
    official = official_card_count(set_info)
    # 1..official is not always contiguous (ja S8a-028 404s, 029 exists).
    upper = max(official, 1) + 16
    found: list[str] = []
    for number in range(1, upper + 1):
        url = first_cdn_image_url(
            client, language, serie, set_id, str(number), quality
        )
        if not url:
            continue
        token = next(
            (
                candidate
                for candidate in local_id_cdn_candidates(str(number))
                if url.endswith(f"/{candidate}/{quality}.webp")
            ),
            str(number).zfill(3),
        )
        found.append(token)
    for token in _ENERGY_LOCAL_IDS:
        url = first_cdn_image_url(client, language, serie, set_id, token, quality)
        if url:
            found.append(token)
    return found


def fill_empty_set_briefs(
    client: httpx.Client,
    language: str,
    allowed: set[str] | None,
    briefs: list[dict],
    sets: dict,
    quality: str = "high",
) -> list[dict]:
    listed = {set_id_from_brief(item) for item in briefs if set_id_from_brief(item)}
    set_ids = sorted(allowed) if allowed is not None else sorted(str(key) for key in sets)
    added = 0
    for set_id in set_ids:
        if set_id in listed:
            continue
        payload = ensure_set_payload(client, language, set_id, sets)
        if not payload:
            continue
        cards = [item for item in (payload.get("cards") or []) if isinstance(item, dict)]
        if cards:
            briefs.extend(cards)
            listed.add(set_id)
            added += len(cards)
            continue
        if allowed is None and official_card_count(payload) <= 0:
            continue
        local_ids = discover_cdn_local_ids(client, language, payload, quality=quality)
        for local_id in local_ids:
            briefs.append(
                {
                    "id": f"{set_id}-{local_id}",
                    "localId": local_id,
                    "name": None,
                    "set": payload,
                }
            )
        if local_ids:
            listed.add(set_id)
            added += len(local_ids)
            print(f"  cdn-fill {language}:{set_id} {len(local_ids)} files")
    if added:
        print(f"  cdn-fill {language} added {added} missing cards")
    return briefs


def backfill_missing_cdn_images(
    conn,
    client: httpx.Client,
    data_dir: Path,
    *,
    languages: list[str],
    quality: str,
    concurrency: int,
) -> dict[str, int]:
    if os.environ.get("TCGDEX_CDN_BACKFILL", "1").strip().lower() in {"0", "false", "no"}:
        return {"probed": 0, "found": 0, "downloaded": 0, "failed": 0}
    images_dir = data_dir / "reference-images"
    sql = """
        SELECT id, provider_id, language, set_id, collector_number, image_path
        FROM cards
        WHERE id NOT LIKE 'extra-%'
          AND (remote_image_url IS NULL OR remote_image_url = '')
          AND IFNULL(set_id, '') != ''
          AND IFNULL(collector_number, '') != ''
    """
    params: tuple = ()
    if languages:
        sql += f" AND language IN ({','.join('?' * len(languages))})"
        params = tuple(languages)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {"probed": 0, "found": 0, "downloaded": 0, "failed": 0}
    sets_by_lang: dict[str, dict] = {}
    found = 0
    downloaded = 0
    failed = 0
    db_lock = threading.Lock()

    def work(row) -> None:
        nonlocal found, downloaded, failed
        card_id = str(row["id"])
        language = str(row["language"] or "en")
        card = {
            "id": str(row["provider_id"] or ""),
            "localId": str(row["collector_number"] or ""),
            "image": None,
            "set": {"id": str(row["set_id"] or "")},
        }
        url = resolve_card_cdn_url(
            client,
            language,
            card,
            sets_by_lang.setdefault(language, {}),
            quality,
        )
        if not url:
            return
        dest = images_dir / language / f"{row['provider_id']}.webp"
        image_path = str(row["image_path"] or "")
        has_file = bool(image_path) and Path(image_path).is_file()
        saved_path = image_path if has_file else None
        download_failed = False
        if not has_file:
            try:
                download_file(url, dest, client=client)
                saved_path = str(dest)
            except Exception as exc:  # noqa: BLE001
                print(f"  skip image {card_id}: {exc}")
                download_failed = True
        with db_lock:
            found += 1
            if saved_path and not download_failed:
                if not has_file:
                    downloaded += 1
                conn.execute(
                    """
                    UPDATE cards
                    SET remote_image_url = ?, image_path = ?, has_image = 1
                    WHERE id = ?
                    """,
                    (url, saved_path, card_id),
                )
            else:
                if download_failed:
                    failed += 1
                conn.execute(
                    "UPDATE cards SET remote_image_url = ? WHERE id = ?",
                    (url, card_id),
                )

    print(f"  cdn-backfill probe {len(rows)} cards missing remote URLs")
    with ThreadPoolExecutor(max_workers=max(concurrency, 1)) as pool:
        futures = [pool.submit(work, row) for row in rows]
        for index, future in enumerate(as_completed(futures), start=1):
            future.result()
            if index % 100 == 0:
                with db_lock:
                    conn.commit()
                print(f"  cdn-backfill {index}/{len(rows)}")
    conn.commit()
    print(
        f"  cdn-backfill found {found}/{len(rows)}, "
        f"downloaded {downloaded}, failed {failed}"
    )
    return {
        "probed": len(rows),
        "found": found,
        "downloaded": downloaded,
        "failed": failed,
    }


_TPC_COLLECTOR_RE = re.compile(
    r"&nbsp;([A-Za-z0-9]+)&nbsp;/&nbsp;([A-Za-z0-9.\-]+)&nbsp;"
)
_TPC_HEADERS = {
    "User-Agent": "scanapp-catalogue/1.0",
    "Referer": f"{TPC_BASE}/card-search/index.php",
}


def tpc_abs_url(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    if raw.startswith("https://") or raw.startswith("http://"):
        return raw
    if raw.startswith("//"):
        return "https:" + raw
    if not raw.startswith("/"):
        raw = "/" + raw
    return TPC_BASE + raw


def parse_tpc_collector(html: str) -> tuple[str, str] | None:
    match = _TPC_COLLECTOR_RE.search(html or "")
    if match is None:
        return None
    collector = match.group(1).strip()
    set_id = match.group(2).strip()
    if not collector or not set_id:
        return None
    return collector, set_id


_TPC_RETRY_STATUSES = {403, 429, 500, 502, 503, 504}


def tpc_get(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    retries: int = 3,
    timeout: float = 15.0,
) -> httpx.Response:
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(max(retries, 1)):
        retry_after = False
        try:
            response = client.get(
                url, params=params, headers=_TPC_HEADERS, timeout=timeout
            )
            if response.status_code in _TPC_RETRY_STATUSES:
                last_error = httpx.HTTPStatusError(
                    f"{response.status_code} {url}",
                    request=response.request,
                    response=response,
                )
                retry_after = True
            else:
                response.raise_for_status()
                return response
        except httpx.RequestError as exc:
            last_error = exc
            retry_after = True
        if retry_after and attempt + 1 < retries:
            print(f"  retry tpc {attempt + 1}/{retries} {url}")
            time.sleep(delay)
            delay = min(delay * 2, 20)
    raise last_error or RuntimeError(f"Failed TPC GET {url}")


def tpc_list_name(item: dict) -> str:
    return str(item.get("cardNameAltText") or item.get("cardNameViewText") or "").strip()


def tpc_list_image(item: dict) -> str:
    return tpc_abs_url(str(item.get("cardThumbFile") or ""))


def tpc_list_expansion(client: httpx.Client, expansion: str) -> list[dict]:
    cards: list[dict] = []
    page = 1
    max_page = 1
    while page <= max_page:
        response = tpc_get(
            client,
            f"{TPC_BASE}/card-search/resultAPI.php",
            params={
                "keyword": "",
                "sm_and_keyword": "true",
                "regulation_sidebar_form": "all",
                "illust": "",
                "pg": expansion,
                "page": page,
            },
        )
        payload = response.json()
        if int(payload.get("result") or 0) != 1:
            break
        batch = payload.get("cardList") or []
        if not isinstance(batch, list):
            break
        cards.extend(item for item in batch if isinstance(item, dict) and item.get("cardID"))
        try:
            max_page = int(payload.get("maxPage") or page)
        except (TypeError, ValueError):
            max_page = page
        if not batch:
            break
        page += 1
    return cards


def tpc_card_record(client: httpx.Client, item: dict) -> dict | None:
    card_id = str(item.get("cardID") or "").strip()
    if not card_id:
        return None
    response = tpc_get(
        client,
        f"{TPC_BASE}/card-search/details.php/card/{card_id}",
        retries=2,
        timeout=12.0,
    )
    parsed = parse_tpc_collector(response.text)
    if parsed is None:
        return None
    collector, set_id = parsed
    image = tpc_list_image(item)
    if not image:
        match = re.search(r"/assets/images/card_images/large/[^\"']+", response.text)
        image = tpc_abs_url(match.group(0) if match else "")
    if not image:
        return None
    return {
        "tpc_id": card_id,
        "collector": collector,
        "set_id": set_id,
        "name": tpc_list_name(item),
        "image_url": image,
    }


def _tpc_index_key(set_id: str, collector: str) -> tuple[str, str]:
    return str(set_id or "").strip().lower(), str(collector or "").strip()


def _pick_tpc_record(records: list[dict], name: str) -> dict | None:
    if not records:
        return None
    unique: list[dict] = []
    seen: set[str] = set()
    for item in records:
        url = str(item.get("image_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(item)
    if len(unique) == 1:
        return unique[0]
    wanted = str(name or "").strip()
    named = [item for item in unique if item.get("name") == wanted]
    if len(named) == 1:
        return named[0]
    return None


def _tpc_db_execute(conn, sql: str, params: tuple = ()) -> None:
    delay = 0.2
    for attempt in range(8):
        try:
            conn.execute(sql, params)
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 5)


def backfill_missing_tpc_images(
    conn,
    client: httpx.Client,
    data_dir: Path,
    *,
    languages: list[str],
    concurrency: int,
) -> dict[str, int]:
    if os.environ.get("TPC_IMAGE_BACKFILL", "1").strip().lower() in {"0", "false", "no"}:
        return {"probed": 0, "listed": 0, "found": 0, "downloaded": 0, "failed": 0}
    wanted_langs = [item for item in languages if item.strip().lower() == "ja"]
    if not wanted_langs:
        return {"probed": 0, "listed": 0, "found": 0, "downloaded": 0, "failed": 0}
    conn.execute("PRAGMA busy_timeout=30000")
    images_dir = data_dir / "reference-images"
    rows = conn.execute(
        """
        SELECT id, provider_id, language, set_id, collector_number, name, image_path
        FROM cards
        WHERE language = 'ja'
          AND id LIKE 'ja:%'
          AND id NOT LIKE 'extra-%'
          AND (remote_image_url IS NULL OR remote_image_url = '')
          AND IFNULL(set_id, '') != ''
          AND IFNULL(collector_number, '') != ''
        """
    ).fetchall()
    if not rows:
        return {"probed": 0, "listed": 0, "found": 0, "downloaded": 0, "failed": 0}
    expansions = sorted({str(row["set_id"] or "").strip() for row in rows if row["set_id"]})
    index: dict[tuple[str, str], list[dict]] = {}
    name_index: dict[tuple[str, str], dict] = {}
    listed = 0
    detail_workers = 1
    name_counts: dict[tuple[str, str], int] = {}
    if expansions:
        placeholders = ",".join("?" * len(expansions))
        for row in conn.execute(
            f"""
            SELECT set_id, name
            FROM cards
            WHERE language = 'ja'
              AND id LIKE 'ja:%'
              AND set_id IN ({placeholders})
            """,
            expansions,
        ):
            key = _tpc_index_key(str(row["set_id"] or ""), str(row["name"] or "").strip())
            name_counts[key] = name_counts.get(key, 0) + 1

    def load_record(item: dict) -> dict | None:
        try:
            return tpc_card_record(client, item)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip tpc {item.get('cardID')}: {exc}")
            return None

    for expansion in expansions:
        try:
            cards = tpc_list_expansion(client, expansion)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip tpc set {expansion}: {exc}")
            continue
        if not cards:
            print(f"  tpc-fill {expansion} 0 cards")
            continue
        by_name: dict[str, list[dict]] = {}
        for item in cards:
            by_name.setdefault(tpc_list_name(item), []).append(item)
        unique_names = 0
        ambiguous: list[dict] = []
        for name, items in by_name.items():
            if not name:
                ambiguous.extend(items)
                continue
            images = [tpc_list_image(item) for item in items if tpc_list_image(item)]
            if len(items) == 1 and len(images) == 1:
                name_index[_tpc_index_key(expansion, name)] = {
                    "tpc_id": str(items[0].get("cardID") or ""),
                    "collector": "",
                    "set_id": expansion,
                    "name": name,
                    "image_url": images[0],
                }
                unique_names += 1
            else:
                ambiguous.extend(items)
        print(
            f"  tpc-fill {expansion} {len(cards)} cards, "
            f"{unique_names} unique names, {len(ambiguous)} details"
        )
        listed += len(cards)
        fetch_details = os.environ.get("TPC_FETCH_DETAILS", "1").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        if not ambiguous or not fetch_details:
            if ambiguous and not fetch_details:
                print(f"  tpc-fill {expansion} skip {len(ambiguous)} details")
            continue
        with ThreadPoolExecutor(max_workers=detail_workers) as pool:
            for record in pool.map(load_record, ambiguous):
                if record is None:
                    continue
                key = _tpc_index_key(record["set_id"], record["collector"])
                index.setdefault(key, []).append(record)

    found = 0
    downloaded = 0
    failed = 0
    db_lock = threading.Lock()

    def work(row) -> None:
        nonlocal found, downloaded, failed
        card_id = str(row["id"])
        set_id = str(row["set_id"] or "")
        collector = str(row["collector_number"] or "")
        records: list[dict] = []
        for token in local_id_cdn_candidates(collector):
            records.extend(index.get(_tpc_index_key(set_id, token), []))
        picked = _pick_tpc_record(records, str(row["name"] or ""))
        if picked is None:
            name = str(row["name"] or "").strip()
            name_key = _tpc_index_key(set_id, name)
            if name and name != "Unknown" and name_counts.get(name_key, 0) == 1:
                named = name_index.get(name_key)
                if named is not None:
                    picked = named
        if picked is None:
            return
        url = str(picked["image_url"])
        dest = images_dir / "ja" / f"{row['provider_id']}.jpg"
        image_path = str(row["image_path"] or "")
        has_file = bool(image_path) and Path(image_path).is_file()
        saved_path = image_path if has_file else None
        download_failed = False
        if not has_file:
            try:
                download_file(url, dest, client=client)
                saved_path = str(dest)
            except Exception as exc:  # noqa: BLE001
                print(f"  skip tpc image {card_id}: {exc}")
                download_failed = True
        with db_lock:
            found += 1
            if saved_path and not download_failed:
                if not has_file:
                    downloaded += 1
                _tpc_db_execute(
                    conn,
                    """
                    UPDATE cards
                    SET remote_image_url = ?, image_path = ?, has_image = 1
                    WHERE id = ?
                    """,
                    (url, saved_path, card_id),
                )
            else:
                if download_failed:
                    failed += 1
                _tpc_db_execute(
                    conn,
                    "UPDATE cards SET remote_image_url = ? WHERE id = ?",
                    (url, card_id),
                )

    print(f"  tpc-backfill probe {len(rows)} ja cards missing remote URLs")
    download_workers = max(min(concurrency, 2), 1)
    with ThreadPoolExecutor(max_workers=download_workers) as pool:
        futures = [pool.submit(work, row) for row in rows]
        for index_n, future in enumerate(as_completed(futures), start=1):
            future.result()
            if index_n % 100 == 0:
                with db_lock:
                    try:
                        conn.commit()
                    except sqlite3.OperationalError:
                        time.sleep(1)
                        conn.commit()
                print(f"  tpc-backfill {index_n}/{len(rows)}")
    conn.commit()
    print(
        f"  tpc-backfill found {found}/{len(rows)}, "
        f"listed {listed}, downloaded {downloaded}, failed {failed}"
    )
    return {
        "probed": len(rows),
        "listed": listed,
        "found": found,
        "downloaded": downloaded,
        "failed": failed,
    }


def _card_pk(language: str, provider_id: str) -> str:
    if provider_id.startswith(f"{language}:"):
        return provider_id
    return f"{language}:{provider_id}"


def upsert_card(
    conn,
    *,
    card_id: str,
    provider_id: str,
    name: str,
    set_id: str,
    set_name: str,
    collector_number: str,
    language: str,
    category: str | None,
    rarity: str | None,
    illustrator: str | None,
    variants_json: str,
    image_path: str | None,
    has_image: int,
    cardmarket_id: int | None,
    cardmarket_url: str | None,
    cardmarket_verified: int,
    cardmarket_provenance: str | None,
    cardmarket_verified_at: str | None,
    remote_image_url: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, category, rarity, illustrator, variants_json,
            image_path, has_image, cardmarket_id, cardmarket_url,
            cardmarket_verified, cardmarket_provenance, cardmarket_verified_at,
            remote_image_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            provider_id = excluded.provider_id,
            name = excluded.name,
            set_id = excluded.set_id,
            set_name = excluded.set_name,
            collector_number = excluded.collector_number,
            language = excluded.language,
            category = excluded.category,
            rarity = excluded.rarity,
            illustrator = excluded.illustrator,
            variants_json = excluded.variants_json,
            image_path = COALESCE(excluded.image_path, cards.image_path),
            has_image = CASE
                WHEN excluded.image_path IS NOT NULL THEN excluded.has_image
                WHEN cards.image_path IS NOT NULL THEN cards.has_image
                ELSE excluded.has_image
            END,
            cardmarket_id = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_id
                ELSE excluded.cardmarket_id
            END,
            cardmarket_url = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_url
                ELSE excluded.cardmarket_url
            END,
            cardmarket_verified = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_verified
                ELSE excluded.cardmarket_verified
            END,
            cardmarket_provenance = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_provenance
                ELSE excluded.cardmarket_provenance
            END,
            cardmarket_verified_at = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_verified_at
                ELSE excluded.cardmarket_verified_at
            END,
            remote_image_url = COALESCE(excluded.remote_image_url, cards.remote_image_url)
        """,
        (
            card_id,
            provider_id,
            name,
            set_id,
            set_name,
            collector_number,
            language,
            category,
            rarity,
            illustrator,
            variants_json,
            image_path,
            has_image,
            cardmarket_id,
            cardmarket_url,
            cardmarket_verified,
            cardmarket_provenance,
            cardmarket_verified_at,
            remote_image_url,
        ),
    )
    conn.execute("DELETE FROM cards_fts WHERE id = ?", (card_id,))
    conn.execute(
        "INSERT INTO cards_fts (id, name, set_name, collector_number) VALUES (?, ?, ?, ?)",
        (card_id, name, set_name, collector_number),
    )


def _write_catalogue_version(
    data_dir: Path,
    conn,
    *,
    languages: list[str],
    allowed: set[str] | None,
    replace: bool,
    imported: int,
    indexed: int,
    missing: int,
    per_language: dict[str, int],
) -> str:
    path = data_dir / "catalogue-version.json"
    existing: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}
    if replace:
        version = f"tcgdex-{'+'.join(languages)}-{imported}"
        payload = {
            "catalogue_version": version,
            "language": languages[0] if len(languages) == 1 else languages,
            "languages": per_language,
            "cards": imported,
            "indexed": indexed,
            "missing_images": missing,
            "sets": sorted(allowed) if allowed else "all",
        }
    else:
        cards_n, indexed_n, missing_n = coverage(conn)
        language_counts = {
            str(item["language"]): int(item["cards"])
            for item in coverage_by_language(conn)
        }
        extra_n = int(
            conn.execute(
                "SELECT COUNT(*) FROM cards WHERE id LIKE 'extra-%'"
            ).fetchone()[0]
        )
        official = max(cards_n - extra_n, 0)
        langs = list(language_counts) or languages
        version = f"tcgdex-{'+'.join(langs)}-{official}"
        if extra_n:
            version += f"+extra{extra_n}"
        added = existing.get("added_sets") if isinstance(existing.get("added_sets"), list) else []
        for set_id in sorted(allowed or []):
            if set_id not in added:
                added.append(set_id)
        payload = {
            **existing,
            "catalogue_version": version,
            "language": langs[0] if len(langs) == 1 else langs,
            "languages": language_counts,
            "cards": cards_n,
            "indexed": indexed_n,
            "missing_images": missing_n,
            "extra_cards": extra_n,
            "added_sets": added,
        }
    path.write_text(json.dumps(payload, indent=2))
    return version


def _get_json(client: httpx.Client, url: str) -> dict | list | None:
    response = client.get(url)
    if response.status_code == 404:
        print(f"skip missing {url}")
        return None
    response.raise_for_status()
    return response.json()


def card_detail_url(language: str, card_id: str) -> str:
    return f"{TCGDEX_BASE}/{language}/cards/{quote(str(card_id), safe='')}"


def fetch_card_detail(
    card_id: str,
    language: str,
    *,
    client: httpx.Client,
    retries: int = 4,
) -> dict | None:
    """Load one TCGdex card. Skip 404s (broken list ids like exu-?). Retry blips."""
    url = card_detail_url(language, card_id)
    delay = 1.0
    last_error: Exception | None = None
    for _ in range(max(retries, 1)):
        try:
            response = client.get(url)
        except httpx.RequestError as exc:
            last_error = exc
            time.sleep(delay)
            delay = min(delay * 2, 16)
            continue
        if response.status_code == 404:
            print(f"  skip missing {language}:{card_id}")
            return None
        if response.status_code in _RETRY_STATUSES:
            last_error = httpx.HTTPStatusError(
                f"{response.status_code} {url}",
                request=response.request,
                response=response,
            )
            time.sleep(delay)
            delay = min(delay * 2, 16)
            continue
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else None
    print(f"  skip failed {language}:{card_id}: {last_error}")
    return None


def _briefs_for_language(
    client: httpx.Client,
    language: str,
    allowed: set[str] | None,
) -> tuple[list[dict], dict]:
    sets_payload = _get_json(client, f"{TCGDEX_BASE}/{language}/sets")
    sets = {
        item["id"]: item
        for item in (sets_payload or [])
        if isinstance(item, dict) and item.get("id")
    }
    if allowed:
        briefs: list[dict] = []
        for set_id in sorted(allowed):
            payload = _get_json(client, f"{TCGDEX_BASE}/{language}/sets/{set_id}")
            if not isinstance(payload, dict):
                continue
            sets[set_id] = payload
            briefs.extend(payload.get("cards") or [])
        return briefs, sets
    print(f"fetch {TCGDEX_BASE}/{language}/cards")
    cards_payload = _get_json(client, f"{TCGDEX_BASE}/{language}/cards")
    briefs = [item for item in (cards_payload or []) if isinstance(item, dict)]
    return briefs, sets


_UNSET = object()


def import_catalogue(
    data_dir: Path,
    *,
    replace: bool = True,
    sets: set[str] | None | object = _UNSET,
) -> dict:
    languages = _languages()
    quality = os.environ.get("TCGDEX_IMAGE_QUALITY", "high")
    concurrency = int(os.environ.get("BOOTSTRAP_CONCURRENCY", "8"))
    allowed = _sets_filter() if sets is _UNSET else sets
    images_dir = data_dir / "reference-images"
    cache_dir = data_dir / "cache" / "cards"
    images_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = data_dir / "catalog.sqlite"
    conn = connect(catalog_path)
    init_catalog(conn)
    if replace:
        conn.execute("DELETE FROM cards")
        conn.execute("DELETE FROM cards_fts")

    total_cards = 0
    total_indexed = 0
    missing = 0
    per_language: dict[str, int] = {}

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for language in languages:
            print(f"== catalogue {language}")
            briefs, sets = _briefs_for_language(client, language, allowed)
            briefs = fill_empty_set_briefs(
                client, language, allowed, briefs, sets, quality=quality
            )
            if not briefs:
                print(f"  no cards for {language}")
                per_language[language] = 0
                continue

            lang = language
            set_index = sets

            def load_card(brief: dict) -> dict | None:
                card_id = str(brief.get("id") or "")
                if not card_id:
                    return None
                cache_path = cache_dir / lang / f"{card_id}.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                if cache_path.exists():
                    try:
                        cached = json.loads(cache_path.read_text())
                    except json.JSONDecodeError:
                        cache_path.unlink(missing_ok=True)
                    else:
                        if isinstance(cached, dict):
                            return cached
                body = fetch_card_detail(card_id, lang, client=client)
                if body is None:
                    body = stub_card_from_brief(
                        brief,
                        lang,
                        client=client,
                        sets=set_index,
                        quality=quality,
                    )
                    if body is None:
                        return None
                cache_path.write_text(json.dumps(body))
                return body

            print(f"  enrich {len(briefs)} cards")
            cards: list[dict] = []
            skipped = 0
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(load_card, brief) for brief in briefs]
                for index, future in enumerate(as_completed(futures), start=1):
                    card = future.result()
                    if card is None:
                        skipped += 1
                    else:
                        cards.append(card)
                    if index % 50 == 0:
                        print(f"  details {language} {index}/{len(briefs)}")
            if skipped:
                print(f"  skipped {skipped} missing {language} details")

            print(f"  download {language} reference images")
            lang_dir = images_dir / language
            lang_dir.mkdir(parents=True, exist_ok=True)
            for card in cards:
                provider_id = str(card["id"])
                dest = lang_dir / f"{provider_id}.webp"
                url = resolve_card_cdn_url(client, language, card, sets, quality)
                card["_remote_image_url"] = url
                if not url:
                    missing += 1
                    card["_image_path"] = None
                    continue
                try:
                    download_file(url, dest, client=client)
                    card["_image_path"] = str(dest)
                    total_indexed += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  skip image {language}:{provider_id}: {exc}")
                    missing += 1
                    card["_image_path"] = None

            for card in cards:
                provider_id = str(card["id"])
                card_id = _card_pk(language, provider_id)
                set_info = card.get("set") or sets.get(
                    str(provider_id).rsplit("-", 1)[0], {}
                )
                variants = card.get("variants") or {}
                has_image = 1 if card.get("_image_path") else 0
                mapping = mapping_from_payload(card, language=language)
                set_id = str(set_info.get("id") or "")
                collector = str(card.get("localId") or "")
                name = str(card.get("name") or "").strip() or "Unknown"
                if name == "Unknown":
                    name = listing_name_for(conn, set_id, collector) or name
                upsert_card(
                    conn,
                    card_id=card_id,
                    provider_id=provider_id,
                    name=name,
                    set_id=set_id,
                    set_name=set_info.get("name") or "",
                    collector_number=collector,
                    language=language,
                    category=card.get("category"),
                    rarity=card.get("rarity"),
                    illustrator=card.get("illustrator"),
                    variants_json=json.dumps(variants),
                    image_path=card.get("_image_path"),
                    has_image=has_image,
                    cardmarket_id=mapping.product_id,
                    cardmarket_url=mapping.url,
                    cardmarket_verified=int(mapping.verified),
                    cardmarket_provenance=mapping.provenance,
                    cardmarket_verified_at=mapping.verified_at,
                    remote_image_url=card.get("_remote_image_url"),
                )
            total_cards += len(cards)
            per_language[language] = len(cards)
            conn.commit()
        backfill = backfill_missing_cdn_images(
            conn,
            client,
            data_dir,
            languages=languages,
            quality=quality,
            concurrency=concurrency,
        )
        total_indexed += int(backfill.get("downloaded") or 0)
        tpc_backfill = backfill_missing_tpc_images(
            conn,
            client,
            data_dir,
            languages=languages,
            concurrency=concurrency,
        )
        total_indexed += int(tpc_backfill.get("downloaded") or 0)

    stats = apply_cardmarket_links(conn, data_dir)
    print(
        f"cardmarket maps {stats['helper_maps']}, "
        f"expansion linked {stats['expansion_linked']}, "
        f"unmatched {stats['expansion_unmatched']}"
    )
    version = _write_catalogue_version(
        data_dir,
        conn,
        languages=languages,
        allowed=allowed,
        replace=replace,
        imported=total_cards,
        indexed=total_indexed,
        missing=missing,
        per_language=per_language,
    )
    conn.close()
    print(f"catalogue {total_cards} cards, {total_indexed} images, {missing} missing")
    return {
        "catalogue_version": version,
        "cards": total_cards,
        "indexed": total_indexed,
        "missing_images": missing,
        "languages": per_language,
    }
