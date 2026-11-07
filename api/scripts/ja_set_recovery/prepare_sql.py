"""Write the inactive-candidate SQL for the Japanese recovery. Read-only on PlanetScale.

    python3 prepare_sql.py RELEASE_DIR ROLE_JSON FEATURE_MANIFEST_SHA256

ROLE_JSON is `pscale role create ... -f json` output (read access is enough); the URL is
never printed. RELEASE_DIR comes from build_release.py. Pattern follows the neo2-057
release (data/catalogue-completion/20261028-neo2-057/release-package-v2/prepare-inactive-release.sql):
one transaction that checks the parent CAS, clones the nine tables into a new schema,
copies read grants, appends the new cards, pad vectors, artwork regions and provenance,
updates the two manifests and the import manifest, renames the import, and ends with a
guard that raises on any count or vector-hash mismatch. The parent schema is not changed.

Writes RELEASE_DIR/sql/candidate.sql, RELEASE_DIR/signature-rows.json (all catalogue
rows for the feature-store signature) and RELEASE_DIR/sql/prepared.json.
"""
import hashlib
import json
import sys
from pathlib import Path

import certifi
import numpy as np
import psycopg

PARENT = "pokesingle_completion_20261028_neo2057"
PARENT_IMPORT = "PS-CATALOGUE-EN-JA-NEO2057-20261028"
TARGET = "pokesingle_completion_20261107_jarec"
IMPORT = "PS-CATALOGUE-EN-JA-REC-20261107"
TABLES = ["cards", "cardmarket_products", "card_embeddings", "reference_metadata", "import_manifest",
          "artwork_embeddings", "cardmarket_review", "cardmarket_url_helpers", "source_records"]
PROVENANCE = "ja-recovery-listing-20261106"
VERIFIED_AT = "2026-11-06T23:59:00Z"
RIGHTS = "Owner approved the Japanese recovery image sources that pass the catalogue gate (chat, 2026-11-07)."
NAME_DECISION = "English checklist name; no official Japanese name available for these rows (owner decision 3, 2026-11-06)."
BATCH = 200


def lit(value):
    return "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"


def jlit(value):
    return lit(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def vhash(vector):
    return hashlib.sha256(np.asarray(vector, dtype=">f4").tobytes()).hexdigest()


def vlit(vector):
    return lit("[" + ",".join(repr(float(x)) for x in np.asarray(vector, dtype=np.float32)) + "]") + "::public.vector"


def token(value):
    return "N" if value is None else "V" + str(value).encode().hex()


def connect(role_file):
    # same connection form as the 2026-10-17 prepare_jasets.py
    role = json.loads(Path(role_file).read_text())
    return psycopg.connect(role["database_url"], port=6432, sslmode="verify-full",
                           sslrootcert=certifi.where(), prepare_threshold=None)


def main(release_dir, role_file, feature_sha):
    rel = Path(release_dir).resolve()
    cards = json.loads((rel / "new-cards.json").read_text())
    pman = json.loads((rel / "vectors/pad/manifest.json").read_text())
    aman = json.loads((rel / "artwork/manifest.json").read_text())
    art_added = json.loads((rel / "art-added.json").read_text())
    ids = np.load(rel / "vectors/pad/embedding_card_ids.npy").astype(str)
    pad = np.load(rel / "vectors/pad/embeddings.npy")
    scannable = [c["id"] for c in cards if c["treatment"] == "scannable"]
    n_parent = len(ids) - len(scannable)
    assert list(ids[n_parent:]) == scannable
    art_vecs = np.load(rel / "artwork/embeddings.npy")[-len(art_added):]
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

    # cards digest = parent rows + new rows, ordered like the loader (id COLLATE "C")
    cols = meta["digests"]["cards"]["columns"]
    parent_rows = [dict(zip(cols, r)) for r in conn.execute(
        f'SELECT {",".join(cols)} FROM {PARENT}.cards ORDER BY id COLLATE "C"').fetchall()]
    assert not {r["id"] for r in parent_rows} & {c["id"] for c in cards}
    new_rows = []
    for c in cards:
        linked = c["cardmarket_url"] is not None
        new_rows.append({
            "id": c["id"], "provider_id": c["provider_id"], "name": c["name"], "set_id": c["set_id"],
            "set_name": c["set_name"], "collector_number": c["collector_number"], "language": "ja",
            "category": None, "rarity": None, "illustrator": None, "variants_json": "{}",
            "image_path": c["image_path"], "has_image": 1 if c["image_path"] else 0,
            "cardmarket_id": int(c["cardmarket_id"]) if c["cardmarket_id"] else None,
            "cardmarket_url": c["cardmarket_url"], "cardmarket_verified": 1 if linked else 0,
            "cardmarket_provenance": PROVENANCE if linked else None,
            "cardmarket_verified_at": VERIFIED_AT if linked else None,
            "remote_image_url": None, "printed_collector_number": None, "view_title": c["name"],
        })
    assert set(cols) <= set(new_rows[0])
    all_rows = sorted(parent_rows + new_rows, key=lambda r: r["id"].encode())
    cards_md5 = hashlib.md5("".join(hashlib.md5("|".join(token(r[k]) for k in cols).encode()).hexdigest()
                                    for r in all_rows).encode()).hexdigest()

    # vector aggregate (loader: md5 over sha256 hex in id byte order)
    vh = dict(conn.execute(f"SELECT card_id, source_vector_sha256 FROM {PARENT}.card_embeddings WHERE mode='pad'").fetchall())
    assert len(vh) == n_parent
    agg = lambda d: hashlib.md5("".join(d[k] for k in sorted(d, key=lambda x: x.encode())).encode()).hexdigest()
    assert agg(vh) == meta["vectors"]["pad"]["aggregate_md5"]
    for i, cid in enumerate(scannable):
        vh[cid] = vhash(pad[n_parent + i])
    # artwork aggregate (row_index order)
    art_rows = conn.execute(f"SELECT row_index, source_vector_sha256 FROM {PARENT}.artwork_embeddings ORDER BY row_index").fetchall()
    assert hashlib.md5("".join(h for _, h in art_rows).encode()).hexdigest() == meta["artwork"]["aggregate_md5"]
    start_row = art_rows[-1][0] + 1
    art_md5 = hashlib.md5(("".join(h for _, h in art_rows) + "".join(r["source_vector_sha256"] for r in art_added)).encode()).hexdigest()

    # signature rows for the feature store (all catalogue rows)
    sig = [{"id": i, "image_path": p, "rarity": rr} for i, p, rr in conn.execute(f"SELECT id, image_path, rarity FROM {PARENT}.cards").fetchall()]
    sig += [{"id": r["id"], "image_path": r["image_path"], "rarity": None} for r in new_rows]
    (rel / "signature-rows.json").write_text(json.dumps(sig, ensure_ascii=False) + "\n")
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
    card_cols = list(new_rows[0])
    for i in range(0, len(new_rows), BATCH):
        values = ",".join("(" + ",".join(lit(r[k]) for k in card_cols) + ")" for r in new_rows[i:i + BATCH])
        s.append(f"INSERT INTO {TARGET}.cards({','.join(card_cols)}) VALUES {values};")
    for i in range(0, len(scannable), BATCH):
        values = ",".join(f"({lit(cid)},'pad',{lit(snapshot)},{vlit(pad[n_parent + i + k])},{lit(vh[cid])})"
                          for k, cid in enumerate(scannable[i:i + BATCH]))
        s.append(f"INSERT INTO {TARGET}.card_embeddings(card_id,mode,snapshot_id,embedding,source_vector_sha256) VALUES {values};")
    for i in range(0, len(art_added), BATCH):
        values = []
        for k, rec in enumerate(art_added[i:i + BATCH]):
            meta_rec = {key: rec[key] for key in ("card_id", "profile", "language", "name", "set_name", "collector_number", "reference_sha256")}
            values.append(f"({lit(rec['card_id'])},{lit(rec['profile'])},{start_row + i + k},{vlit(art_vecs[i + k])},"
                          f"{lit(rec['source_vector_sha256'])},{jlit(meta_rec)}::jsonb)")
        s.append(f"INSERT INTO {TARGET}.artwork_embeddings(card_id,profile,row_index,embedding,source_vector_sha256,metadata) VALUES {','.join(values)};")
    by_id = {c["id"]: c for c in cards}
    prov = [{"source_key": f"catalogue-completion-source:{IMPORT}:{c['id']}", "metadata": {
        "id": c["id"], "name": c["name"], "language": "ja", "set_id": c["set_id"], "set_name": c["set_name"],
        "collector_number": c["collector_number"], "printed_number": c["printed_number"], "group_id": c["group_id"],
        "image_path": c["image_path"], "sha256": c["image_sha256_stored"], "source_file_sha256": c["image_sha256"],
        "source_kind": c["image_source"], "source_use_permission": RIGHTS if c["image_path"] else None,
        "name_decision": NAME_DECISION, "treatment": c["treatment"],
        "cardmarket_status": c["cardmarket_status"], "status": "candidate_staging_scan_pending"}} for c in cards]
    for i in range(0, len(prov), 1000):
        s.append(f"INSERT INTO {TARGET}.reference_metadata(source_key,metadata) SELECT x.source_key,x.metadata FROM "
                 f"jsonb_to_recordset({jlit(prov[i:i + 1000])}::jsonb) AS x(source_key text, metadata jsonb);")
    delta = {k: v for k, v in pman.items() if k != "indexed_ids" and rm["vector-manifest:pad"][0].get(k) != v}
    s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(delta)}::jsonb || "
             f"jsonb_build_object('indexed_ids', (metadata->'indexed_ids') || {jlit(scannable)}::jsonb) "
             f"WHERE source_key='vector-manifest:pad' AND md5(metadata::text)={lit(rm['vector-manifest:pad'][1])};")
    s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(aman)}::jsonb "
             f"WHERE source_key='artwork-manifest' AND md5(metadata::text)={lit(rm['artwork-manifest'][1])};")
    new_counts = dict(meta["counts"])
    for t, extra in (("cards", len(new_rows)), ("card_embeddings", len(scannable)),
                     ("artwork_embeddings", len(art_added)), ("reference_metadata", len(prov))):
        new_counts[t] = counts[t] + extra
    alternatives = [{"card_id": c["id"], "image_path": c["image_path"], "source_sha256": c["image_sha256_stored"],
                     "reason": "Pad cosine >= 0.95 to another Japanese printing (decide_lookalikes.py). Printing alternative: image and features, no vectors."}
                    for c in cards if c["treatment"] == "printing_alternative"]
    patch = {
        "counts": new_counts, "expected_counts": new_counts,
        "parent_schema": PARENT, "parent_import_id": PARENT_IMPORT,
        "reference_feature_manifest_sha256": feature_sha,
        "state": "candidate_ja_recovery_inactive", "activation_allowed": False,
        "rebuilt_from": {"schema": PARENT, "import_id": PARENT_IMPORT, "metadata_md5": meta_md5},
        "artwork": {"cards": aman["indexed_cards"], "count": aman["indexed_regions"], "aggregate_md5": art_md5,
                    "records_sha256": aman["records_sha256"], "embeddings_sha256": aman["embeddings_sha256"],
                    "manifest_sha256": hashlib.sha256((rel / "artwork/manifest.json").read_bytes()).hexdigest()},
        "feature_only_printing_alternatives": list(meta.get("feature_only_printing_alternatives") or []) + alternatives,
        "ja_recovery": {"run": "data/catalogue-gaps/ja-set-recovery-20261029-v3", "cards": len(new_rows),
                        "with_image": sum(1 for r in new_rows if r["has_image"]), "scannable": len(scannable),
                        "printing_alternatives": len(alternatives),
                        "cardmarket_linked": sum(1 for r in new_rows if r["cardmarket_url"]),
                        "cardmarket_ids": sum(1 for r in new_rows if r["cardmarket_id"]),
                        "names": NAME_DECISION, "image_rights": RIGHTS, "lookalike_rule": "pad cosine >= 0.95"},
    }
    vectors_pad = {**meta["vectors"]["pad"], "count": len(ids), "aggregate_md5": agg(vh)}
    s.append(f"UPDATE {TARGET}.import_manifest SET metadata = jsonb_set(jsonb_set(jsonb_set(metadata,'{{digests,cards,md5}}',{jlit(cards_md5)}::jsonb),"
             f"'{{vectors,pad}}',{jlit(vectors_pad)}::jsonb),'{{target,schema}}',{jlit(TARGET)}::jsonb) || {jlit(patch)}::jsonb, "
             f"validated_at = now(), import_id = {lit(IMPORT)} WHERE import_id={lit(PARENT_IMPORT)};")
    checks = [f"(SELECT count(*) FROM {TARGET}.{t})={new_counts[t] if t in new_counts else counts[t]}" for t in TABLES if t != "import_manifest"]
    checks += [
        f"(SELECT count(*) FROM {TARGET}.import_manifest WHERE import_id={lit(IMPORT)} AND status='validated')=1",
        f"(SELECT count(*) FROM {TARGET}.card_embeddings WHERE mode='pad' AND encode(sha256(substring(public.vector_send(embedding) from 5)),'hex')=source_vector_sha256)={len(ids)}",
        f"(SELECT count(*) FROM {TARGET}.artwork_embeddings WHERE row_index>={start_row} AND encode(sha256(substring(public.vector_send(embedding) from 5)),'hex')=source_vector_sha256)={len(art_added)}",
        f"(SELECT jsonb_array_length(metadata->'indexed_ids') FROM {TARGET}.reference_metadata WHERE source_key='vector-manifest:pad' AND metadata->>'embeddings_sha256'={lit(pman['embeddings_sha256'])})={len(ids)}",
        f"(SELECT count(*) FROM {TARGET}.reference_metadata WHERE source_key='artwork-manifest' AND (metadata->>'indexed_regions')::int={aman['indexed_regions']} AND metadata->>'base_embeddings_sha256'={lit(pman['embeddings_sha256'])})=1",
        f"(SELECT md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)})={lit(meta_md5)}",
    ]
    s.append("DO $$ BEGIN IF NOT (" + " AND ".join(checks) + ") THEN RAISE EXCEPTION 'ja recovery checks failed'; END IF; END $$;")
    s.append("COMMIT;")
    (rel / "sql").mkdir(exist_ok=True)
    (rel / "sql/candidate.sql").write_text("\n".join(s) + "\n")
    report = {"target": TARGET, "import_id": IMPORT, "parent": PARENT, "parent_metadata_md5": meta_md5,
              "cards_total": len(all_rows), "new_cards": len(new_rows), "pad_vectors": len(ids),
              "new_artwork_rows": len(art_added), "artwork_start_row": start_row, "cards_md5": cards_md5,
              "vector_aggregate_md5": vectors_pad["aggregate_md5"], "artwork_aggregate_md5": art_md5,
              "feature_manifest_sha256": feature_sha, "counts": new_counts,
              "sql_sha256": hashlib.sha256((rel / "sql/candidate.sql").read_bytes()).hexdigest(),
              "sql_bytes": (rel / "sql/candidate.sql").stat().st_size}
    (rel / "sql/prepared.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
