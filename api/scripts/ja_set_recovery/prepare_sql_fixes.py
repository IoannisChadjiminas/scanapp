"""Write the inactive-candidate SQL for card-row fixes (names and Cardmarket links) only.

    PARENT=... PARENT_IMPORT=... TARGET=... IMPORT=... \
      python3 prepare_sql_fixes.py FIXES_JSON ROLE_JSON OUT_DIR

Read-only on PlanetScale. FIXES_JSON maps card id -> any of: name_ja, name_en (with name_source),
url/product_name/product_id (new Cardmarket link), clear_link + reason (drop a link),
relink {url, old_url} + reason (a card that holds another product's page: the page changes, the
product id stays; the new page must be the product the crawl already matched to this card),
set {column: value} + reason for plain label columns (SET_COLUMNS),
display_image_url + display_reason (a page-only image for a card with no image: remote_image_url
only, has_image stays 0, so no features and no vectors).
A row an image-delivery alias points at or from cannot have its identity columns changed here:
the alias contract stores a checksum of them.
FIX_KEY, FIX_STATE, FIX_PROVENANCE and FIX_VERIFIED_AT (optional env) name the manifest entry, the
manifest state and the provenance of a new or changed link for batches after the name-and-link fixes.
COVERAGE_QUEUE (optional env, a JSON list of {id, status, reason}) is stored in the import manifest
as `coverage_queue`: the recorded reason for every card that is neither scannable nor a printing
alternative. Vectors,
artwork, features and images are unchanged, so the parent's vector/artwork metadata and feature
manifest stay valid. Same transaction shape as prepare_sql.py; only cards, the cards' provenance
rows and the import manifest change. Writes OUT_DIR/candidate.sql and prepared.json.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sql import TABLES, connect, jlit, lit, token  # noqa: E402

PARENT = os.environ.get("PARENT")
PARENT_IMPORT = os.environ.get("PARENT_IMPORT")
TARGET = os.environ.get("TARGET")
IMPORT = os.environ.get("IMPORT")
COVERAGE_QUEUE = os.environ.get("COVERAGE_QUEUE")
FIX_KEY = os.environ.get("FIX_KEY", "ja_recovery_fixes")
FIX_STATE = os.environ.get("FIX_STATE", "candidate_ja_recovery_fixes_inactive")
PROVENANCE = os.environ.get("FIX_PROVENANCE", "ja-recovery-name-link-fix-20261107")
VERIFIED_AT = os.environ.get("FIX_VERIFIED_AT", "2026-11-07T16:00:00Z")
SET_COLUMNS = ("name", "view_title", "set_name", "category", "rarity", "printed_collector_number")
# The columns visual_aliases.identity_sha256 covers.
IDENTITY_COLUMNS = {"name", "set_name", "category"}


def label_groups(labelled):
    """The manifest record of label and relink fixes: cards with the same change, old value and reason share one entry."""
    groups = {}
    for cid, fix, before in labelled:
        entry = {"reason": fix.get("reason"), "source": fix.get("source"), "set": fix.get("set"),
                 "before": {k: before[k] for k in fix.get("set") or {}}, "relink": fix.get("relink")}
        key = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        groups.setdefault(key, {"ids": [], **{k: v for k, v in entry.items() if v}})["ids"].append(cid)
    return list(groups.values())


def row_change(cid, row, fix, urls_in_use, ids_in_use, matched_products=None, alias_ids=frozenset()):
    """The column changes one fix makes to one cards row; raises AssertionError on a fix that must not ship."""
    change = {}
    if fix.get("name_en"):
        change["name"] = fix.get("name_ja") or fix["name_en"]
        change["view_title"] = fix["name_en"]
    if fix.get("set"):
        assert fix.get("reason") and set(fix["set"]) <= set(SET_COLUMNS), cid
        change.update(fix["set"])
    assert cid not in alias_ids or not IDENTITY_COLUMNS & set(change), cid
    assert sum(1 for key in ("clear_link", "url", "relink") if fix.get(key)) <= 1, cid
    if fix.get("clear_link"):
        change.update(cardmarket_url=None, cardmarket_id=None, cardmarket_verified=0,
                      cardmarket_provenance=None, cardmarket_verified_at=None)
    elif fix.get("url"):
        assert not row["cardmarket_url"] and fix["url"] not in urls_in_use, cid
        pid = int(fix["product_id"]) if fix.get("product_id") else None
        assert pid is None or pid not in ids_in_use, cid
        change.update(cardmarket_url=fix["url"], cardmarket_id=pid, cardmarket_verified=1,
                      cardmarket_provenance=PROVENANCE, cardmarket_verified_at=VERIFIED_AT)
        urls_in_use.add(fix["url"])
        if pid:
            ids_in_use.add(pid)
    elif fix.get("relink"):
        link = fix["relink"]
        assert fix.get("reason") and row["cardmarket_url"] == link["old_url"] != link["url"], cid
        assert link["url"] not in urls_in_use and (matched_products or {}).get(link["url"]) == cid, cid
        change.update(cardmarket_url=link["url"], cardmarket_verified=1,
                      cardmarket_provenance=PROVENANCE, cardmarket_verified_at=VERIFIED_AT)
        urls_in_use.add(link["url"])
    if fix.get("display_image_url"):
        assert fix["display_image_url"].startswith("https://") and fix.get("display_reason"), cid
        assert row["has_image"] == 0 and not row["remote_image_url"], cid
        change["remote_image_url"] = fix["display_image_url"]
    return change


def main(fixes_file, role_file, out_dir):
    fixes = json.loads(Path(fixes_file).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    conn = connect(role_file)
    conn.execute("SET statement_timeout = '300s'")
    status, meta, meta_md5 = conn.execute(
        f"SELECT status, metadata, md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id=%s",
        (PARENT_IMPORT,)).fetchone()
    assert status == "validated" and meta["target"]["schema"] == PARENT
    alias_ids = {r[k] for r in (meta.get("visual_image_aliases") or {}).get("records", []) for k in ("alias_id", "owner_id")}
    assert conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (TARGET,)).fetchone()[0] == 0
    counts = {t: conn.execute(f"SELECT count(*) FROM {PARENT}.{t}").fetchone()[0] for t in TABLES}
    cols = meta["digests"]["cards"]["columns"]
    rows = [dict(zip(cols, r)) for r in conn.execute(f'SELECT {",".join(cols)} FROM {PARENT}.cards ORDER BY id COLLATE "C"').fetchall()]
    by_id = {r["id"]: r for r in rows}
    urls_in_use = {r["cardmarket_url"] for r in rows if r["cardmarket_url"]}
    ids_in_use = {r["cardmarket_id"] for r in rows if r["cardmarket_id"]}
    prov_keys = dict(conn.execute(
        f"SELECT metadata->>'id', source_key FROM {PARENT}.reference_metadata WHERE source_key LIKE 'catalogue-completion-source:%%' "
        f"AND metadata->>'id' = ANY(%s)", (list(fixes),)).fetchall())
    relinks = [f["relink"]["url"] for f in fixes.values() if f.get("relink")]
    matched_products = dict(conn.execute(
        f"SELECT url, card_id FROM {PARENT}.cardmarket_products WHERE matched = 1 AND url = ANY(%s)", (relinks,)).fetchall())
    conn.close()

    updates = []
    for cid, fix in sorted(fixes.items()):
        row = by_id[cid]
        change = row_change(cid, row, fix, urls_in_use, ids_in_use, matched_products, alias_ids)
        before = {k: row[k] for k in change}
        row.update(change)
        updates.append((cid, change, fix, before))
    cards_md5 = hashlib.md5("".join(hashlib.md5("|".join(token(r[k]) for k in cols).encode()).hexdigest()
                                    for r in rows).encode()).hexdigest()

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
    for cid, change, fix, before in updates:
        if not change:
            continue
        s.append(f"UPDATE {TARGET}.cards SET " + ", ".join(f"{k}={lit(v)}" for k, v in change.items()) + f" WHERE id={lit(cid)};")
        if cid in prov_keys:
            patch = {"name_fix": {k: fix.get(k) for k in ("name_ja", "name_en", "name_source") if fix.get(k)},
                     "cardmarket_fix": ({"cleared": True, "reason": fix.get("reason"), "old_url": fix.get("old_url")} if fix.get("clear_link")
                                        else {"url": fix.get("url"), "product_name": fix.get("product_name"), "product_id": fix.get("product_id")}
                                        if fix.get("url") else {"relinked": fix["relink"], "reason": fix.get("reason")}
                                        if fix.get("relink") else None),
                     "label_fix": ({"set": fix["set"], "before": {k: before[k] for k in fix["set"]}, "reason": fix.get("reason"),
                                    "source": fix.get("source")} if fix.get("set") else None),
                     "display_only": ({"remote_image_url": fix["display_image_url"], "reason": fix["display_reason"]}
                                      if fix.get("display_image_url") else None),
                     "fix_batch": IMPORT}
            # An empty entry would wipe what an earlier batch recorded under the same key.
            patch = {k: v for k, v in patch.items() if v}
            s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(patch)}::jsonb WHERE source_key={lit(prov_keys[cid])};")
    summary = {"names": sum(1 for f in fixes.values() if f.get("name_en")),
               "links_added": sum(1 for f in fixes.values() if f.get("url") and not f.get("clear_link")),
               "links_cleared": sum(1 for f in fixes.values() if f.get("clear_link")),
               "display_only_images": sum(1 for f in fixes.values() if f.get("display_image_url"))}
    labelled = [(cid, fix, before) for cid, _, fix, before in updates if fix.get("set") or fix.get("relink")]
    if labelled:
        summary.update(labels=sum(1 for _, f, _ in labelled if f.get("set")),
                       links_changed=sum(1 for _, f, _ in labelled if f.get("relink")), rows=label_groups(labelled))
    patch = {"parent_schema": PARENT, "parent_import_id": PARENT_IMPORT, "state": FIX_STATE,
             "activation_allowed": False, "rebuilt_from": {"schema": PARENT, "import_id": PARENT_IMPORT, "metadata_md5": meta_md5},
             FIX_KEY: summary}
    if COVERAGE_QUEUE:
        queue = json.loads(Path(COVERAGE_QUEUE).read_text())
        assert all(q.get("id") and q.get("status") and q.get("reason") for q in queue)
        patch["coverage_queue"] = queue
    s.append(f"UPDATE {TARGET}.import_manifest SET metadata = jsonb_set(jsonb_set(metadata,'{{digests,cards,md5}}',{jlit(cards_md5)}::jsonb),"
             f"'{{target,schema}}',{jlit(TARGET)}::jsonb) || {jlit(patch)}::jsonb, validated_at = now(), import_id = {lit(IMPORT)} "
             f"WHERE import_id={lit(PARENT_IMPORT)};")
    checks = [f"(SELECT count(*) FROM {TARGET}.{t})={counts[t]}" for t in TABLES]
    checks += [f"(SELECT count(*) FROM {TARGET}.import_manifest WHERE import_id={lit(IMPORT)} AND status='validated')=1",
               # no new shared Cardmarket pages (the parent already has a few deliberate ones; a relink may end one)
               f"NOT EXISTS (SELECT cardmarket_url FROM {TARGET}.cards WHERE cardmarket_url IS NOT NULL GROUP BY 1 HAVING count(*)>1"
               f" EXCEPT SELECT cardmarket_url FROM {PARENT}.cards WHERE cardmarket_url IS NOT NULL GROUP BY 1 HAVING count(*)>1)",
               f"(SELECT md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)})={lit(meta_md5)}"]
    s.append("DO $$ BEGIN IF NOT (" + " AND ".join(checks) + ") THEN RAISE EXCEPTION 'fix batch checks failed'; END IF; END $$;")
    s.append("COMMIT;")
    (out / "candidate.sql").write_text("\n".join(s) + "\n")
    report = {"target": TARGET, "import_id": IMPORT, "parent": PARENT, "cards_updated": sum(1 for u in updates if u[1]), "cards_md5": cards_md5,
              "provenance_rows": len(prov_keys), "sql_sha256": hashlib.sha256((out / "candidate.sql").read_bytes()).hexdigest()}
    (out / "prepared.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
