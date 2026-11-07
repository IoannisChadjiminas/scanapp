#!/usr/bin/env python3
"""Read product ids from Cardmarket expansion list pages for the Japanese recovery.

Adapted from data/catalogue-gaps/tcgdex-empty-sets-20261017/read_cm_id_lists.py.
Grid view has no product id. List view puts it on each row as productRow<id>.
One page every 2 seconds, in the owner's Chrome (a new window it opens at start; Chrome needs View > Developer > Allow JavaScript from Apple Events).
On a human check it waits up to 10 minutes for the owner to clear it and never
clicks it. Resumable. Does not change the catalogue.

    python3 read_product_ids.py RUN_DIR [desc]

Cardmarket's list view stops after 10 pages (300 rows). For larger sets, run again
with `desc`: it reads only the sets that still have targets without an id, sorted by
collector number descending, so the tail of the set becomes visible.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import sys

ROOT = Path(sys.argv[1]).resolve()
TARGETS = ROOT / "verified-mappings.jsonl"
OUT = ROOT / "cardmarket-ids.jsonl"
STATE = ROOT / "cardmarket-ids-state.json"
DESC = len(sys.argv) > 2 and sys.argv[2] == "desc"
DONE = ROOT / ("cardmarket-ids-done-desc.json" if DESC else "cardmarket-ids-done.json")
GAP_S = 2
HUMAN_WAIT_S = 600
TAB = ""
WINDOW = ""

PAGE_JS = r"""
var title = document.title || '';
var body = ((document.body && document.body.innerText) || '').slice(0, 800);
var low = (title + ' ' + body).toLowerCase();
var human = low.indexOf('verify you are human') >= 0 || low.indexOf('attention required') >= 0 || low.indexOf('access denied') >= 0;
var waiting = low.indexOf('just a moment') >= 0 || low.indexOf('verification successful') >= 0 || low.indexOf('waiting for www.cardmarket.com') >= 0;
var expansion = null;
var links = document.querySelectorAll('a[href*="idExpansion="]');
for (var i = 0; i < links.length; i++) {
  var match = String(links[i].getAttribute('href') || '').match(/idExpansion=(\d+)/);
  if (match) { expansion = match[1]; break; }
}
var rows = document.querySelectorAll('[id^="productRow"]');
var products = [];
for (var r = 0; r < rows.length; r++) {
  var row = rows[r];
  var id = String(row.id || '').replace('productRow', '');
  var anchor = row.querySelector('a[href*="/Products/Singles/"]');
  if (!anchor || !/^\d+$/.test(id)) continue;
  var abs = new URL(anchor.href);
  abs.hash = ''; abs.search = '';
  abs.pathname = abs.pathname.replace(/\/$/, '');
  products.push({product_id: id, url: abs.toString(), text: (anchor.textContent || '').replace(/\s+/g, ' ').trim()});
}
JSON.stringify({title: title, href: location.href, ready: document.readyState, human: human, waiting: waiting, expansion: expansion, products: products, gallery: document.querySelectorAll('.galleryBox').length});
"""


def osa(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def go(url: str) -> None:
    osa(
        'tell application "Google Chrome" to tell (first tab of window id ' + WINDOW + ' whose id is '
        + TAB + ") to set URL to " + json.dumps(url)
    )


def read_page() -> dict:
    script = (
        'tell application "Google Chrome" to tell (first tab of window id ' + WINDOW + ' whose id is '
        + TAB + ") to execute javascript " + json.dumps(PAGE_JS)
    )
    return json.loads(osa(script))


def wait_ready(needle: str) -> dict:
    last: dict = {}
    for _ in range(HUMAN_WAIT_S):
        last = read_page()
        if last.get("human"):
            time.sleep(1)
            continue
        href = str(last.get("href") or "")
        if needle in href and last.get("ready") == "complete" and not last.get("waiting"):
            return last
        time.sleep(1)
    return last


def on_list_page(payload: dict, slug: str, expansion_id: str | None, page: int) -> bool:
    if payload.get("ready") != "complete" or payload.get("waiting") or payload.get("human"):
        return False
    href = str(payload.get("href") or "")
    if "mode=list" not in href:
        return False
    if expansion_id:
        if f"idExpansion={expansion_id}" not in href:
            return False
        return re.search(rf"(?:^|[?&])site={page}(?:&|$)", href) is not None
    if f"/Singles/{slug}" not in href:
        return False
    match = re.search(r"[?&]site=(\d+)", href)
    current = int(match.group(1)) if match else 1
    return current == page


def wait_list(slug: str, expansion_id: str | None, page: int) -> dict:
    last: dict = {}
    for _ in range(HUMAN_WAIT_S):
        last = read_page()
        if last.get("human"):
            time.sleep(1)
            continue
        if on_list_page(last, slug, expansion_id, page):
            return last
        time.sleep(1)
    return last


def list_url(slug: str, expansion_id: str | None, page: int) -> str:
    if expansion_id:
        return (
            "https://www.cardmarket.com/en/Pokemon/Products/Singles?idExpansion="
            + expansion_id + "&sortBy=collectorsnumber_" + ("desc" if DESC else "asc") + "&site=" + str(page) + "&mode=list"
        )
    url = "https://www.cardmarket.com/en/Pokemon/Products/Singles/" + slug + "?mode=list"
    if page > 1:
        url += "&site=" + str(page)
    return url


def slug_of(url: str) -> str | None:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    if len(parts) < 6 or parts[3] != "Singles":
        return None
    return parts[4]


def needed_slugs() -> dict[str, int]:
    done_urls = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                done_urls.add(json.loads(line)["url"].rstrip("/"))
    counts: dict[str, int] = {}
    for line in TARGETS.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["url"].rstrip("/") in done_urls:
            continue
        slug = slug_of(row["url"])
        if slug:
            counts[slug] = counts.get(slug, 0) + 1
    return counts


def finished() -> set[str]:
    if not DONE.exists():
        return set()
    return set(json.loads(DONE.read_text()))


def mark_finished(slug: str) -> None:
    slugs = finished()
    slugs.add(slug)
    DONE.write_text(json.dumps(sorted(slugs), indent=1) + "\n")


def main() -> None:
    global TAB, WINDOW
    # always work in a new window of our own, never in the tab the owner is using; then pin it
    osa('tell application "Google Chrome" to make new window')
    WINDOW = osa('tell application "Google Chrome" to get id of window 1')
    TAB = osa('tell application "Google Chrome" to get id of active tab of window 1')
    counts = needed_slugs()
    pending = [slug for slug in sorted(counts) if slug not in finished()]
    print(json.dumps({"expansions": len(pending), "cards": sum(counts[slug] for slug in pending)}), flush=True)
    seen = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                seen.add(json.loads(line)["url"])
    for slug in pending:
        expansion_url = "https://www.cardmarket.com/en/Pokemon/Expansions/" + slug
        go(expansion_url)
        info = wait_ready("/Pokemon/Expansions/" + slug)
        STATE.write_text(json.dumps({"slug": slug, "href": info.get("href"), "title": info.get("title"), "human": info.get("human"), "waiting": info.get("waiting")}, indent=1) + "\n")
        if info.get("human") or info.get("waiting") or "/Pokemon/Expansions/" + slug not in str(info.get("href") or ""):
            print(json.dumps({"stopped": True, "slug": slug, "title": info.get("title"), "expansion": info.get("expansion")}), flush=True)
            raise SystemExit(2)
        expansion_id = str(info["expansion"]) if info.get("expansion") else None
        time.sleep(GAP_S)
        page = 1
        while page <= 40:
            go(list_url(slug, expansion_id, page))
            payload = wait_list(slug, expansion_id, page)
            STATE.write_text(json.dumps({"slug": slug, "page": page, "href": payload.get("href"), "title": payload.get("title"), "human": payload.get("human"), "waiting": payload.get("waiting"), "rows": len(payload.get("products") or [])}, indent=1) + "\n")
            if payload.get("human") or payload.get("waiting"):
                print(json.dumps({"stopped": True, "slug": slug, "page": page, "title": payload.get("title")}), flush=True)
                raise SystemExit(2)
            if "mode=list" not in str(payload.get("href") or "") or payload.get("gallery"):
                print(json.dumps({"stopped": True, "reason": "not-list-view", "slug": slug, "page": page, "href": payload.get("href")}), flush=True)
                raise SystemExit(2)
            products = payload.get("products") or []
            added = 0
            with OUT.open("a") as handle:
                for product in products:
                    if product["url"] in seen:
                        continue
                    product.update({"expansion": slug, "expansion_id": int(expansion_id) if expansion_id else None, "page": page})
                    handle.write(json.dumps(product, ensure_ascii=False) + "\n")
                    seen.add(product["url"])
                    added += 1
            print(json.dumps({"slug": slug, "page": page, "rows": len(products), "added": added, "total": len(seen)}), flush=True)
            if len(products) < 30:
                break
            if page == 40:
                print(json.dumps({"stopped": True, "reason": "page-cap", "slug": slug}), flush=True)
                raise SystemExit(2)
            page += 1
            time.sleep(GAP_S)
        mark_finished(slug)
        time.sleep(GAP_S)
    print(json.dumps({"done": True, "total": len(seen)}), flush=True)


if __name__ == "__main__":
    main()
