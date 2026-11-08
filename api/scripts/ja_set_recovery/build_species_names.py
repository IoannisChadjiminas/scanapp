"""Build the Japanese species table used by RANK_SPECIES_NAMES from the served catalogue.

    PLANETSCALE_DATABASE_URL=... python3 build_species_names.py SCHEMA IMPORT_ID OUT_JSON

Source pairs: Japanese Pokemon rows from Sun & Moon onward, which carry the official Japanese
name in `name` and the English title in `view_title`. Older-era Japanese names are not used: part
of them are machine transliterations (マチャンプ for Machamp). Titles are reduced to species on
both sides (forms, owners, mechanics). An English species enters the table only when one Japanese
species holds at least DOMINANCE of its rows and appears on at least MIN_ROWS rows. Nothing is
written by hand. The output records the schema, import id, counts, and every rejected species.
"""
import collections
import json
import re
import sys
import unicodedata

MODERN = re.compile(r"^(SM|S[0-9]|SV|M[0-9]|MC|S-P)")
DOMINANCE = .8
MIN_ROWS = 2

EN_PREFIX = re.compile(r"^(?:m|mega|primal|radiant|shining|dark|light|alolan|galarian|hisuian|paldean|"
                       r"team rocket's|rocket's|[a-z.]+(?:\s[a-z.]+)?'s)\s+")
EN_SUFFIX = re.compile(r"(?:[\s-](?:ex|gx|v|vmax|vstar|v-union|break|lv\.x|lv\.?\s?\d+|prime|legend|star|δ|[xy]))+$")
MEGA = re.compile(r"^(?:m|mega)\s", re.I)
JA_MEGA = re.compile(r"^(?:メガ|M)")
OWNER = re.compile(r"^(?:team rocket's|rocket's|[a-z.]+(?:\s[a-z.]+)?'s)\s", re.I)
JA_OWNER = re.compile(r"^.{1,12}の")
JA_PREFIX = re.compile(r"^(?:ゲンシ|かがやく|ひかる|わるい|アローラ|ガラル|ヒスイ|パルデア)")
JA_SUFFIX = re.compile(r"(?:ex|EX|GX|V-UNION|V|VMAX|VSTAR|BREAK|LV\.X|[XY]|☆|δ)+$")


def en_species(title: str) -> str | None:
    t = unicodedata.normalize("NFKC", title).lower().strip()
    t = re.sub(r"\s*[\[(].*$", "", t)  # provider annotations: "Pikachu [SV-P]", "(MA1 184)from N/A"
    if "&" in t or not t:
        return None
    for _ in range(2):
        t = EN_PREFIX.sub("", t).strip()
    t = EN_SUFFIX.sub("", t).strip()
    return t or None


def ja_species(name: str, mega: bool = False, owner: bool = False) -> str | None:
    """`mega` / `owner`: the English title is a Mega form or names an owner, so a leading メガ/M or
    "…の" is not part of the species (メガニウム is Meganium; あかつきのつばさネクロズマ is a form)."""
    n = unicodedata.normalize("NFKC", name).strip().replace(" ", "")
    if "&" in n or not n:
        return None
    n = JA_SUFFIX.sub("", n)
    if mega:
        n = JA_MEGA.sub("", n, count=1)
    if owner:
        n = JA_OWNER.sub("", n, count=1)
    n = JA_PREFIX.sub("", n, count=1)
    n = JA_SUFFIX.sub("", n)
    return n if len(n) >= 2 else None


def build(rows):
    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for set_id, name, title in rows:
        if not MODERN.match(set_id or "") or not name or not title:
            continue
        if not re.search(r"[^\x00-\x7f]", name) or re.search(r"[^\x00-\x7f]", title):
            continue
        en, ja = en_species(title), ja_species(name, mega=bool(MEGA.match(title.strip())),
                                                owner=bool(OWNER.match(title.strip())))
        if en and ja:
            counts[en][ja] += 1
    species, rejected = {}, {}
    for en, c in sorted(counts.items()):
        (ja, top), total = c.most_common(1)[0], sum(c.values())
        if top >= MIN_ROWS and top / total >= DOMINANCE:
            species[en] = ja
        else:
            rejected[en] = dict(c.most_common(4))
    # One Japanese species may only name one English species.
    owners = collections.defaultdict(list)
    for en, ja in species.items():
        owners[ja].append(en)
    for ja, ens in owners.items():
        if len(ens) > 1:
            for en in ens:
                rejected[en] = {species.pop(en): "shared"}
    return species, rejected


def main(schema, import_id, out):
    import os

    import certifi
    import psycopg
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise SystemExit("bad schema")
    with psycopg.connect(os.environ["PLANETSCALE_DATABASE_URL"], port=6432, sslmode="verify-full",
                         sslrootcert=certifi.where(), autocommit=True) as pg:
        rows = pg.execute(f"select set_id, name, view_title from {schema}.cards "
                          "where language='ja' and category='Pokemon'").fetchall()
    species, rejected = build(rows)
    json.dump({"schema": schema, "import_id": import_id, "source": "ja Pokemon rows, Sun & Moon onward",
               "dominance": DOMINANCE, "min_rows": MIN_ROWS, "species_count": len(species),
               "species": species, "rejected": rejected},
              open(out, "w"), ensure_ascii=False, indent=0, sort_keys=False)
    print(len(species), "species,", len(rejected), "rejected")


if __name__ == "__main__":
    main(*sys.argv[1:4])
