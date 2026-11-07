"""Split the recovery checklist into rows already in the catalogue and new rows.

Read-only. Inputs are the run folder (registry + image reconciliation CSV) and
the audit's catalogue snapshot (`catalogue-sets.json`, id/name/number per set).
A row is an existing match when one of its group's catalogue set codes holds the
same printed number. Names are not compared: catalogue names are Japanese and
the checklist names are English, so every match here is number-only evidence
and is labelled that way.

    python3 match_existing.py RUN_DIR CATALOGUE_SETS_JSON
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def norm_number(raw):
    head = (raw or "").split("/")[0].strip()
    m = re.fullmatch(r"0*(\d+)([A-Za-z]*)", head)
    return f"{int(m.group(1))}{m.group(2).upper()}" if m else head.upper()


def main(run_dir, catalogue_path):
    run = Path(run_dir)
    registry = {g["group_id"]: g for g in json.loads((run / "set-registry.json").read_text())}
    catalogue = json.loads(Path(catalogue_path).read_text())
    rows = list(csv.DictReader(
        (run / "review/image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig")))

    by_group = defaultdict(list)
    for row in rows:
        by_group[row["group_id"]].append(row)

    out, stats = [], Counter()
    for group_id, group_rows in by_group.items():
        reg = registry.get(group_id, {})
        index = defaultdict(list)
        for code in reg.get("catalogue_codes", []):
            for card in catalogue.get(code, []):
                index[norm_number(card["collector_number"])].append(card)
        for row in group_rows:
            hits = index.get(norm_number(row["printed_number"]), []) if row["printed_number"] else []
            if len(hits) == 1:
                status = "existing_number_match"
            elif hits:
                status = "existing_ambiguous"
            else:
                status = "new"
            stats[(reg.get("coverage", "?"), status)] += 1
            out.append({
                "group_id": group_id,
                "printed_number": row["printed_number"],
                "card_name": row["card_name"],
                "status": status,
                "catalogue_ids": [h["id"] for h in hits],
                "catalogue_has_image": [h["has_image"] for h in hits],
                "evidence": "set code + printed number; names not compared" if hits else "",
            })

    (run / "existing-matches.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out if r["status"] != "new"))
    (run / "new-or-incomplete-printings.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out if r["status"] == "new"))
    empty = [g for g in registry if g not in by_group]
    print("rows", len(out), "groups with rows", len(by_group), "registry groups without rows", len(empty))
    for key, n in sorted(stats.items()):
        print(key, n)


if __name__ == "__main__":
    main(*sys.argv[1:3])
