"""Count staging scans whose first or confirmed card is a held-era Japanese card. Ids only.

This is a scan count, not a demand measure: staging scans are the owner's tests and the
regression panels, so no product decision rests on it.

1. Export ids only from staging. No photos and no OCR text leave the server:

    ssh auctaro-staging 'docker exec scanapp-scanapp-z1mwj4-api-1 python3 -c "
    import sqlite3,json
    c=sqlite3.connect(\\"file:/data/results.sqlite?mode=ro\\",uri=True)
    for sid,ses,ts,st,o,cr,conf in c.execute(\\"select id,session_id,created_at,status,ocr_json,combined_ranking_json,confirmed_card_id from scans\\"):
      o=json.loads(o or \\"{}\\"); cr=json.loads(cr or \\"[]\\")
      print(json.dumps({\\"id\\":sid,\\"s\\":ses,\\"t\\":ts,\\"st\\":st,\\"det\\":o.get(\\"detected_language\\"),
        \\"req\\":o.get(\\"requested_language\\"),\\"sl\\":o.get(\\"search_languages\\"),
        \\"top\\":[x.get(\\"card_id\\") for x in cr[:5] if isinstance(x,dict)],\\"conf\\":conf}))
    "' > EXPORT_DIR/scans-ids.jsonl

2. python3 count_held_era_scans.py EXPORT_DIR RUN_DIR

RUN_DIR is the recovery run folder (set-registry.json, cards.json). A session is "burst" when the
median gap between its scans is under 15 s (automated runs); the rest are human-paced.
"""
import collections
import json
import re
import statistics
import sys
from datetime import datetime

MODERN = {"Mega Evolution Era", "Scarlet & Violet Era", "Sword & Shield Era", "Sun & Moon Era"}
# Set-id prefixes of Japanese sets outside the recovery registry (the TCGdex-era catalogue).
PREFIX_ERAS = [(r"^(SV|S\d|S1|SM|M\d|MC$|SMP|s-p|s8b|sm9|pooka-wcs23)", "modern"),
               (r"^(PMCG|cll|pooka-cl)", "Original Era"), (r"^neo", "Neo Era"), (r"^E\d", "e-Card Era"),
               (r"^PCG", "PCG Era"), (r"^(BW|BK|MDB|pc-plasma|pc-red|pooka-bk)", "Black & White Era"),
               (r"^(CP|xy|pc-xy)", "XY Era")]


def main(export_dir, run_dir):
    registry = {g["group_id"]: g for g in json.load(open(f"{run_dir}/set-registry.json"))}
    set_era = {c["set_id"]: registry[c["group_id"]]["era"] for c in json.load(open(f"{run_dir}/cards.json"))}

    def era(card_id):
        if not card_id or not card_id.startswith("ja:"):
            return None
        set_id = card_id[3:].rsplit("-", 1)[0]
        if set_id in set_era:
            return set_era[set_id]
        return next((e for pattern, e in PREFIX_ERAS if re.match(pattern, set_id)), "older (other)")

    def held(e):
        return e is not None and e not in MODERN and e != "modern"

    def japanese(r):
        return "ja" in (r["sl"] or []) or r["det"] == "ja" or r["req"] == "ja"

    rows = [json.loads(line) for line in open(f"{export_dir}/scans-ids.jsonl")]
    by_session = collections.defaultdict(list)
    for r in rows:
        by_session[r["s"]].append(r)

    def pacing(session):
        times = sorted(datetime.fromisoformat(r["t"][:19]) for r in by_session[session])
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        return "single" if not gaps else "burst" if statistics.median(gaps) < 15 else "human-paced"
    kind = {s: pacing(s) for s in by_session}

    held_rows = [r for r in rows if any(held(era(c)) for c in ([r["top"][0]] if r["top"] else []) + [r["conf"]])]
    human = [r for r in held_rows if kind[r["s"]] != "burst"]
    report = {
        "scans": len(rows), "sessions": len(by_session),
        "japanese_language_scans": sum(japanese(r) for r in rows),
        "held_era_scans": len(held_rows), "held_era_sessions": len({r["s"] for r in held_rows}),
        "held_era_burst_scans": sum(kind[r["s"]] == "burst" for r in held_rows),
        "held_era_human_paced_scans": len(human), "held_era_human_paced_sessions": len({r["s"] for r in human}),
        "human_paced_by_era": collections.Counter(era(r["top"][0]) for r in human if r["top"]).most_common(),
        "human_paced_status": collections.Counter(r["st"] for r in human).most_common(),
    }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
