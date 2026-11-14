"""Write the inactive-candidate SQL and local artifacts for a clean-up release: rows and vectors out.

    PARENT=... PARENT_IMPORT=... TARGET=... IMPORT=... \
      python3 prepare_sql_cleanup.py DECISIONS_JSON PARENT_PACKAGE ROLE_JSON OUT_DIR [FEATURE_MANIFEST_SHA256]

Read-only on PlanetScale. PARENT_PACKAGE holds the parent's served vectors/pad and artwork/ files
(checked against the parent's stored manifests). DECISIONS_JSON:

  delete        {card_id: reason}    the card row goes, with its vectors (all modes), artwork rows and
                                     helper; its Cardmarket product rows move to its successor
  successor     {card_id: kept_id}   for a deleted row that has product rows or a helper
  unvector      {card_id: reason}    the row stays (archived: not scannable), its vectors and
                                     artwork rows go
  move_vector   {from_id: to_id}     the from-row's vectors become the to-row's (to has none); the
                                     from-row must be deleted
  relink        {to_id: from_id}     copy the Cardmarket columns of from (a deleted row) onto to

Nothing else changes: names, images, the other vectors and the other tables are copied as they are.
Writes OUT_DIR/vectors/pad (ids, embeddings, manifest), OUT_DIR/artwork (bundle), OUT_DIR/signature-rows.json
(every remaining catalogue row, for the feature manifest), OUT_DIR/feature-deleted.json, and, when
FEATURE_MANIFEST_SHA256 is given, OUT_DIR/sql/candidate.sql and prepared.json. Same transaction shape as
prepare_sql.py: clone the nine tables, change, update the manifests, guard on every count and hash.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_sql import TABLES, agg_md5, connect, jlit, lit, token  # noqa: E402

PARENT = os.environ.get("PARENT")
PARENT_IMPORT = os.environ.get("PARENT_IMPORT")
TARGET = os.environ.get("TARGET")
IMPORT = os.environ.get("IMPORT")
CARD_COLS = ("cardmarket_id", "cardmarket_url", "cardmarket_verified", "cardmarket_provenance",
             "cardmarket_verified_at")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def digest(rows, cols):
    """The loader's table digest: md5 over per-row md5 of the column tokens, rows in key byte order."""
    return hashlib.md5("".join(hashlib.md5("|".join(token(r[k]) for k in cols).encode()).hexdigest()
                               for r in rows).encode()).hexdigest()


def new_segments(segments, removed_positions):
    """Each lineage segment loses the removed rows that fall inside it; an emptied segment is dropped."""
    out, start, removed = [], 0, sorted(removed_positions)
    i = 0
    for count in segments:
        end = start + count
        gone = 0
        while i < len(removed) and removed[i] < end:
            gone += 1
            i += 1
        if count - gone:
            out.append(count - gone)
        start = end
    assert i == len(removed)
    return out


def plan_vectors(ids, decisions):
    """(kept ids in order, kept parent positions, removed positions) after deletes, unvectors and moves."""
    delete, unvector, move = decisions["delete"], decisions["unvector"], decisions["move_vector"]
    kept, positions, removed = [], [], []
    for i, cid in enumerate(ids):
        if cid in move:
            kept.append(move[cid])
            positions.append(i)
        elif cid in delete or cid in unvector:
            removed.append(i)
        else:
            kept.append(cid)
            positions.append(i)
    assert len(kept) == len(set(kept))
    return kept, positions, removed


def check_decisions(decisions, card_ids, vector_ids):
    delete, unvector = decisions["delete"], decisions["unvector"]
    successor, move, relink = decisions["successor"], decisions["move_vector"], decisions["relink"]
    assert not set(delete) & set(unvector)
    assert set(delete) <= card_ids and set(unvector) <= card_ids
    assert set(unvector) <= vector_ids, "an unvectored row must have a vector"
    for old, new in successor.items():
        assert old in delete and new in card_ids and new not in delete and new not in unvector, old
    for old, new in move.items():
        assert old in delete and old in vector_ids and new in card_ids and new not in vector_ids, old
        assert new not in delete and new not in unvector, old
    for to, frm in relink.items():
        assert frm in delete and to in card_ids and to not in delete, to


def main(decisions_path, package, role_file, out_dir, feature_sha=None):
    decisions = json.loads(Path(decisions_path).read_text())
    for key in ("delete", "successor", "unvector", "move_vector", "relink"):
        decisions.setdefault(key, {})
    package, out = Path(package).resolve(), Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    pman = json.loads((package / "vectors/pad/manifest.json").read_text())
    aman = json.loads((package / "artwork/manifest.json").read_text())
    assert sha_file(package / "vectors/pad/embeddings.npy") == pman["embeddings_sha256"]
    assert sha_file(package / "vectors/pad/embedding_card_ids.npy") == pman["ids_sha256"]
    assert sha_file(package / "artwork/embeddings.npy") == aman["embeddings_sha256"]
    assert sha_file(package / "artwork/records.json") == aman["records_sha256"]
    assert aman["base_embeddings_sha256"] == pman["embeddings_sha256"]
    ids = np.load(package / "vectors/pad/embedding_card_ids.npy").astype(str).tolist()
    pad = np.load(package / "vectors/pad/embeddings.npy")
    assert ids == pman["indexed_ids"]

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
    stored = rm["vector-manifest:pad"][0]
    assert stored["embeddings_sha256"] == pman["embeddings_sha256"] and stored["indexed_ids"] == ids
    assert rm["artwork-manifest"][0].get("embeddings_sha256") == aman["embeddings_sha256"]

    cols = meta["digests"]["cards"]["columns"]
    rows = [dict(zip(cols, r)) for r in conn.execute(
        f'SELECT {",".join(cols)} FROM {PARENT}.cards ORDER BY id COLLATE "C"').fetchall()]
    assert digest(rows, cols) == meta["digests"]["cards"]["md5"]
    by_id = {r["id"]: r for r in rows}
    pcols = meta["digests"]["cardmarket_products"]["columns"]
    pkey = meta["digests"]["cardmarket_products"]["keys"][0]
    products = [dict(zip(pcols, r)) for r in conn.execute(
        f'SELECT {",".join(pcols)} FROM {PARENT}.cardmarket_products ORDER BY {pkey} COLLATE "C"').fetchall()]
    assert digest(products, pcols) == meta["digests"]["cardmarket_products"]["md5"]
    vecs = {mode: dict(conn.execute(f"SELECT card_id, source_vector_sha256 FROM {PARENT}.card_embeddings WHERE mode=%s",
                                    (mode,)).fetchall()) for mode in meta["vectors"]}
    for mode, hashes in vecs.items():
        assert agg_md5(hashes) == meta["vectors"][mode]["aggregate_md5"] and len(hashes) == meta["vectors"][mode]["count"]
    art_rows = conn.execute(f"SELECT row_index, card_id, source_vector_sha256 FROM {PARENT}.artwork_embeddings ORDER BY row_index").fetchall()
    assert hashlib.md5("".join(h for _, _, h in art_rows).encode()).hexdigest() == meta["artwork"]["aggregate_md5"]
    helpers = dict(conn.execute(f"SELECT card_id, metadata FROM {PARENT}.cardmarket_url_helpers").fetchall())
    conn.close()

    check_decisions(decisions, set(by_id), set(vecs["pad"]))
    delete, unvector, successor = decisions["delete"], decisions["unvector"], decisions["successor"]
    move, relink = decisions["move_vector"], decisions["relink"]
    gone_vectors = set(delete) | set(unvector)
    for p in products:
        if p["card_id"] in delete:
            assert p["card_id"] in successor, f"product rows of {p['card_id']} need a successor"
    for cid in delete:
        assert cid not in helpers or cid in successor, f"helper of {cid} needs a successor"

    # pad vectors
    kept, positions, removed = plan_vectors(ids, decisions)
    vdir = out / "vectors/pad"
    vdir.mkdir(parents=True, exist_ok=True)
    np.save(vdir / "embedding_card_ids.npy", np.asarray(kept, dtype=str))
    np.save(vdir / "embeddings.npy", np.asarray(pad[positions], dtype=np.float32))
    new_pman = dict(pman)
    new_pman.update(
        indexed_ids=kept, indexed_count=len(kept), card_count=pman["card_count"] - len(delete),
        missing_images=pman["missing_images"] - sum(1 for c in delete if not by_id[c]["image_path"]),
        embeddings_sha256=sha_file(vdir / "embeddings.npy"), ids_sha256=sha_file(vdir / "embedding_card_ids.npy"),
        parent_embeddings_sha256=pman["embeddings_sha256"], parent_ids_sha256=pman["ids_sha256"],
        retrieval_segments=new_segments(pman["retrieval_segments"], removed),
        catalogue_version=pman["catalogue_version"] + "-cleanup-" + IMPORT,
    )
    (vdir / "manifest.json").write_text(json.dumps(new_pman, ensure_ascii=False) + "\n")

    # artwork bundle: the regions of every card that loses its vectors go
    p_art = np.load(package / "artwork/embeddings.npy")
    p_recs = json.loads((package / "artwork/records.json").read_text())
    assert not any(r["card_id"] in move for r in p_recs), "a moved vector's row has artwork regions"
    keep_art = [i for i, r in enumerate(p_recs) if r["card_id"] not in gone_vectors]
    adir = out / "artwork"
    adir.mkdir(exist_ok=True)
    np.save(adir / "embeddings.npy", np.asarray(p_art[keep_art], dtype=np.float32))
    recs = [p_recs[i] for i in keep_art]
    (adir / "records.json").write_text(json.dumps(recs, ensure_ascii=False, separators=(",", ":")))
    new_aman = dict(aman)
    new_aman.update(
        base_embeddings_sha256=new_pman["embeddings_sha256"], base_ids_sha256=new_pman["ids_sha256"],
        embeddings_sha256=sha_file(adir / "embeddings.npy"), records_sha256=sha_file(adir / "records.json"),
        indexed_regions=len(recs), indexed_cards=len({r["card_id"] for r in recs}),
        parent_manifest_sha256=sha_file(package / "artwork/manifest.json"),
    )
    (adir / "manifest.json").write_text(json.dumps(new_aman, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    db_art_gone = [(ri, cid) for ri, cid, _ in art_rows if cid in gone_vectors]
    assert len(db_art_gone) == len(p_recs) - len(recs), "database artwork rows differ from the bundle"
    art_md5 = hashlib.md5("".join(h for _, cid, h in art_rows if cid not in gone_vectors).encode()).hexdigest()

    # card rows after the change
    new_rows = []
    for r in rows:
        if r["id"] in delete:
            continue
        r = dict(r)
        if r["id"] in relink:
            src = by_id[relink[r["id"]]]
            r.update({k: src[k] for k in CARD_COLS})
        new_rows.append(r)
    cards_md5 = digest(new_rows, cols)
    new_products = [dict(p, card_id=successor.get(p["card_id"], p["card_id"])) for p in products]
    products_md5 = digest(new_products, pcols)
    sig = [{"id": r["id"], "image_path": r["image_path"], "rarity": r["rarity"]} for r in new_rows]
    (out / "signature-rows.json").write_text(json.dumps(sig, ensure_ascii=False) + "\n")
    (out / "feature-deleted.json").write_text(json.dumps(sorted(delete)) + "\n")

    new_vecs = {}
    for mode, hashes in vecs.items():
        h = {move.get(c, c): v for c, v in hashes.items() if c not in gone_vectors or c in move}
        new_vecs[mode] = {**meta["vectors"][mode], "count": len(h), "aggregate_md5": agg_md5(h)}
    assert new_vecs["pad"]["count"] == len(kept)
    helper_drop = [c for c in delete if c in helpers and successor.get(c) in helpers]
    helper_move = {c: successor[c] for c in delete if c in helpers and successor.get(c) not in helpers}

    report = {"target": TARGET, "import_id": IMPORT, "parent": PARENT, "parent_metadata_md5": meta_md5,
              "deleted_cards": len(delete), "unvectored_cards": len(unvector), "moved_vectors": len(move),
              "relinked": len(relink), "products_moved": sum(1 for p in products if p["card_id"] in successor),
              "helpers_dropped": len(helper_drop), "helpers_moved": len(helper_move),
              "pad_vectors": f"{len(ids)} -> {len(kept)}", "segments": f"{len(pman['retrieval_segments'])} -> {len(new_pman['retrieval_segments'])}",
              "artwork_regions": f"{len(p_recs)} -> {len(recs)}", "cards": f"{len(rows)} -> {len(new_rows)}",
              "cards_md5": cards_md5, "products_md5": products_md5, "artwork_aggregate_md5": art_md5,
              "vectors": new_vecs, "embeddings_sha256": new_pman["embeddings_sha256"], "ids_sha256": new_pman["ids_sha256"],
              "artwork_embeddings_sha256": new_aman["embeddings_sha256"]}
    if not feature_sha:
        (out / "prepared-artifacts.json").write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps(report, indent=1))
        return

    q = lambda values: ",".join(lit(v) for v in values)  # noqa: E731
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
    for to, frm in relink.items():
        src = by_id[frm]
        s.append(f"UPDATE {TARGET}.cards SET " + ",".join(f"{k}={lit(src[k])}" for k in CARD_COLS)
                 + f" WHERE id={lit(to)};")
    for frm, to in move.items():
        s.append(f"UPDATE {TARGET}.card_embeddings SET card_id={lit(to)} WHERE card_id={lit(frm)};")
    gone = sorted(gone_vectors - set(move))
    for i in range(0, len(gone), 500):
        part = q(gone[i:i + 500])
        s.append(f"DELETE FROM {TARGET}.card_embeddings WHERE card_id IN ({part});")
        s.append(f"DELETE FROM {TARGET}.artwork_embeddings WHERE card_id IN ({part});")
    for old, new in sorted(successor.items()):
        s.append(f"UPDATE {TARGET}.cardmarket_products SET card_id={lit(new)} WHERE card_id={lit(old)};")
    for i in range(0, len(helper_drop), 500):
        s.append(f"DELETE FROM {TARGET}.cardmarket_url_helpers WHERE card_id IN ({q(helper_drop[i:i + 500])});")
    for old, new in sorted(helper_move.items()):
        s.append(f"UPDATE {TARGET}.cardmarket_url_helpers SET card_id={lit(new)}, "
                 f"metadata=jsonb_set(metadata,'{{card_id}}',{jlit(new)}::jsonb) WHERE card_id={lit(old)};")
    dels = sorted(delete)
    for i in range(0, len(dels), 500):
        s.append(f"DELETE FROM {TARGET}.cards WHERE id IN ({q(dels[i:i + 500])});")
    record = {"import_id": IMPORT, "parent_import_id": PARENT_IMPORT, "decisions": decisions,
              "provenance": "catalogue clean-up release, owner approved 2026-11-14 (docs/catalogue-cleanup-20261114.md)"}
    s.append(f"INSERT INTO {TARGET}.reference_metadata(source_key,metadata) VALUES "
             f"({lit('catalogue-cleanup:' + IMPORT)},{jlit(record)}::jsonb);")
    delta = {k: v for k, v in new_pman.items() if stored.get(k) != v}
    s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(delta)}::jsonb "
             f"WHERE source_key='vector-manifest:pad' AND md5(metadata::text)={lit(rm['vector-manifest:pad'][1])};")
    s.append(f"UPDATE {TARGET}.reference_metadata SET metadata = metadata || {jlit(new_aman)}::jsonb "
             f"WHERE source_key='artwork-manifest' AND md5(metadata::text)={lit(rm['artwork-manifest'][1])};")
    new_counts = dict(meta["counts"])
    new_counts.update({t: counts[t] for t in TABLES if t != "import_manifest"})
    new_counts.update(cards=counts["cards"] - len(delete),
                      card_embeddings=counts["card_embeddings"] - sum(
                          1 for h in vecs.values() for c in h if c in gone_vectors and c not in move),
                      artwork_embeddings=counts["artwork_embeddings"] - len(db_art_gone),
                      cardmarket_url_helpers=counts["cardmarket_url_helpers"] - len(helper_drop),
                      reference_metadata=counts["reference_metadata"] + 1)
    patch = {
        "counts": new_counts, "expected_counts": new_counts,
        "parent_schema": PARENT, "parent_import_id": PARENT_IMPORT,
        "reference_feature_manifest_sha256": feature_sha,
        "state": "candidate_catalogue_cleanup_inactive", "activation_allowed": False,
        "rebuilt_from": {"schema": PARENT, "import_id": PARENT_IMPORT, "metadata_md5": meta_md5},
        "artwork": {**meta["artwork"], "cards": new_aman["indexed_cards"], "count": new_aman["indexed_regions"],
                    "aggregate_md5": art_md5, "records_sha256": new_aman["records_sha256"],
                    "embeddings_sha256": new_aman["embeddings_sha256"],
                    "manifest_sha256": sha_file(adir / "manifest.json")},
        "vectors": new_vecs,
        "catalogue_cleanup_20261114": {k: report[k] for k in (
            "deleted_cards", "unvectored_cards", "moved_vectors", "relinked", "products_moved",
            "helpers_dropped", "helpers_moved", "pad_vectors", "artwork_regions", "cards")},
    }
    s.append(f"UPDATE {TARGET}.import_manifest SET metadata = jsonb_set(jsonb_set(jsonb_set(metadata,"
             f"'{{digests,cards,md5}}',{jlit(cards_md5)}::jsonb),'{{digests,cardmarket_products,md5}}',{jlit(products_md5)}::jsonb),"
             f"'{{target,schema}}',{jlit(TARGET)}::jsonb) || {jlit(patch)}::jsonb, "
             f"validated_at = now(), import_id = {lit(IMPORT)} WHERE import_id={lit(PARENT_IMPORT)};")
    checks = [f"(SELECT count(*) FROM {TARGET}.{t})={new_counts[t]}" for t in TABLES if t != "import_manifest"]
    checks += [
        f"(SELECT count(*) FROM {TARGET}.import_manifest WHERE import_id={lit(IMPORT)} AND status='validated')=1",
        f"(SELECT count(*) FROM {TARGET}.card_embeddings WHERE mode='pad')={len(kept)}",
        f"(SELECT count(*) FROM {TARGET}.card_embeddings e LEFT JOIN {TARGET}.cards c ON c.id=e.card_id WHERE c.id IS NULL)=0",
        f"(SELECT count(*) FROM {TARGET}.artwork_embeddings e LEFT JOIN {TARGET}.cards c ON c.id=e.card_id WHERE c.id IS NULL)=0",
        f"(SELECT count(*) FROM {TARGET}.cardmarket_products p WHERE p.card_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {TARGET}.cards c WHERE c.id=p.card_id))="
        f"(SELECT count(*) FROM {PARENT}.cardmarket_products p WHERE p.card_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {PARENT}.cards c WHERE c.id=p.card_id))",
        f"(SELECT jsonb_array_length(metadata->'indexed_ids') FROM {TARGET}.reference_metadata WHERE source_key='vector-manifest:pad' AND metadata->>'embeddings_sha256'={lit(new_pman['embeddings_sha256'])})={len(kept)}",
        f"(SELECT count(*) FROM {TARGET}.reference_metadata WHERE source_key='artwork-manifest' AND (metadata->>'indexed_regions')::int={new_aman['indexed_regions']} AND metadata->>'base_embeddings_sha256'={lit(new_pman['embeddings_sha256'])})=1",
        f"(SELECT md5(metadata::text) FROM {PARENT}.import_manifest WHERE import_id={lit(PARENT_IMPORT)})={lit(meta_md5)}",
    ]
    s.append("DO $$ BEGIN IF NOT (" + " AND ".join(checks) + ") THEN RAISE EXCEPTION 'clean-up checks failed'; END IF; END $$;")
    s.append("COMMIT;")
    (out / "sql").mkdir(exist_ok=True)
    (out / "sql/candidate.sql").write_text("\n".join(s) + "\n")
    report.update(feature_manifest_sha256=feature_sha, counts=new_counts,
                  sql_sha256=sha_file(out / "sql/candidate.sql"), sql_bytes=(out / "sql/candidate.sql").stat().st_size)
    (out / "sql/prepared.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "vectors"}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:6])
