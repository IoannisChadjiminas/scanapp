"""Add rarity, category and illustrator to TCGdex rows of a batch's checklist. Network, no database.

    python3 fill_tcgdex_fields.py RUN_DIR

For each row of RUN_DIR/new-or-incomplete-printings.jsonl whose source_row_url is a TCGdex card
(https://api.tcgdex.net/v2/<language>/cards/<id>), reads that card and adds its `rarity`,
`category` and `illustrator`. Run it before prepare_cards.py, which refuses a TCGdex row without a
rarity. Rows from other sources are left as they are. The original file is kept as `.bak`.
A TCGdex card that still has no rarity stops the run: wait for TCGdex rather than store none.
"""
import json
import shutil
import sys
import urllib.request
from pathlib import Path

PREFIX = "https://api.tcgdex.net/v2/"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "catalogue-batch-builder"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main(run_dir, fetch=fetch):
    path = Path(run_dir) / "new-or-incomplete-printings.jsonl"
    rows = [json.loads(line) for line in path.open() if line.strip()]
    missing, filled = [], 0
    for row in rows:
        url = str(row.get("source_row_url") or "")
        if not url.startswith(PREFIX) or "/cards/" not in url:
            continue
        card = fetch(url)
        if not card.get("rarity"):
            missing.append(url)
            continue
        for key in ("rarity", "category", "illustrator"):
            if card.get(key):
                row[key] = card[key]
        filled += 1
    if missing:
        raise SystemExit(f"{len(missing)} TCGdex cards have no rarity yet, e.g. {missing[0]}")
    shutil.copyfile(path, path.with_name(path.name + ".bak"))
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(json.dumps({"rows": len(rows), "tcgdex_filled": filled}))


if __name__ == "__main__":
    main(sys.argv[1])
