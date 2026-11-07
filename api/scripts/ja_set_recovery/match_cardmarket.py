"""Match new checklist rows to Cardmarket single products. Offline and read-only.

    python3 match_cardmarket.py RUN_DIR

A row is linked only when exactly one product in its group's pool agrees on the
printed number AND the English name (token sets equal, or one contained in the
other with only level/era tags extra, see NEUTRAL). Unnumbered rows need a unique exact-name product. The pool is the group's
own listing products plus shared-pool products that name the group (their
membership is unverified, so they only count when the same number+name rule
holds). A product URL is never given to two rows: every claimant is held.

Writes verified-mappings.jsonl, held-mappings.jsonl and cardmarket-match-summary.json.
"""
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

FILLER = {"delta", "species", "the", "of", "and"}
SUFFIX = re.compile(r"\s*\(([^()]*)\)\s*$")


def tokens(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " ").replace("'", "").replace("’", "")
    s = re.sub(r"\[([mf])\]", r" \1 ", s)
    s = re.sub(r"\be4\b", "4", s)
    s = re.sub(r"\bm(?=[a-z]{3,})", "m ", s) if s.startswith("m") and not s.startswith(("ma", "me", "mi", "mo", "mu", "my", "mr")) else s
    return frozenset(t for t in re.split(r"[^a-z0-9]+", s) if t and t not in FILLER)


def norm_number(raw):
    head = (raw or "").split("/")[0].strip()
    m = re.search(r"(\d+)([a-z]?)$", head, re.I)
    return f"{int(m.group(1))}{m.group(2).lower()}" if m else ""


def split_product(name):
    m = SUFFIX.search(name)
    if not m:
        return name.strip(), ""
    inner = m.group(1).split()
    number = norm_number(inner[-1]) if inner and re.search(r"\d", inner[-1]) else ""
    return name[: m.start()].strip(), number


# Tokens one side may carry that do not change the card: levels, LV.X-era tags, Team Plasma.
NEUTRAL = {"lv", "gl", "fb", "c", "g", "4", "team", "plasma"}


def name_agrees(a, b):
    if not a or not b:
        return False
    extra = a ^ b
    return (a <= b or b <= a) and all(t in NEUTRAL or t.isdigit() for t in extra)


def main(run_dir):
    run = Path(run_dir)
    pools = defaultdict(list)
    for line in (run / "cardmarket-products.jsonl").open():
        p = json.loads(line)
        pools[p["group_id"]].append({**p, "pool": "group_listing"})
    for line in (run / "shared-listings-products.jsonl").open():
        p = json.loads(line)
        for gid in p.get("related_group_ids", []):
            pools[gid].append({**p, "pool": "shared_unverified"})
    for gid, items in pools.items():
        dedup = {}
        for p in items:
            base, number = split_product(p["name"])
            dedup.setdefault(p["url"], {**p, "base": base, "number": number, "tok": tokens(base)})
        pools[gid] = list(dedup.values())

    rows = [json.loads(l) for l in (run / "new-or-incomplete-printings.jsonl").open()]
    results = []
    for row in rows:
        pool = pools.get(row["group_id"], [])
        num = norm_number(row["printed_number"])
        tok = tokens(row["card_name"])
        out = {k: row[k] for k in ("group_id", "printed_number", "card_name")}
        if not pool:
            out.update(status="held", reason="no_products_for_group")
        elif num:
            same_num = [p for p in pool if p["number"] == num]
            agree = [p for p in same_num if name_agrees(tok, p["tok"])]
            if len(agree) == 1:
                out.update(status="linked", url=agree[0]["url"], product_name=agree[0]["name"],
                           evidence=f"number {num} + name ({agree[0]['pool']})")
            elif len(agree) > 1:
                out.update(status="held", reason="several_products_agree", candidates=[p["url"] for p in agree])
            elif same_num:
                out.update(status="held", reason="number_matches_name_differs",
                           candidates=[f"{p['name']} {p['url']}" for p in same_num])
            else:
                out.update(status="held", reason="no_product_with_number")
        else:
            exact = [p for p in pool if p["tok"] == tok]
            if len(exact) == 1:
                out.update(status="linked", url=exact[0]["url"], product_name=exact[0]["name"],
                           evidence=f"unnumbered unique exact name ({exact[0]['pool']})")
            else:
                out.update(status="held", reason="unnumbered_name_not_unique" if exact else "unnumbered_no_name_match",
                           candidates=[p["url"] for p in exact])
        results.append(out)

    claims = Counter(r["url"] for r in results if r["status"] == "linked")
    for r in results:
        if r["status"] == "linked" and claims[r["url"]] > 1:
            r.update(status="held", reason="url_claimed_by_several_rows", candidates=[r.pop("url")])
            r.pop("product_name", None)
            r.pop("evidence", None)

    linked = [r for r in results if r["status"] == "linked"]
    held = [r for r in results if r["status"] != "linked"]
    (run / "verified-mappings.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in linked))
    (run / "held-mappings.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in held))
    summary = {"rows": len(results), "linked": len(linked),
               "linked_via": dict(Counter(r["evidence"].split(" (")[-1].rstrip(")") for r in linked)),
               "held": dict(Counter(r["reason"] for r in held))}
    (run / "cardmarket-match-summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
