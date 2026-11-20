"""Hold back Japanese names that would split a name group (rules 5 and 6 of docs/catalogue-names-families-20261114.md).

    python3 hold_split_names.py NAMES_JSON CATALOG_SQLITE OUT_JSON

The server groups same-art Japanese printings by their exact `name`. A rename is kept only when every
`ja` row carrying that English name is renamed, to one spelling; otherwise every rename of that English
name moves to "review" with its candidate. CP6 (20th Anniversary) renames are held first: their PMCG1
originals are already Japanese, and the shared name moved Base Set photos to the reprint in the LINKS1 gate.
"""
import collections, json, sqlite3, sys

names_path, db_path, out_path = sys.argv[1:4]
d = json.load(open(names_path))
acc = d["accepted"]


def hold(cid, reason):
    v = acc.pop(cid)
    d["review"].append({"id": cid, "en": v["en"], "limitless": v.get("limitless", ""), "name_ja": v["name_ja"],
                        "reason": reason})


d["held_cp6"] = sorted(k for k in acc if k.startswith("ja:CP6-"))
for cid in d["held_cp6"]:
    hold(cid, "held: CP6 reprint of PMCG1")
by_name = collections.defaultdict(set)
for cid, name in sqlite3.connect(db_path).execute("SELECT id, name FROM cards WHERE language='ja'"):
    by_name[name].add(cid)
groups = collections.defaultdict(set)
for cid, v in acc.items():
    groups[v["en"]].add(cid)
d["held_split"] = []
for en, ids in sorted(groups.items()):
    if not (ids >= by_name[en] and len({acc[i]["name_ja"] for i in ids}) == 1):
        for cid in sorted(ids):
            hold(cid, f"held: other ja rows named {en!r} keep the English name (no-split rule)")
            d["held_split"].append(cid)
json.dump(d, open(out_path, "w"), ensure_ascii=False)
print(json.dumps({"accepted": len(acc), "held_cp6": len(d["held_cp6"]), "held_split": len(d["held_split"])}))
