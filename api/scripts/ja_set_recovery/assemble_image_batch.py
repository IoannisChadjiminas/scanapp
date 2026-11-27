"""Turn eye-checked image candidates into build_image_batch.py inputs. No database access.

    python3 assemble_image_batch.py RUN_DIR CARDS_JSON ACCEPTED_JSONL

RUN_DIR holds the worklist; CARDS_JSON is the parent catalogue snapshot ({"rows": [...]}: every card with
id, image_path, rarity, name, view_title, set_id, set_name); ACCEPTED_JSONL has one line per accepted image
({id, file, image_url, page_url, source, sha256, match}). Writes RUN_DIR/fill.jsonl, RUN_DIR/set-registry.json
(era per set: Sun & Moon onward is modern, so it may get vectors; English rows count as modern, as in batch G)
and, after the build, signature rows via --signature BATCH_DIR.
Names are not changed: name and view_title keep their parent values.
An accepted line with "new_row_from" (and "collector_number") adds a new catalogue row: one more real card
behind a checklist name that covered several. It copies the named row's name, set and other columns.
"""
import hashlib
import json
import sys
from pathlib import Path

MODERN_JA = {
    "SMB": "Sun & Moon Era", "SMC": "Sun & Moon Era", "SMK": "Sun & Moon Era", "SMN": "Sun & Moon Era",
    "SMP": "Sun & Moon Era", "SP": "Sword & Shield Era", "SP1": "Sword & Shield Era", "SP2": "Sword & Shield Era",
    "SLL": "Sword & Shield Era", "jr-scarlet-violet-energies": "Scarlet & Violet Era",
    "jr-mega-evolution-energies": "Mega Evolution Era",
}
SOURCE_KIND = {  # provenance labels, in the style of the earlier batches
    "limitless": "limitless_source_files", "pokemon-card.com": "official_pokemon_card_site",
    "pooka": "pooka_source_files", "tcgdex": "tcgdex_high_resolution_files", "tcgcollector": "tcgcollector_scan",
    "pokemontcg.io": "pokemon_tcg_io_source_files", "pokedatavault": "pokedatavault_source_files",
    "tcgstats": "tcgstats_source_files", "binderboss": "binderboss_source_files", "supercartas": "supercartas_source_files",
}


def main(run_dir, cards_json, accepted):
    run = Path(run_dir)
    rows = {r["id"]: r for r in json.loads(Path(cards_json).read_text())["rows"]}
    fills, groups = [], {}
    for line in Path(accepted).read_text().splitlines():
        a = json.loads(line)
        if a.get("new_row_from"):
            assert a["id"] not in rows, a["id"]
            r = rows[a["new_row_from"]]
        else:
            r = rows[a["id"]]
            assert not r["has_image"], a["id"]
        data = Path(a["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == a["sha256"], a["id"]
        lang = a["id"].split(":", 1)[0]
        era = "English" if lang == "en" else MODERN_JA.get(r["set_id"], "Older Era")
        groups[r["set_id"]] = {"group_id": r["set_id"], "era": "Mega Evolution Era" if lang == "en" else era, "line": 1}
        fills.append({"id": a["id"], "file": a["file"], "group_id": r["set_id"], "official_name_ja": r["name"],
                      "name": r["view_title"], "set_name": r["set_name"], "detail_url": a.get("page_url"),
                      "image_url": a["image_url"], "official_card_id": None, "official_number": a.get("match"),
                      "sha256": a["sha256"], "source_kind": SOURCE_KIND.get(a["source"], a["source"] + "_source_files"),
                      **{k: a[k] for k in ("new_row_from", "collector_number", "tcgc_label") if a.get(k)}})
    assert len({f["id"] for f in fills}) == len(fills)
    assert len({f["sha256"] for f in fills}) == len(fills), "one image file for two rows"
    (run / "fill.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in fills))
    (run / "set-registry.json").write_text(json.dumps(sorted(groups.values(), key=lambda g: g["group_id"]), ensure_ascii=False) + "\n")
    print(json.dumps({"fills": len(fills), "groups": len(groups)}))


def signature(cards_json, batch_dir):
    rows = json.loads(Path(cards_json).read_text())["rows"]
    updates = json.loads((Path(batch_dir) / "updates.json").read_text())
    upd = {u["id"]: u["image_path"] for u in updates}
    by_id = {r["id"]: r for r in rows}
    sig = [{"id": r["id"], "image_path": upd.get(r["id"], r["image_path"]), "rarity": r["rarity"]} for r in rows]
    sig += [{"id": u["id"], "image_path": u["image_path"], "rarity": by_id[u["new_row_from"]]["rarity"]}
            for u in updates if u.get("new_row_from")]
    (Path(batch_dir) / "signature-rows.json").write_text(json.dumps(sig, ensure_ascii=False) + "\n")
    print(json.dumps({"signature_rows": len(sig), "updated": len(upd)}))


if __name__ == "__main__":
    if sys.argv[1] == "--signature":
        signature(sys.argv[2], sys.argv[3])
    else:
        main(*sys.argv[1:4])
