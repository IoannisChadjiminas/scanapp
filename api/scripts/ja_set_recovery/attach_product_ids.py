"""Attach Cardmarket product ids (from read_product_ids.py) to verified mappings. Offline.

    python3 attach_product_ids.py RUN_DIR

An id is attached only when the list-view row for exactly that product URL gave it,
and no other mapped row received the same id. Rows without an id keep their link
and get `product_id: null` with a reason. Rewrites verified-mappings.jsonl in place
(the previous file is kept as verified-mappings.before-ids.jsonl) and writes
product-id-summary.json plus product-ids.txt (one id per line, for the catalogue check).
"""
import json
import sys
from collections import Counter
from pathlib import Path


def norm(url):
    return url.rstrip("/").split("?")[0]


def main(run_dir):
    run = Path(run_dir)
    ids = {}
    for line in (run / "cardmarket-ids.jsonl").open():
        if line.strip():
            row = json.loads(line)
            ids.setdefault(norm(row["url"]), set()).add(str(row["product_id"]))
    rows = [json.loads(l) for l in (run / "verified-mappings.jsonl").open()]
    (run / "verified-mappings.before-ids.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    for row in rows:
        found = ids.get(norm(row["url"]), set())
        row.pop("product_id_reason", None)
        if len(found) == 1:
            row["product_id"] = next(iter(found))
        else:
            row["product_id"] = None
            row["product_id_reason"] = "not_in_list_view" if not found else "several_ids_for_url"
    claims = Counter(r["product_id"] for r in rows if r["product_id"])
    for row in rows:
        if row["product_id"] and claims[row["product_id"]] > 1:
            row["product_id"] = None
            row["product_id_reason"] = "id_on_several_rows"

    (run / "verified-mappings.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    got = [r["product_id"] for r in rows if r["product_id"]]
    (run / "product-ids.txt").write_text("\n".join(got) + "\n")
    summary = {"linked": len(rows), "with_product_id": len(got),
               "without": dict(Counter(r["product_id_reason"] for r in rows if not r["product_id"]))}
    (run / "product-id-summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
