"""Write the candidate SQL that fills 285 English rarities (RAR2). Read-only on PlanetScale.

    python3 prepare_rar1.py ROLE_JSON

One transaction: check the parent's import manifest md5, clone the nine tables of the parent into
the target schema with the parent's read grants, set the 285 rarities (only where still NULL),
set the cards digest, the feature manifest hash and the release names in the import manifest,
append a corrections entry, and raise on any count, rarity or digest mismatch. The parent is not
changed. Writes sql/candidate.sql and sql/prepared.json.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/ioannischadjiminas/WebstormProjects/scanapp/api/scripts/ja_set_recovery")
from prepare_sql import TABLES, connect, jlit, lit, token  # noqa: E402

PARENT = "pokesingle_completion_20261127_rar1"
PARENT_IMPORT = "PS-CATALOGUE-EN-JA-RAR1-20261127"
TARGET = "pokesingle_completion_20261127_rar2"
IMPORT = "PS-CATALOGUE-EN-JA-RAR2-20261127"
HERE = Path.cwd()  # the run folder: rarities.json, features.json; writes sql/ there


def main(role_file):
    rarities = json.loads((HERE / "rarities.json").read_text())
    features = json.loads((HERE / "features.json").read_text())
    conn = connect(role_file)
    conn.execute("SET statement_timeout = '300s'")
    status, meta, meta_md5 = conn.execute(
        f"SELECT status, metadata, md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id=%s",
        (PARENT_IMPORT,)).fetchone()
    assert status == "validated" and meta["target"]["schema"] == PARENT
    assert meta["reference_feature_manifest_sha256"] == features["parent_sha256"]
    assert conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (TARGET,)).fetchone()[0] == 0
    counts = {t: conn.execute(f"SELECT count(*) FROM {PARENT}.{t}").fetchone()[0] for t in TABLES}
    digest = meta["digests"]["cards"]
    cols = digest["columns"]
    at = cols.index("rarity")
    old_hashes, new_hashes, changed = [], [], 0
    with conn.cursor(name="cards_digest") as cur:
        cur.execute(f"SELECT {','.join(cols)} FROM {PARENT}.cards ORDER BY {digest['keys'][0]} COLLATE \"C\"")
        while rows := cur.fetchmany(2000):
            for row in rows:
                old_hashes.append(hashlib.md5("|".join(token(v) for v in row).encode()).hexdigest())
                if row[0] in rarities:
                    assert row[at] is None, row[0]
                    row = list(row)
                    row[at] = rarities[row[0]]
                    changed += 1
                new_hashes.append(hashlib.md5("|".join(token(v) for v in row).encode()).hexdigest())
    conn.close()
    assert changed == len(rarities) == 285
    assert len(old_hashes) == meta["counts"]["cards"]
    old_md5 = hashlib.md5("".join(old_hashes).encode()).hexdigest()
    assert old_md5 == digest["md5"], "loader digest not reproduced"
    cards_md5 = hashlib.md5("".join(new_hashes).encode()).hexdigest()

    s = ["BEGIN;", "SET LOCAL statement_timeout = '900s';",
         "LOCK TABLE " + ", ".join(f"{PARENT}.{t}" for t in TABLES) + " IN SHARE MODE;",
         f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)} "
         f"AND status='validated' AND md5(metadata::text)={lit(meta_md5)}) THEN RAISE EXCEPTION 'Parent release changed; rebuild candidate'; END IF; END $$;",
         f"CREATE SCHEMA {TARGET};"]
    for t in TABLES:
        s.append(f"CREATE TABLE {TARGET}.{t} (LIKE {PARENT}.{t} INCLUDING ALL);")
        s.append(f"INSERT INTO {TARGET}.{t} SELECT * FROM {PARENT}.{t};")
    s.append(f"""DO $acl$ DECLARE item record; recipient text; BEGIN
 FOR item IN SELECT acl.grantee FROM pg_namespace n, LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) acl
  WHERE n.nspname='{PARENT}' AND acl.privilege_type='USAGE' LOOP
  recipient:=CASE WHEN item.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(item.grantee)) END;
  EXECUTE 'GRANT USAGE ON SCHEMA {TARGET} TO ' || recipient; END LOOP;
 FOR item IN SELECT c.relname,acl.grantee FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
  LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl
  WHERE n.nspname='{PARENT}' AND c.relkind='r' AND acl.privilege_type='SELECT' LOOP
  recipient:=CASE WHEN item.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(item.grantee)) END;
  EXECUTE 'GRANT SELECT ON TABLE {TARGET}.' || quote_ident(item.relname) || ' TO ' || recipient; END LOOP;
END $acl$;""")
    s.append(f"UPDATE {TARGET}.cards AS c SET rarity = x.rarity FROM jsonb_each_text({jlit(rarities)}::jsonb) AS x(id, rarity) "
             f"WHERE c.id = x.id AND c.rarity IS NULL;")
    correction = {
        "date": "2026-11-27", "rows": len(rarities), "table": "cards",
        "change": "285 English rarities filled: 35 from TCGdex, 214 reprints and alternates from their original card "
                  "(name and number matched; alternates also agree with pokemontcg.io), 28 Unseen Forces Unown from the printed "
                  "star. The 5 Ultra Rare cards' reference features rebuilt with the full-art box.",
        "rollback": "scanapp docs/catalogue-english-rarity-20261127.md", "md5_before": digest["md5"], "md5_after": cards_md5,
    }
    patch = {
        "parent_schema": PARENT, "parent_import_id": PARENT_IMPORT,
        "rebuilt_from": {"schema": PARENT, "import_id": PARENT_IMPORT, "metadata_md5": meta_md5},
        "reference_feature_manifest_sha256": features["manifest_sha256"],
        "state": "candidate_rarity_en_inactive", "activation_allowed": False,
        "corrections": list(meta.get("corrections") or []) + [correction],
        "english_rarities": {"cards": len(rarities), "decisions": "data/catalogue-gaps/rar2-en-20261127/decisions.json",
                             "features_rebuilt": features["rebuilt"], "feature_dir": "20261127-rar2"},
    }
    s.append(f"UPDATE {TARGET}.import_manifest SET metadata = jsonb_set(jsonb_set(metadata,'{{digests,cards,md5}}',{jlit(cards_md5)}::jsonb),"
             f"'{{target,schema}}',{jlit(TARGET)}::jsonb) || {jlit(patch)}::jsonb, validated_at = now(), import_id = {lit(IMPORT)} "
             f"WHERE import_id={lit(PARENT_IMPORT)};")
    checks = [f"(SELECT count(*) FROM {TARGET}.{t})={counts[t]}" for t in TABLES]
    checks += [
        f"(SELECT count(*) FROM {TARGET}.import_manifest WHERE import_id={lit(IMPORT)} AND status='validated')=1",
        f"(SELECT count(*) FROM {TARGET}.cards c JOIN jsonb_each_text({jlit(rarities)}::jsonb) x(id, rarity) ON c.id = x.id AND c.rarity = x.rarity)={len(rarities)}",
        f"(SELECT count(*) FROM {TARGET}.cards c JOIN {PARENT}.cards p USING (id) WHERE c.rarity IS DISTINCT FROM p.rarity)={len(rarities)}",
        f"(SELECT md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)})={lit(meta_md5)}",
    ]
    s.append("DO $$ BEGIN IF NOT (" + " AND ".join(checks) + ") THEN RAISE EXCEPTION 'rar2 checks failed'; END IF; END $$;")
    s.append("COMMIT;")
    (HERE / "sql").mkdir(exist_ok=True)
    (HERE / "sql/candidate.sql").write_text("\n".join(s) + "\n")
    report = {"target": TARGET, "import_id": IMPORT, "parent": PARENT, "parent_metadata_md5": meta_md5,
              "cards_md5_before": digest["md5"], "cards_md5_after": cards_md5, "rarities": len(rarities),
              "feature_manifest_sha256": features["manifest_sha256"], "counts": counts,
              "sql_sha256": hashlib.sha256((HERE / "sql/candidate.sql").read_bytes()).hexdigest()}
    (HERE / "sql/prepared.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
