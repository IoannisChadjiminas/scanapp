"""Write the inactive-candidate SQL for an image batch on top of the served recovery release.

    PARENT=... PARENT_IMPORT=... TARGET=... IMPORT=... \
      python3 prepare_sql_images.py BATCH_DIR ROLE_JSON FEATURE_MANIFEST_SHA256

Read-only on PlanetScale. BATCH_DIR comes from build_image_batch.py. Same transaction shape as
prepare_sql.py: parent CAS, clone the nine tables, copy read grants, then for the batch cards
(already in the catalogue without an image) set image_path/has_image, the official Japanese
name (English kept in view_title), append pad vectors and artwork regions for the scannable
ones, update both manifests, the cards' provenance rows and the import manifest, rename the
import, and end with a guard. Writes BATCH_DIR/sql/candidate.sql and sql/prepared.json.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sql import TABLES, agg_md5, connect, jlit, lit, token, vhash, vlit  # noqa: E402

PARENT = os.environ["PARENT"]
PARENT_IMPORT = os.environ["PARENT_IMPORT"]
TARGET = os.environ["TARGET"]
IMPORT = os.environ["IMPORT"]
# Provenance of the batch's images. The default is the official-site batch (JAREC3). JAREC4's
# TCG Collector images were recorded with that default by mistake; FIX_SOURCE_BATCH names an
# earlier batch whose rows get SOURCE_KIND / SOURCE_PERMISSION too.
SOURCE_KIND = os.environ.get("SOURCE_KIND", "official_pokemon_card_site")
SOURCE_PERMISSION = os.environ.get("SOURCE_PERMISSION", "pokemon-card.com is an owner-approved Japanese image source.")
FIX_SOURCE_BATCH = os.environ.get("FIX_SOURCE_BATCH")


def main(batch_dir, role_file, feature_sha):
    rel = Path(batch_dir).resolve()
    updates = json.loads((rel / "updates.json").read_text())
    pman = json.loads((rel / "vectors/pad/manifest.json").read_text())
    aman = json.loads((rel / "artwork/manifest.json").read_text())
    art_added = json.loads((rel / "art-added.json").read_text())
    ids = np.load(rel / "vectors/pad/embedding_card_ids.npy").astype(str)
    pad = np.load(rel / "vectors/pad/embeddings.npy")
    scannable = [u["id"] for u in updates if u["treatment"] == "scannable"]
    n_parent = len(ids) - len(scannable)
    assert sorted(ids[n_parent:].tolist()) == sorted(scannable)
    art_vecs = np.load(rel / "artwork/embeddings.npy")[len(np.load(rel / "artwork/embeddings.npy")) - len(art_added):]
    for rec, vec in zip(art_added, art_vecs):
        assert vhash(vec) == rec["source_vector_sha256"]

    conn = connect(role_file)
    conn.execute("SET statement_timeout = '300s'")
    status, meta, meta_md5 = conn.execute(
        f"SELECT status, metadata, md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id=%s",
        (PARENT_IMPORT,)).fetchone()
    assert status == "validated" and meta["target"]["schema"] == PARENT
    assert conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (TARGET,)).fetchone()[0] == 0
    counts = {t: conn.execute(f"SELECT count(*) FROM {PARENT}.{t}").fetchone()[0] for t in TABLES}
    rm = {key: conn.execute(f"SELECT metadata, md5(metadata::text) FROM {PARENT}.reference_metadata WHERE source_key=%s",
                            (key,)).fetchone() for key in ("vector-manifest:pad", "artwork-manifest")}
    assert rm["vector-manifest:pad"][0]["embeddings_sha256"] == pman["parent_embeddings_sha256"]
    assert rm["vector-manifest:pad"][0]["indexed_ids"] == list(ids[:n_parent])

    cols = meta["digests"]["cards"]["columns"]
    rows = [dict(zip(cols, r)) for r in conn.execute(f'SELECT {",".join(cols)} FROM {PARENT}.cards ORDER BY id COLLATE "C"').fetchall()]
    by_id = {r["id"]: r for r in rows}
    for u in updates:
        row = by_id[u["id"]]
        assert row["has_image"] == 0 and not row["image_path"], u["id"]
        row.update(image_path=u["image_path"], has_image=1, name=u["name_ja"], view_title=u["name_en"])
    cards_md5 = hashlib.md5("".join(hashlib.md5("|".join(token(r[k]) for k in cols).encode()).hexdigest()
                                    for r in rows).encode()).hexdigest()
    vh = dict(conn.execute(f"SELECT card_id, source_vector_sha256 FROM {PARENT}.card_embeddings WHERE mode='pad'").fetchall())
    assert len(vh) == n_parent and agg_md5(vh) == meta["vectors"]["pad"]["aggregate_md5"]
    pos = {cid: i for i, cid in enumerate(ids)}
    for cid in scannable:
        vh[cid] = vhash(pad[pos[cid]])
    art_rows = conn.execute(f"SELECT row_index, source_vector_sha256 FROM {PARENT}.artwork_embeddings ORDER BY row_index").fetchall()
    assert hashlib.md5("".join(h for _, h in art_rows).encode()).hexdigest() == meta["artwork"]["aggregate_md5"]
    start_row = art_rows[-1][0] + 1
    art_md5 = hashlib.md5(("".join(h for _, h in art_rows) + "".join(r["source_vector_sha256"] for r in art_added)).encode()).hexdigest()
    prov_keys = dict(conn.execute(
        f"SELECT metadata->>'id', source_key FROM {PARENT}.reference_metadata WHERE source_key LIKE 'catalogue-completion-source:%%' "
        f"AND metadata->>'id' = ANY(%s)", ([u["id"] for u in updates],)).fetchall())
    snapshot = meta["vectors"]["pad"]["snapshot"]
    conn.close()

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
    for u in updates:
        s.append(f"UPDATE {TARGET}.cards SET image_path={lit(u['image_path'])}, has_image=1, name={lit(u['name_ja'])}, "
                 f"view_title={lit(u['name_en'])} WHERE id={lit(u['id'])} AND has_image=0;")
    if scannable:
        s.append(f"INSERT INTO {TARGET}.card_embeddings(card_id,mode,snapshot_id,embedding,source_vector_sha256) VALUES "
                 + ",".join(f"({lit(c)},'pad',{lit(snapshot)},{vlit(pad[pos[c]])},{lit(vh[c])})" for c in scannable) + ";")
        s.append(f"INSERT INTO {TARGET}.artwork_embeddings(card_id,profile,row_index,embedding,source_vector_sha256,metadata) VALUES "
                 + ",".join(f"({lit(r['card_id'])},{lit(r['profile'])},{start_row + i},{vlit(art_vecs[i])},{lit(r['source_vector_sha256'])},"
                            f"{jlit({k: r[k] for k in ('card_id','profile','language','name','set_name','collector_number','reference_sha256')})}::jsonb)"
                            for i, r in enumerate(art_added)) + ";")
    for u in updates:
        patch = {"image_path": u["image_path"], "sha256": u["image_sha256"], "source_kind": SOURCE_KIND,
                 "source": u["source"], "name_official_ja": u["name_ja"], "treatment": u["treatment"],
                 "treatment_reason": u["reason"], "source_use_permission": SOURCE_PERMISSION,
                 "image_batch": IMPORT}
        s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(patch)}::jsonb WHERE source_key={lit(prov_keys[u['id']])};")
    if FIX_SOURCE_BATCH:
        fix = {"source_kind": SOURCE_KIND, "source_use_permission": SOURCE_PERMISSION, "source_kind_corrected_in": IMPORT}
        s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(fix)}::jsonb "
                 f"WHERE source_key LIKE 'catalogue-completion-source:%' AND metadata->>'image_batch' = {lit(FIX_SOURCE_BATCH)};")
    delta = {k: v for k, v in pman.items() if k != "indexed_ids" and rm["vector-manifest:pad"][0].get(k) != v}
    s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(delta)}::jsonb || "
             f"jsonb_build_object('indexed_ids', (metadata->'indexed_ids') || {jlit(scannable)}::jsonb) "
             f"WHERE source_key='vector-manifest:pad' AND md5(metadata::text)={lit(rm['vector-manifest:pad'][1])};")
    s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(aman)}::jsonb "
             f"WHERE source_key='artwork-manifest' AND md5(metadata::text)={lit(rm['artwork-manifest'][1])};")
    new_counts = dict(meta["counts"])
    new_counts["card_embeddings"] = counts["card_embeddings"] + len(scannable)
    new_counts["artwork_embeddings"] = counts["artwork_embeddings"] + len(art_added)
    alternatives = [{"card_id": u["id"], "image_path": u["image_path"], "source_sha256": u["image_sha256"], "reason": u["reason"]}
                    for u in updates if u["treatment"] != "scannable"]
    patch = {"counts": new_counts, "expected_counts": new_counts, "parent_schema": PARENT, "parent_import_id": PARENT_IMPORT,
             "reference_feature_manifest_sha256": feature_sha, "state": "candidate_ja_recovery_images_inactive",
             "activation_allowed": False, "rebuilt_from": {"schema": PARENT, "import_id": PARENT_IMPORT, "metadata_md5": meta_md5},
             "artwork": {"cards": aman["indexed_cards"], "count": aman["indexed_regions"], "aggregate_md5": art_md5,
                         "records_sha256": aman["records_sha256"], "embeddings_sha256": aman["embeddings_sha256"],
                         "manifest_sha256": hashlib.sha256((rel / "artwork/manifest.json").read_bytes()).hexdigest()},
             "feature_only_printing_alternatives": list(meta.get("feature_only_printing_alternatives") or []) + alternatives,
             "ja_recovery_images": {"cards": len(updates), "scannable": len(scannable), "printing_alternatives": len(alternatives),
                                    "source": SOURCE_KIND, "batch": rel.name}}
    vectors_pad = {**meta["vectors"]["pad"], "count": len(ids), "aggregate_md5": agg_md5(vh)}
    s.append(f"UPDATE {TARGET}.import_manifest SET metadata = jsonb_set(jsonb_set(jsonb_set(metadata,'{{digests,cards,md5}}',{jlit(cards_md5)}::jsonb),"
             f"'{{vectors,pad}}',{jlit(vectors_pad)}::jsonb),'{{target,schema}}',{jlit(TARGET)}::jsonb) || {jlit(patch)}::jsonb, "
             f"validated_at = now(), import_id = {lit(IMPORT)} WHERE import_id={lit(PARENT_IMPORT)};")
    checks = [f"(SELECT count(*) FROM {TARGET}.{t})={new_counts.get(t, counts[t])}" for t in TABLES if t != "import_manifest"]
    checks += [
        f"(SELECT count(*) FROM {TARGET}.cards WHERE id IN ({','.join(lit(u['id']) for u in updates)}) AND has_image=1)={len(updates)}",
        f"(SELECT count(*) FROM {TARGET}.import_manifest WHERE import_id={lit(IMPORT)} AND status='validated')=1",
        f"(SELECT count(*) FROM {TARGET}.card_embeddings WHERE mode='pad' AND encode(sha256(substring(public.vector_send(embedding) from 5)),'hex')=source_vector_sha256)={len(ids)}",
        f"(SELECT jsonb_array_length(metadata->'indexed_ids') FROM {TARGET}.reference_metadata WHERE source_key='vector-manifest:pad' AND metadata->>'embeddings_sha256'={lit(pman['embeddings_sha256'])})={len(ids)}",
        f"(SELECT count(*) FROM {TARGET}.reference_metadata WHERE source_key='artwork-manifest' AND (metadata->>'indexed_regions')::int={aman['indexed_regions']})=1",
        f"(SELECT md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)})={lit(meta_md5)}",
    ]
    s.append("DO $$ BEGIN IF NOT (" + " AND ".join(checks) + ") THEN RAISE EXCEPTION 'image batch checks failed'; END IF; END $$;")
    s.append("COMMIT;")
    (rel / "sql").mkdir(exist_ok=True)
    (rel / "sql/candidate.sql").write_text("\n".join(s) + "\n")
    report = {"target": TARGET, "import_id": IMPORT, "parent": PARENT, "parent_metadata_md5": meta_md5, "updated_cards": len(updates),
              "pad_vectors": len(ids), "new_artwork_rows": len(art_added), "cards_md5": cards_md5,
              "feature_manifest_sha256": feature_sha, "provenance_rows": len(prov_keys),
              "sql_sha256": hashlib.sha256((rel / "sql/candidate.sql").read_bytes()).hexdigest()}
    (rel / "sql/prepared.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
