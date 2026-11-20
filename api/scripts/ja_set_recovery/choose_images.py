"""Pick one reference image per new checklist row and apply the catalogue size/blur gate.

Read-only on the catalogue. Needs pillow, numpy and opencv. Run from the repo root:

    python3 api/scripts/ja_set_recovery/choose_images.py RUN_DIR

Reads `new-or-incomplete-printings.jsonl` and the image reconciliation CSV, writes
`image-chosen.jsonl` and `image-chosen-summary.json`. Decision 1 of the finish plan:
keep the catalogue gate (MIN_SIDE, BLUR_LIMIT from catalogue/bootstrap/checks.py) and
use the largest image that passes; rows whose best image is under 500 px on the short
side are flagged `upgrade_later`. An image file is never given to two rows: when the
same SHA-256 appears on several rows, every row except the first keeps the status
`duplicate_file` for manual review.
"""
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from catalogue.bootstrap.checks import BLUR_LIMIT, MIN_SIDE, load_facts  # noqa: E402

SOURCE_RANK = [  # tie-break only; resolution decides first
    "official_source_files", "pooka_source_files", "tcgcollector_source_files",
    "linked_source_files", "alternate_source_files", "binderboss_source_files",
    "supercartas_source_files", "pokemon_tcg_io_source_files", "tcgdex_high_resolution_files",
    "tcgstats_source_files", "pokedatavault_source_files", "local_reference_files",
    "limitless_source_files",
]
REPO = Path(__file__).resolve().parents[3]
UPGRADE_BELOW = 500


def candidates(row, run):
    for rank, col in enumerate(SOURCE_RANK):
        for rel in filter(None, (row.get(col) or "").split(";")):
            rel = rel.strip()
            # the reference-scan column is relative to the run folder, the rest to the repo
            yield rank, col, rel if (REPO / rel).exists() else str((run / rel).relative_to(REPO))


def main(run_dir):
    run = Path(run_dir).resolve()
    # Unnumbered rows share (group, "") so the key carries the name, and repeats are consumed in file order.
    csv_rows = defaultdict(list)
    for r in csv.DictReader((run / "review/image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig")):
        csv_rows[(r["group_id"], r["printed_number"], r["card_name"])].append(r)
    new_rows = [json.loads(l) for l in (run / "new-or-incomplete-printings.jsonl").open()]
    chosen, stats, by_sha = [], Counter(), defaultdict(list)
    for item in new_rows:
        row = csv_rows[(item["group_id"], item["printed_number"], item["card_name"])].pop(0)
        best = None
        seen = 0
        for rank, col, rel in candidates(row, run):
            path = REPO / rel
            if not path.exists():
                continue
            seen += 1
            try:
                facts = load_facts(path)
            except Exception:
                continue
            side = min(facts.width, facts.height)
            if side < MIN_SIDE or facts.blur is None or facts.blur < BLUR_LIMIT:
                continue
            key = (-side, rank)
            if best is None or key < best[0]:
                best = (key, rel, col, facts)
        out = {"group_id": item["group_id"], "printed_number": item["printed_number"], "card_name": item["card_name"]}
        if best is None:
            out["status"] = "no_file" if seen == 0 else "failed_gate"
        else:
            _, rel, col, facts = best
            sha = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
            out.update(status="chosen", file=rel, source=col, width=facts.width, height=facts.height,
                       blur=round(facts.blur, 1), sha256=sha, upgrade_later=min(facts.width, facts.height) < UPGRADE_BELOW)
            by_sha[sha].append(out)
        stats[out["status"]] += 1
        chosen.append(out)
    for rows in by_sha.values():
        for dup in rows[1:]:
            dup["status"] = "duplicate_file"
            dup["duplicate_of"] = f'{rows[0]["group_id"]}:{rows[0]["printed_number"]}'
            stats["chosen"] -= 1
            stats["duplicate_file"] += 1
    (run / "image-chosen.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in chosen))
    ok = [r for r in chosen if r["status"] == "chosen"]
    summary = {
        "new_rows": len(chosen), "status": dict(stats),
        "upgrade_later": sum(r["upgrade_later"] for r in ok),
        "by_source": dict(Counter(r["source"] for r in ok)),
        "min_side": MIN_SIDE, "blur_limit": BLUR_LIMIT,
    }
    (run / "image-chosen-summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
