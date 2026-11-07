"""Match TCG Collector set-page images to new recovery cards that still have no image.

    python3 match_tcgcollector_images.py RUN_DIR MODEL_ONNX

Inputs: the set pages from read_tcgcollector_sets.py (labels like "Seedot (World Champions Pack
001/108)") and the cards still without an image after the official fill. A card gets a TCG
Collector image only when exactly one label in its set has the same number (numerator equal,
denominator equal when both print one; roster labels such as "No. 005" compare as written)
AND the same English name (an unnumbered card needs an unnumbered or roster label with its name, "Basic" ignored) (token sets equal, or one contained in the other with only
level/era tags extra, as match_cardmarket.py). If the card already had a low-quality or shared
image, the new one must also look like it (pad cosine >= 0.85). Images pass the catalogue gate.

Downloads (browser UA + TCG Collector referer, 0.5 s apart) go to RUN_DIR/images/tcgcollector-fill/.
Writes RUN_DIR/review/tcgcollector-fill-20261107.jsonl (same fields as the official fill, so
build_image_batch.py can take it) and tcgcollector-fill-held-20261107.jsonl.
"""
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
API = HERE.parents[1]
REPO = API.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from app.recognition.embed import DinoEmbedder  # noqa: E402
from catalogue.bootstrap.checks import BLUR_LIMIT, MIN_SIDE, load_facts  # noqa: E402
from match_cardmarket import name_agrees, tokens  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Referer": "https://www.tcgcollector.com/"}
SIMILAR = 0.85


def number_key(text):
    text = (text or "").strip()
    roster = re.fullmatch(r"(?i)no\.?\s*0*(\d+)", text)
    if roster:
        return ("roster", int(roster.group(1)), None)
    m = re.search(r"0*(\d{1,4})\s*(?:/\s*([A-Za-z0-9.-]+))?$", text)
    if not m or text.lower().startswith("unnum"):
        return None
    return ("printed", int(m.group(1)), (m.group(2) or "").upper() or None)


def same_number(a, b):
    if not a or not b or a[1] != b[1]:
        return False
    if a[0] == "roster" or b[0] == "roster":
        return True
    return not (a[2] and b[2] and a[2].isdigit() and b[2].isdigit()) or int(a[2]) == int(b[2])


def parse_label(alt):
    m = re.fullmatch(r"(.*) \((.*)\)\s*", alt or "")
    if not m:
        return None, None
    inner = m.group(2).strip()
    token = inner.split()[-1] if inner.split() else ""
    roster = re.search(r"(?i)\bno\.?\s*(\d+)\s*$", inner)
    return m.group(1).strip(), number_key("No. " + roster.group(1) if roster else token)


def main(run_dir, model_path):
    run = Path(run_dir).resolve()
    pages = run / "source-pages/tcgcollector-20261107"
    done = {json.loads(l)["id"] for l in (run / "review/official-fill-20261107.jsonl").open()}
    cards = [c for c in json.loads((run / "cards.json").read_text())
             if not c["problem"] and not c["local_file"] and c["id"] not in done]
    rows = defaultdict(list)
    for r in csv.DictReader((run / "review/image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig")):
        rows[(r["group_id"], r["printed_number"], r["card_name"])].append(r)
    model = DinoEmbedder(model_path, 4, 1)
    matched, held = [], []
    claimed = set()
    for card in cards:
        base = {"id": card["id"], "group_id": card["group_id"], "set_name": card["set_name"],
                "printed_number": card["printed_number"], "name": card["name"], "image_status": card["image_status"]}
        page_file = pages / f"{card['group_id']}.json"
        if not page_file.exists():
            held.append({**base, "reason": "set_page_not_read"})
            continue
        labels = json.loads(page_file.read_text())["cards"]
        want = number_key(card["printed_number"])
        want_tok = tokens(card["name"])
        if not want_tok:
            held.append({**base, "reason": "no_name"})
            continue
        hits = []
        for alt, src in labels:
            name, number = parse_label(alt)
            if not name:
                continue
            if want and same_number(want, number) and name_agrees(want_tok, tokens(name)):
                hits.append((alt, src))
            elif not want and (number is None or number[0] == "roster") and \
                    tokens(name) - {"basic"} == want_tok - {"basic"}:
                # unnumbered card (basic energies): unnumbered or roster label, same name ignoring "Basic"
                hits.append((alt, src))
        hits = list(dict(hits).items())
        if len(hits) != 1:
            held.append({**base, "reason": "no_label_match" if not hits else "several_label_matches",
                         "candidates": [a for a, _ in hits][:5]})
            continue
        alt, src = hits[0]
        if src in claimed:
            held.append({**base, "reason": "image_claimed_by_another_card", "label": alt})
            continue
        with urllib.request.urlopen(urllib.request.Request(src, headers=HEADERS), timeout=30) as response:
            data = response.read()
        time.sleep(0.5)
        dest = run / "images/tcgcollector-fill" / card["group_id"] / (card["id"].replace(":", "_") + Path(src).suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        facts = load_facts(dest)
        if min(facts.width, facts.height) < MIN_SIDE or facts.blur is None or facts.blur < BLUR_LIMIT:
            held.append({**base, "reason": "image_failed_gate", "label": alt, "width": facts.width, "height": facts.height})
            continue
        similarity = None
        for r in rows.get((card["group_id"], card["printed_number"], card["name"])) or []:
            for key, value in r.items():
                if not key.endswith("_files"):
                    continue
                for rel in filter(None, (p.strip() for p in value.split(";"))):
                    path = REPO / rel if (REPO / rel).exists() else run / rel
                    try:
                        with Image.open(path) as im:
                            a = model.embed(im.convert("RGB"), "pad")
                    except Exception:
                        continue
                    with Image.open(io.BytesIO(data)) as im:
                        similarity = round(float(a @ model.embed(im.convert("RGB"), "pad")), 4)
                    break
                if similarity is not None:
                    break
        if similarity is not None and similarity < SIMILAR:
            held.append({**base, "reason": "image_looks_different", "similarity": similarity, "label": alt})
            continue
        claimed.add(src)
        matched.append({**base, "file": str(dest.relative_to(REPO)), "sha256": hashlib.sha256(data).hexdigest(),
                        "width": facts.width, "height": facts.height, "blur": round(facts.blur, 1),
                        "official_card_id": None, "official_name_ja": card["name"], "official_number": alt,
                        "detail_url": json.loads(page_file.read_text())["url"], "image_url": src,
                        "similarity_to_previous_image": similarity, "source_kind": "tcgcollector_scan"})
    (run / "review/tcgcollector-fill-20261107.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in matched))
    (run / "review/tcgcollector-fill-held-20261107.jsonl").write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in held))
    print(json.dumps({"matched": len(matched), "held": len(held)}), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
