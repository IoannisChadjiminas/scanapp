"""Fill missing images of new recovery cards from the official Japanese card search.

pokemon-card.com is an owner-approved Japanese image source. For each set that still has new
cards without an image, read the official result list for its set code(s) and every card's
detail page (printed number, official Japanese name, image), then attach an official image
to a card only when:

- exactly one official card in that pool has the same printed number (numerator equal, and
  the denominator equal too when both sides print one), and
- the checklist number is a printed number, not a roster index ("No. 005", "unnumbered"), and
- if the card already has a low-quality or shared image, the official image looks like it
  (DINOv2 pad cosine >= 0.85); otherwise the number rule alone decides.

Detail pages are cached in RUN_DIR/source-pages/official-detail-cache.json, one request every
0.6 s. Downloads go to RUN_DIR/images/official-fill/<group>/. Writes
RUN_DIR/review/official-fill-20261107.jsonl (matched) and official-fill-held-20261107.jsonl.

    python3 fill_official_images.py RUN_DIR MODEL_ONNX
"""
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

API = Path(__file__).resolve().parents[2]
REPO = API.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(REPO))
from app.recognition.embed import DinoEmbedder  # noqa: E402
from catalogue.bootstrap.checks import BLUR_LIMIT, MIN_SIDE, load_facts  # noqa: E402

BASE = "https://www.pokemon-card.com"
HEADERS = {"User-Agent": "scanapp-catalogue/1.0", "Referer": BASE + "/card-search/index.php"}
GAP_S = 0.6
SIMILAR = 0.85


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def pool(code):
    out, page, last = [], 1, 1
    while page <= last:
        q = urllib.parse.urlencode({"keyword": "", "sm_and_keyword": "true", "regulation_sidebar_form": "all",
                                    "illust": "", "pg": code, "page": page})
        d = json.loads(get(f"{BASE}/card-search/resultAPI.php?{q}"))
        out += [x["cardID"] for x in d.get("cardList") or [] if x.get("cardID")]
        last = int(d.get("maxPage") or 0)
        page += 1
        time.sleep(GAP_S)
    return out


def detail(card_id):
    url = f"{BASE}/card-search/details.php/card/{card_id}/regu/all"
    html = get(url).decode("utf-8", "replace")
    image = re.search(r'<img class="fit" src="([^"]+)"\s+alt="([^"]+)"', html)
    number = re.search(r'alt="([^"<>]+)"\s*/>\s*&nbsp;([0-9]{1,4})&nbsp;/&nbsp;([0-9]{1,4}|[A-Za-z][A-Za-z0-9.-]*)&nbsp;', html)
    return {"card_id": card_id, "detail_url": url,
            "image_url": urllib.parse.urljoin(BASE, image.group(1)) if image else None,
            "name_ja": image.group(2) if image else None,
            "numerator": number.group(2) if number else None, "denominator": number.group(3) if number else None}


def printed(text):
    """(numerator int, denominator or None) for a printed number; None for roster indices."""
    text = (text or "").strip()
    if not text or text.lower().startswith(("no.", "unnum", "none")) or text in ("—", "-"):
        return None
    m = re.fullmatch(r"([A-Za-z]{0,4})\s*0*(\d{1,4})\s*(?:/\s*([A-Za-z0-9.-]+))?", text)
    if not m:
        return None
    return int(m.group(2)), (m.group(3) or "").upper() or None


def main(run_dir, model_path):
    run = Path(run_dir).resolve()
    probe = json.loads((run / "review/official-probe-missing-20261107.json").read_text())
    cards = [c for c in json.loads((run / "cards.json").read_text()) if not c["problem"] and not c["local_file"]]
    rows = defaultdict(list)
    for r in csv.DictReader((run / "review/image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig")):
        rows[(r["group_id"], r["printed_number"], r["card_name"])].append(r)
    cache_file = run / "source-pages/official-detail-cache.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {"pools": {}, "details": {}}
    model = DinoEmbedder(model_path, 4, 1)
    matched, held = [], []
    by_group = defaultdict(list)
    for c in cards:
        by_group[c["group_id"]].append(c)
    for gid, info in probe.items():
        codes = [code for code, hits in info["official_hits"].items() if isinstance(hits, int) and hits > 0]
        if not codes or gid not in by_group:
            continue
        details = []
        for code in codes:
            if code not in cache["pools"]:
                cache["pools"][code] = pool(code)
            for cid in cache["pools"][code]:
                if cid not in cache["details"]:
                    cache["details"][cid] = detail(cid)
                    time.sleep(GAP_S)
                details.append(cache["details"][cid])
            cache_file.write_text(json.dumps(cache, ensure_ascii=False))
        for card in by_group[gid]:
            want = printed(card["printed_number"])
            base = {"id": card["id"], "group_id": gid, "set_name": card["set_name"], "printed_number": card["printed_number"],
                    "name": card["name"], "image_status": card["image_status"]}
            if not want:
                held.append({**base, "reason": "roster_or_unnumbered"})
                continue
            hits = [d for d in details if d["numerator"] and int(d["numerator"]) == want[0]
                    and (not want[1] or not d["denominator"] or not d["denominator"].isdigit() or not want[1].isdigit()
                         or int(d["denominator"]) == int(want[1]))]
            hits = list({d["card_id"]: d for d in hits}.values())
            if len(hits) != 1:
                held.append({**base, "reason": "no_official_number" if not hits else "several_official_numbers",
                             "candidates": [d["detail_url"] for d in hits][:6]})
                continue
            hit = hits[0]
            data = get(hit["image_url"])
            time.sleep(GAP_S)
            dest = run / "images/official-fill" / gid / (card["id"].replace(":", "_") + Path(urllib.parse.urlsplit(hit["image_url"]).path).suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            facts = load_facts(dest)
            if min(facts.width, facts.height) < MIN_SIDE or facts.blur is None or facts.blur < BLUR_LIMIT:
                held.append({**base, "reason": "official_image_failed_gate", "file": str(dest.relative_to(REPO))})
                continue
            similarity = None
            old = rows.get((gid, card["printed_number"], card["name"]))
            old_files = [p.strip() for r in old or [] for k, v in r.items() if k.endswith("_files") for p in v.split(";") if p.strip()]
            for rel in old_files:
                path = REPO / rel if (REPO / rel).exists() else run / rel
                try:
                    with Image.open(path) as im:
                        a = model.embed(im.convert("RGB"), "pad")
                except Exception:
                    continue
                with Image.open(io.BytesIO(data)) as im:
                    b = model.embed(im.convert("RGB"), "pad")
                similarity = round(float(a @ b), 4)
                break
            if similarity is not None and similarity < SIMILAR:
                held.append({**base, "reason": "official_image_looks_different", "similarity": similarity,
                             "official": hit["detail_url"]})
                continue
            matched.append({**base, "file": str(dest.relative_to(REPO)), "sha256": hashlib.sha256(data).hexdigest(),
                            "width": facts.width, "height": facts.height, "blur": round(facts.blur, 1),
                            "official_card_id": hit["card_id"], "official_name_ja": hit["name_ja"],
                            "official_number": f"{hit['numerator']}/{hit['denominator']}", "detail_url": hit["detail_url"],
                            "image_url": hit["image_url"], "similarity_to_previous_image": similarity,
                            "source_kind": "official_pokemon_card_site"})
        print(json.dumps({"group": gid, "name": info["name"], "matched": sum(1 for m in matched if m["group_id"] == gid),
                          "held": sum(1 for h in held if h["group_id"] == gid)}, ensure_ascii=False), flush=True)
    (run / "review/official-fill-20261107.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in matched))
    (run / "review/official-fill-held-20261107.jsonl").write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in held))
    print(json.dumps({"matched": len(matched), "held": len(held)}), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
