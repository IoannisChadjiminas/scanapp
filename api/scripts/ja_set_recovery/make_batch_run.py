"""Turn rows of docs/outside-list-missing-rows-20261111.json into a run folder for the release scripts.

    python3 -I make_batch_run.py RUN_DIR CATALOGUE_SETS_JSON BATCH_SPEC_JSON

BATCH_SPEC_JSON:
  {"batch": "a2", "checklist_source": "limitless-20261111",
   "sets": [{"source_set": "SAf", "name": "Starter Set V (Fighting)", "code": "SAf", "line": 800,
             "image_dir": "data/catalogue-gaps/<run>/SAf", "printed_total": 25, "new_set": true,
             "include_status": ["missing"]}, ...]}

For each listed set it selects the rows of the rows file (ja, row_source limitless, source_set, the
given statuses), drops rows whose number the catalogue snapshot already holds in that set, and writes
the files the other scripts read: set-registry.json, new-or-incomplete-printings.jsonl,
held-mappings.jsonl (Cardmarket links are not verified here: they go on the browser worklist),
verified-mappings.jsonl (empty), review/image-coverage-reconciliation-20261030.csv (one image column,
`limitless_source_files`, only when the file exists and the eye check accepted it) and
already-present.json. Names are the Japanese names of the rows file.

The eye check is separate: ACCEPTED_JSON (RUN_DIR/eye-check.json, written by hand after looking at
every image) maps `<source_set>:<number>` to "accepted" or to a rejection reason; a row without an
entry is not given an image. CATALOGUE_SETS_JSON is {set_id: [{"id": ..., "collector_number": ...}]}.
"""
import csv
import json
import sys
from pathlib import Path

ROWS = Path(__file__).resolve().parents[3] / "docs/outside-list-missing-rows-20261111.json"


def main(run_dir, catalogue_path, spec_path):
    run = Path(run_dir)
    spec = json.loads(Path(spec_path).read_text())
    catalogue = json.loads(Path(catalogue_path).read_text())
    rows = json.loads(ROWS.read_text())["rows"]
    eye_path = run / "eye-check.json"
    eye = json.loads(eye_path.read_text()) if eye_path.exists() else {}
    registry, new_rows, held, recon, present = [], [], [], [], []
    for entry in spec["sets"]:
        code = entry["source_set"]
        selected = [r for r in rows if r["language"] == "ja" and r["source_set"] == code
                    and r["row_source"] == entry.get("row_source", "limitless")
                    and r["status"] in entry.get("include_status", ["missing"])]
        if entry.get("numbers"):
            selected = [r for r in selected if r["number"] in entry["numbers"]]
        have = catalogue.get(entry.get("catalogue_set", code), [])
        have_numbers = {str(c.get("collector_number", "")).lstrip("0") for c in have}
        group_id = f"second-batch-{spec['batch']}-{code}"
        registry.append({"group_id": group_id, "name": entry["name"], "code": entry["code"],
                         "line": entry["line"],
                         "coverage": "partial_by_count" if have else "absent",
                         "catalogue_codes": [entry.get("catalogue_set", code)] if have else [],
                         "catalogue_rows": len(have), "checklist_source": spec["checklist_source"]})
        total = entry.get("printed_total")
        for row in selected:
            number = row["number"]
            if number.isdigit() and number.lstrip("0") in have_numbers:
                present.append(row)
                continue
            if number.isdigit():
                printed = f"{int(number):03d}/{total:03d}" if total else f"{int(number):03d}"
            else:
                printed = f"unnumbered ({number})"
            card = {"group_id": group_id, "printed_number": printed, "card_name": row["name"],
                    "status": "new", "catalogue_ids": [], "evidence": row["row_url"],
                    "source_row_url": row["row_url"]}
            if row.get("image_url"):
                card["source_image_url"] = row["image_url"]
            new_rows.append(card)
            held.append({"group_id": group_id, "printed_number": printed, "card_name": row["name"],
                         "status": "held", "reason": "not_verified_on_cardmarket_browser_worklist"})
            suffix = f"{int(number):03d}" if number.isdigit() else number
            image = Path(entry["image_dir"]) / f"{code}_{suffix}.png"
            ok = eye.get(f"{code}:{number}") == "accepted" and image.is_file()
            recon.append({"group_id": group_id, "printed_number": printed, "card_name": row["name"],
                          "limitless_source_files": str(image) if ok else ""})
    (run / "review").mkdir(exist_ok=True)
    (run / "set-registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    (run / "new-or-incomplete-printings.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new_rows))
    (run / "held-mappings.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in held))
    (run / "verified-mappings.jsonl").write_text("")
    (run / "already-present.json").write_text(json.dumps(present, ensure_ascii=False, indent=2) + "\n")
    with (run / "review/image-coverage-reconciliation-20261030.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=["group_id", "printed_number", "card_name", "limitless_source_files"])
        writer.writeheader()
        writer.writerows(recon)
    print(json.dumps({"sets": len(registry), "new_rows": len(new_rows), "already_present": len(present),
                      "with_accepted_image": sum(bool(r["limitless_source_files"]) for r in recon)}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
