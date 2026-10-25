"""Collect private main-photo examples from eBay Browse API search results.

Credentials are read from a local, owner-only env file and are never printed.
Search responses and photos are cached under the gitignored corpus directory.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, ImageOps


API_ROOT = "https://api.ebay.com"
TOKEN_URL = f"{API_ROOT}/identity/v1/oauth2/token"
SEARCH_URL = f"{API_ROOT}/buy/browse/v1/item_summary/search"
DEFAULT_CREDENTIAL_FILE = Path.home() / "WebstormProjects/pokesingle-api/.secrets/ebay-api.env"
MANIFEST_FIELDS = (
    "photo", "bucket", "source_site", "page_url", "title", "photo_index",
    "width", "height", "long_edge",
)
USER_AGENT = "PokeSingle internal photo-corpus research (hello@pokesingle.com)"
PACE_SECONDS = 3.5
MIN_LONG_EDGE = 1000


def load_credentials(path: Path) -> tuple[str, str]:
    """Read client credentials without exporting or displaying their values."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    client_id = values.get("EBAY_CLIENT_ID", "")
    client_secret = values.get("EBAY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in the local credential file")
    return client_id, client_secret


def image_extension(content_type: str, image_url: str) -> str | None:
    """Return a safe extension for supported image responses."""
    mime = content_type.partition(";")[0].strip().lower()
    extension = mimetypes.guess_extension(mime)
    if extension in {".jpg", ".jpeg"}:
        extension = ".jpg"
    if extension not in {".jpg", ".png", ".webp", ".gif", ".bmp"}:
        suffix = Path(urlparse(image_url).path).suffix.lower()
        extension = suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"} else None
        if extension == ".jpeg":
            extension = ".jpg"
    return extension


def full_size_image_url(image_url: str) -> str:
    """Select the listing's full-size Browse `image.imageUrl` variant.

    Browse search summaries in the current cache return an `s-l225` URL.
    `thumbnailImages` is deliberately never read. Only a recognized eBay image
    size token is upgraded; an unknown URL shape fails closed.
    """
    parsed = urlparse(image_url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith("ebayimg.com"):
        raise ValueError("Browse image URL is not an HTTPS eBay image URL")
    path, count = re.subn(r"/s-l\d+(?=\.[^/]+$)", "/s-l1600", parsed.path, count=1)
    if count != 1:
        raise ValueError("Browse image URL has no recognized eBay size token")
    return parsed._replace(path=path).geturl()


def image_dimensions(data: bytes) -> tuple[int, int]:
    """Read the displayed image dimensions after applying EXIF orientation."""
    with Image.open(BytesIO(data)) as image:
        upright = ImageOps.exif_transpose(image)
        return int(upright.width), int(upright.height)


def item_id_from_url(url: str) -> str | None:
    match = re.search(r"/itm/(?:[^/?]+/)?(\d{9,})", urlparse(url).path)
    return match.group(1) if match else None


def item_id_from_summary(item: dict, page_url: str | None) -> str | None:
    """Normalize Browse REST and legacy IDs to the numeric listing ID."""
    value = item.get("itemId")
    if isinstance(value, str):
        match = re.search(r"(?:^|\|)(\d{9,})(?:\||$)", value)
        if match:
            return match.group(1)
    return item_id_from_url(page_url) if isinstance(page_url, str) else None


def read_manifest(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    if not path.exists():
        return [], set()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows, {item_id for row in rows if (item_id := item_id_from_url(row.get("page_url", "")))}


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in MANIFEST_FIELDS} for row in rows)


class Pacer:
    """Keep requests to each host at least the configured interval apart."""

    def __init__(self, interval: float = PACE_SECONDS):
        self.interval = interval
        self.last_request: dict[str, float] = {}

    def wait(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        now = time.monotonic()
        delay = self.interval - (now - self.last_request.get(host, 0.0))
        if delay > 0:
            time.sleep(delay)
        self.last_request[host] = time.monotonic()


def get_token(client: httpx.Client, client_id: str, client_secret: str, pacer: Pacer) -> str:
    pair = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
    pacer.wait(TOKEN_URL)
    response = client.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {pair}", "Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": USER_AGENT},
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
    )
    if response.status_code != 200:
        raise RuntimeError(f"eBay OAuth failed with HTTP {response.status_code}; credentials were not logged")
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("eBay OAuth response did not contain an access token")
    return token


def cached_search(
    client: httpx.Client, token: str, query: str, offset: int, cache_dir: Path, pacer: Pacer
) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{query}\0{offset}".encode()).hexdigest()[:20]
    cache_path = cache_dir / f"search-{key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    params = {"q": query, "limit": 50, "offset": offset, "filter": "buyingOptions:{FIXED_PRICE}"}
    pacer.wait(SEARCH_URL)
    response = client.get(SEARCH_URL, params=params, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": USER_AGENT,
    })
    if response.status_code != 200:
        raise RuntimeError(f"eBay Browse search failed with HTTP {response.status_code}")
    raw = response.json()
    # Browse summaries can include seller identities and other fields we do not
    # need. Keep the cache minimal so those fields are never retained locally.
    summaries = []
    for item in raw.get("itemSummaries", []) if isinstance(raw, dict) else []:
        if not isinstance(item, dict):
            continue
        image = item.get("image")
        summaries.append({
            "itemId": item.get("itemId"),
            "title": item.get("title"),
            "itemWebUrl": item.get("itemWebUrl"),
            "image": {"imageUrl": image.get("imageUrl")} if isinstance(image, dict) else None,
        })
    body = {"itemSummaries": summaries}
    cache_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return body


def append_manifest(path: Path, row: dict[str, str]) -> None:
    rows, _ = read_manifest(path)
    write_manifest(path, [*rows, row])


def get_image(client: httpx.Client, image_url: str, pacer: Pacer) -> httpx.Response:
    """Fetch one image while pacing each host, including redirect targets."""
    url = image_url
    for _ in range(4):
        pacer.wait(url)
        response = client.get(url, headers={"User-Agent": USER_AGENT})
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        url = urljoin(url, location)
    raise RuntimeError("eBay image redirected too many times")


def collect(args: argparse.Namespace, client: httpx.Client | None = None) -> int:
    client_id, client_secret = load_credentials(args.credentials)
    root = args.destination
    raw_dir = root / "raw"
    cache_dir = root / "cache" / "ebay"
    manifest_path = root / "manifest.csv"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows, seen_ids = read_manifest(manifest_path)
    rejected_path = root / "cache" / "ebay" / "rejected-small-image-ids.txt"
    if rejected_path.exists():
        seen_ids.update(rejected_path.read_text(encoding="utf-8").splitlines())
    used_names = {row["photo"] for row in rows}
    used_stems = {path.stem for path in raw_dir.iterdir() if path.is_file()}
    used_stems.update(Path(name).stem for name in used_names)
    if not 1 <= args.count <= 500:
        raise ValueError("count must be between 1 and 500")
    own_client = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    pacer = Pacer()
    try:
        token = get_token(client, client_id, client_secret, pacer)
        added = 0
        # eBay's public Browse API maximum page size is 50; cap at 500 pages
        # even when a query returns many duplicate or unsuitable items.
        offsets = range(0, 50 * 500, 50)
        for offset in offsets:
            if added >= args.count:
                break
            body = cached_search(client, token, args.query, offset, cache_dir, pacer)
            items = body.get("itemSummaries")
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if added >= args.count:
                    break
                if not isinstance(item, dict):
                    continue
                page_url = item.get("itemWebUrl")
                image_url = (item.get("image") or {}).get("imageUrl")
                title = item.get("title")
                item_id = item_id_from_summary(item, page_url if isinstance(page_url, str) else None)
                if (not isinstance(page_url, str) or not isinstance(image_url, str) or not isinstance(title, str)
                        or not item_id or item_id in seen_ids):
                    continue
                try:
                    full_url = full_size_image_url(image_url)
                    image_response = get_image(client, full_url, pacer)
                except (httpx.HTTPError, RuntimeError, ValueError):
                    continue
                if image_response.status_code != 200:
                    continue
                extension = image_extension(image_response.headers.get("content-type", ""), full_url)
                if not extension or not image_response.content:
                    continue
                try:
                    width, height = image_dimensions(image_response.content)
                except Exception:
                    continue
                long_edge = max(width, height)
                if long_edge < MIN_LONG_EDGE:
                    rejected_path.parent.mkdir(parents=True, exist_ok=True)
                    with rejected_path.open("a", encoding="utf-8") as rejected:
                        rejected.write(item_id + "\n")
                    seen_ids.add(item_id)
                    continue
                index = 1
                while f"{index:04d}" in used_stems:
                    index += 1
                filename = f"{index:04d}{extension}"
                image_path = raw_dir / filename
                image_path.write_bytes(image_response.content)
                row = {"photo": f"raw/{filename}", "bucket": args.bucket, "source_site": "ebay",
                       "page_url": page_url, "title": title.strip(), "photo_index": "1",
                       "width": str(width), "height": str(height), "long_edge": str(long_edge)}
                append_manifest(manifest_path, row)
                used_names.add(row["photo"])
                used_stems.add(Path(filename).stem)
                seen_ids.add(item_id)
                added += 1
                print(f"saved {row['photo']} ({width}x{height}; {added}/{args.count})", flush=True)
            if len(items) < 50:
                break
        print(f"Added {added} photos with long edge >= {MIN_LONG_EDGE}px. Existing photos: {len(rows)}. Source URLs and photos remain local.")
        return added
    finally:
        if own_client:
            client.close()


def verify_connection(credentials: Path, query: str) -> int:
    """Verify OAuth and Browse access without saving results or photos."""
    client_id, client_secret = load_credentials(credentials)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        pacer = Pacer()
        token = get_token(client, client_id, client_secret, pacer)
        params = {"q": query, "limit": 1, "offset": 0,
                  "filter": "buyingOptions:{FIXED_PRICE}"}
        pacer.wait(SEARCH_URL)
        response = client.get(SEARCH_URL, params=params, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": USER_AGENT,
        })
        if response.status_code != 200:
            raise RuntimeError(f"eBay Browse search failed with HTTP {response.status_code}")
        body = response.json()
    return len(body.get("itemSummaries", []))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--query", default="pokemon trading card")
    result.add_argument("--bucket", choices=(
        "modern_raw", "vintage_wotc_raw", "same_artwork_reprint", "japanese_raw", "slab", "hard_case"))
    result.add_argument("--count", type=int, help="Number of new photos to collect (1–500)")
    result.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIAL_FILE)
    result.add_argument("--destination", type=Path, default=Path("data/photo-corpus"))
    result.add_argument("--check-auth", action="store_true", help="Verify OAuth and Browse access without saving photos")
    return result


if __name__ == "__main__":
    try:
        options = parser().parse_args()
        if options.check_auth:
            found = verify_connection(options.credentials, options.query)
            print(f"eBay Browse API access OK; search returned {found} summaries. Credentials were not logged.")
        else:
            if not options.bucket or options.count is None:
                parser().error("--bucket and --count are required unless --check-auth is used")
            collect(options)
    except (OSError, ValueError, RuntimeError, httpx.HTTPError) as error:
        print(f"Collection stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
