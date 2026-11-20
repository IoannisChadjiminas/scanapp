"""Write the inactive-candidate SQL for a names-and-families release: card names and two records.

    PARENT=... PARENT_IMPORT=... TARGET=... IMPORT=... \
      python3 prepare_sql_names.py NAMES_JSON FAMILIES_JSON ROLE_JSON OUT_DIR

Read-only on PlanetScale. NAMES_JSON is match_names.py's output: "accepted" {card_id: {name_ja,
source, check, en}}; each accepted row's `name` becomes name_ja (guarded on its current name, which
must be the English one the match was made from); view_title keeps the English name. FAMILIES_JSON
is families.py's output: "family" {card_id: family_id}, stored whole as the reference_metadata record
`printing-families` (the loader does not read it; the phone exporter takes it with --families).
The name sources go into `catalogue-names-ja:<IMPORT>`.

Nothing else changes: vectors, ids, images, links and the feature and artwork bundles are the
parent's (the feature signature covers id, image_path and rarity, not names). Same transaction
shape as prepare_sql.py: clone the nine tables, change, update the manifest, guard every count.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sql import TABLES, connect, jlit, lit  # noqa: E402
from prepare_sql_cleanup import digest, sha_file  # noqa: E402

PARENT = os.environ.get("PARENT")
PARENT_IMPORT = os.environ.get("PARENT_IMPORT")
TARGET = os.environ.get("TARGET")
IMPORT = os.environ.get("IMPORT")
ACL = """DO $acl$ DECLARE item record; recipient text; BEGIN
 FOR item IN SELECT acl.grantee FROM pg_namespace n, LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) acl
  WHERE n.nspname='{P}' AND acl.privilege_type='USAGE' LOOP
  recipient:=CASE WHEN item.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(item.grantee)) END;
  EXECUTE 'GRANT USAGE ON SCHEMA {T} TO ' || recipient; END LOOP;
 FOR item IN SELECT c.relname,acl.grantee FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
  LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl
  WHERE n.nspname='{P}' AND c.relkind='r' AND acl.privilege_type='SELECT' LOOP
  recipient:=CASE WHEN item.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(item.grantee)) END;
  EXECUTE 'GRANT SELECT ON TABLE {T}.' || quote_ident(item.relname) || ' TO ' || recipient; END LOOP;
END $acl$;"""


def plan_names(rows_by_id, accepted):
    """{card_id: (old, new)}; every accepted row must exist, be ja and still carry the English name.
    A row whose source name equals its current name is left out (nothing to change)."""
    plan = {}
    for cid, v in sorted(accepted.items()):
        row = rows_by_id[cid]
        assert row["language"] == "ja" and cid.startswith("ja:"), cid
        assert row["name"] == v["en"], (cid, row["name"], v["en"])
        assert v["name_ja"] and "\t" not in v["name_ja"] and "\n" not in v["name_ja"], cid
        if v["name_ja"] != row["name"]:  # the Japanese print's name can be the Latin one ("N", "AZ")
            plan[cid] = (row["name"], v["name_ja"])
    return plan


def check_families(family, card_ids):
    assert set(family) <= card_ids and set(family.values()) <= card_ids
    for cid, base in family.items():
        assert family.get(base) == base, (cid, base)  # every family id is its own base


def main(names_path, families_path, role_file, out_dir):
    names = json.loads(Path(names_path).read_text())
    fam_doc = json.loads(Path(families_path).read_text())
    out = Path(out_dir).resolve()
    (out / "sql").mkdir(parents=True, exist_ok=True)
    conn = connect(role_file)
    conn.execute("SET statement_timeout = '300s'")
    status, meta, meta_md5 = conn.execute(
        f"SELECT status, metadata, md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id=%s",
        (PARENT_IMPORT,)).fetchone()
    assert status == "validated" and meta["target"]["schema"] == PARENT
    assert conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (TARGET,)).fetchone()[0] == 0
    counts = {t: conn.execute(f"SELECT count(*) FROM {PARENT}.{t}").fetchone()[0] for t in TABLES}
    cols = meta["digests"]["cards"]["columns"]
    assert "name" in cols
    rows = [dict(zip(cols, r)) for r in conn.execute(
        f'SELECT {",".join(cols)} FROM {PARENT}.cards ORDER BY id COLLATE "C"').fetchall()]
    assert digest(rows, cols) == meta["digests"]["cards"]["md5"]
    by_id = {r["id"]: r for r in rows}
    plan = plan_names(by_id, names["accepted"])
    family = fam_doc["family"]
    check_families(family, set(by_id))
    for r in rows:
        if r["id"] in plan:
            r["name"] = plan[r["id"]][1]
    cards_md5 = digest(rows, cols)

    s = ["BEGIN;", "SET LOCAL statement_timeout = '900s';",
         "LOCK TABLE " + ", ".join(f"{PARENT}.{t}" for t in TABLES) + " IN SHARE MODE;",
         f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)} "
         f"AND status='validated' AND md5(metadata::text)={lit(meta_md5)}) THEN RAISE EXCEPTION 'Parent release changed; rebuild candidate'; END IF; END $$;",
         f"CREATE SCHEMA {TARGET};"]
    for t in TABLES:
        s.append(f"CREATE TABLE {TARGET}.{t} (LIKE {PARENT}.{t} INCLUDING ALL);")
        s.append(f"INSERT INTO {TARGET}.{t} SELECT * FROM {PARENT}.{t};")
    s.append(ACL.format(P=PARENT, T=TARGET))
    items = sorted(plan.items())
    for i in range(0, len(items), 500):
        values = ",".join(f"({lit(cid)},{lit(old)},{lit(new)})" for cid, (old, new) in items[i:i + 500])
        s.append(f"UPDATE {TARGET}.cards c SET name=v.new FROM (VALUES {values}) AS v(id,old,new) "
                 f"WHERE c.id=v.id AND c.name=v.old;")
    sources = {cid: {k: v[k] for k in ("source", "check")} for cid, v in names["accepted"].items()}
    names_record = {"import_id": IMPORT, "parent_import_id": PARENT_IMPORT, "rows": len(plan), "sources": sources,
                    "rule": "set + printed number on a Limitless JP set list, name checked against the English name "
                            "(docs/catalogue-names-families-20261114.md)"}
    families_record = {"rule": fam_doc["rule"], "min_cos": fam_doc["min_cos"], "import_id": IMPORT,
                       "family": family, "families": len(set(family.values())), "rows": len(family),
                       "doc": "docs/catalogue-names-families-20261114.md"}
    s.append(f"INSERT INTO {TARGET}.reference_metadata(source_key,metadata) VALUES "
             f"({lit('catalogue-names-ja:' + IMPORT)},{jlit(names_record)}::jsonb),"
             f"('printing-families',{jlit(families_record)}::jsonb);")
    new_counts = dict(meta["counts"])
    new_counts.update({t: counts[t] for t in TABLES if t != "import_manifest"})
    new_counts["reference_metadata"] = counts["reference_metadata"] + 2
    report = {"target": TARGET, "import_id": IMPORT, "parent": PARENT, "parent_metadata_md5": meta_md5,
              "names_changed": len(plan), "family_rows": len(family), "families": len(set(family.values())),
              "cards_md5": cards_md5}
    patch = {"counts": new_counts, "expected_counts": new_counts,
             "parent_schema": PARENT, "parent_import_id": PARENT_IMPORT,
             "state": "candidate_catalogue_names_families_inactive", "activation_allowed": False,
             "rebuilt_from": {"schema": PARENT, "import_id": PARENT_IMPORT, "metadata_md5": meta_md5},
             "catalogue_names_families_20261114": {k: report[k] for k in ("names_changed", "family_rows", "families")}}
    s.append(f"UPDATE {TARGET}.import_manifest SET metadata = jsonb_set(jsonb_set(metadata,"
             f"'{{digests,cards,md5}}',{jlit(cards_md5)}::jsonb),'{{target,schema}}',{jlit(TARGET)}::jsonb) || {jlit(patch)}::jsonb, "
             f"validated_at = now(), import_id = {lit(IMPORT)} WHERE import_id={lit(PARENT_IMPORT)};")
    new_ids = ",".join(lit(cid) for cid, _ in items)
    checks = [f"(SELECT count(*) FROM {TARGET}.{t})={new_counts[t]}" for t in TABLES if t != "import_manifest"]
    checks += [
        f"(SELECT count(*) FROM {TARGET}.import_manifest WHERE import_id={lit(IMPORT)} AND status='validated')=1",
        f"(SELECT count(*) FROM {TARGET}.cards c JOIN {PARENT}.cards p ON p.id=c.id WHERE c.name IS DISTINCT FROM p.name)={len(plan)}",
        f"(SELECT count(*) FROM {TARGET}.cards c JOIN {PARENT}.cards p ON p.id=c.id WHERE c.name IS DISTINCT FROM p.name AND c.id NOT IN ({new_ids}))=0",
        f"(SELECT count(*) FROM {TARGET}.cards c JOIN {PARENT}.cards p ON p.id=c.id WHERE (c.view_title IS DISTINCT FROM p.view_title) OR (c.image_path IS DISTINCT FROM p.image_path) OR (c.cardmarket_url IS DISTINCT FROM p.cardmarket_url))=0",
        f"(SELECT md5(metadata::text) FROM {TARGET}.reference_metadata WHERE source_key='vector-manifest:pad')="
        f"(SELECT md5(metadata::text) FROM {PARENT}.reference_metadata WHERE source_key='vector-manifest:pad')",
        f"(SELECT md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)})={lit(meta_md5)}",
    ]
    s.append("DO $$ BEGIN IF NOT (" + " AND ".join(checks) + ") THEN RAISE EXCEPTION 'names-families checks failed'; END IF; END $$;")
    s.append("COMMIT;")
    (out / "sql/candidate.sql").write_text("\n".join(s) + "\n")
    report.update(counts=new_counts, sql_sha256=sha_file(out / "sql/candidate.sql"),
                  sql_bytes=(out / "sql/candidate.sql").stat().st_size, statements=len(s))
    (out / "sql/prepared.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "counts"}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
