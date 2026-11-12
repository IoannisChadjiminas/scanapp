"""Build the new-card records for the Japanese recovery. Offline, no database writes.

    python3 prepare_cards.py RUN_DIR CATALOGUE_SETS_JSON

One record per new checklist row (new-or-incomplete-printings.jsonl), in the shape of
data/catalogue-gaps/tcgdex-empty-sets-20261017/cards.json plus Cardmarket fields.

Set ids: a partial set keeps the catalogue's own code (the first one that is not a
pooka-/pc-/ra- helper code). An absent set uses its checklist code when that code is
unique in the registry and not already a catalogue set; otherwise `jr-<slug of name>`.
Collector numbers are the printed number before the slash, without a "No." prefix. Unnumbered rows get
`u<NN>` in checklist order. Names are the English checklist names (owner decision 3:
no official Japanese name is available for these rows). Rows without a chosen image
are kept with `local_file: null` (owner decision 4). Every id is checked unique
against the catalogue snapshot and the batch.

Writes cards.json and cards-summary.json in RUN_DIR.
"""
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

LANG = os.environ.get("JAREC_LANGUAGE", "ja")  # "en" for English rows (second batch D); default keeps the Japanese recovery
HELPER = ("pooka-", "pc-", "ra-")


def slug(text):
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def main(run_dir, catalogue_path):
    run = Path(run_dir)
    registry = {g["group_id"]: g for g in json.loads((run / "set-registry.json").read_text())}
    catalogue = json.loads(Path(catalogue_path).read_text())
    taken_ids = {card["id"] for cards in catalogue.values() for card in cards}
    code_count = Counter(g["code"] for g in registry.values() if g["code"])

    def set_id_for(group):
        if group["coverage"] == "partial_by_count":
            own = [c for c in group["catalogue_codes"] if not c.startswith(HELPER)]
            if own:
                return own[0]
        code = group["code"]
        code = re.sub(r"[^A-Za-z0-9-]", "", code.replace("+", "p").replace(" ", "-"))
        if code and code_count[group["code"]] == 1 and code not in catalogue:
            return code
        return "jr-" + slug(group["name"])

    images = {}
    for line in (run / "image-chosen.jsonl").open():
        row = json.loads(line)
        images.setdefault((row["group_id"], row["printed_number"], row["card_name"]), []).append(row)
    links = {}
    for name in ("verified-mappings.jsonl", "held-mappings.jsonl"):
        for line in (run / name).open():
            row = json.loads(line)
            links.setdefault((row["group_id"], row["printed_number"], row["card_name"]), []).append(row)

    cards, seen, unnumbered = [], set(), defaultdict(int)
    for line in (run / "new-or-incomplete-printings.jsonl").open():
        row = json.loads(line)
        key = (row["group_id"], row["printed_number"], row["card_name"])
        group = registry[row["group_id"]]
        set_id = set_id_for(group)
        printed = row["printed_number"].strip()
        head = printed.split("/")[0].strip()
        match = None if "unnum" in head.lower() else re.search(r"([A-Za-z]{0,3}\d+[a-z]?)\s*$", head)
        if not match and "unnum" not in head.lower() and re.fullmatch(r"[A-Z]{1,3}", head):
            match = re.search(r"([A-Z]{1,3})$", head)  # letter numbers, e.g. 30th Celebration Mew B, G, R
        if match:
            number = match.group(1)
        else:
            unnumbered[set_id] += 1
            number = f"u{unnumbered[set_id]:02d}"
            while f"{LANG}:{set_id}-{number}" in taken_ids:
                unnumbered[set_id] += 1
                number = f"u{unnumbered[set_id]:02d}"
        card_id = f"{LANG}:{set_id}-{number}"
        image = images[key].pop(0)
        link = links[key].pop(0)
        total = re.match(r"\s*\d+", printed.split("/")[1]) if "/" in printed else None
        card = {
            "id": card_id, "provider_id": f"{set_id}-{number}", "name": row["card_name"],
            "set_id": set_id, "set_name": group["name"], "collector_number": number,
            "printed_number": printed, "language": LANG, "rarity": "",
            "group_id": row["group_id"],
            "local_file": image.get("file") if image["status"] == "chosen" else None,
            "image_status": image["status"], "image_source": image.get("source"),
            "width": image.get("width"), "height": image.get("height"), "blur": image.get("blur"),
            "image_sha256": image.get("sha256"), "upgrade_later": image.get("upgrade_later", False),
            "printed_total": int(total.group(0)) if total else None,
            "cardmarket_url": link.get("url") if link["status"] == "linked" else None,
            "cardmarket_id": link.get("product_id") if link["status"] == "linked" else None,
            "cardmarket_status": link["status"] if link["status"] == "linked" else link.get("reason"),
            **{k: row[k] for k in ("source_row_url", "source_image_url", "remote_image_url") if row.get(k)},
        }
        card["problem"] = ("id_taken_in_catalogue" if card_id in taken_ids
                           else "id_repeated_in_batch" if card_id in seen else None)
        seen.add(card_id)
        cards.append(card)

    cards.sort(key=lambda c: c["id"].encode())
    (run / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1) + "\n")
    summary = {
        "cards": len(cards),
        "with_image": sum(bool(c["local_file"]) for c in cards),
        "with_cardmarket_url": sum(bool(c["cardmarket_url"]) for c in cards),
        "with_cardmarket_id": sum(bool(c["cardmarket_id"]) for c in cards),
        "image_and_url": sum(bool(c["local_file"] and c["cardmarket_url"]) for c in cards),
        "set_ids": len({c["set_id"] for c in cards}),
        "jr_set_ids": len({c["set_id"] for c in cards if c["set_id"].startswith("jr-")}),
        "unnumbered": sum(c["collector_number"].startswith("u") for c in cards),
        "problems": dict(Counter(c["problem"] for c in cards if c["problem"])),
    }
    (run / "cards-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
