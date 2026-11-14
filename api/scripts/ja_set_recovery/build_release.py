"""Assemble the local release files for the Japanese recovery candidate. No database access.

    python3 build_release.py RUN_DIR PARENT_PACKAGE RELEASE_NAME

PARENT_PACKAGE is the served release's package (for 2026-11-07:
data/catalogue-completion/20261028-neo2-057/release-package-v2), whose vectors/pad and
artwork/ are the exact files behind pokesingle_completion_20261028_neo2057.

Writes RUN_DIR/<RELEASE_NAME>/:
  images/ja_<set>-<number>.jpg       stored references (the JPEGs the vectors came from)
  vectors/pad/                       parent ids/embeddings + scannable new cards, appended
  artwork/                           parent bundle + two regions per scannable new card
  new-cards.json                     card rows to insert (all 11,705 new cards)
  feature-rows.json                  {id,image_path,rarity} for every new card with an image
  release.json                       counts and sha256 of every file above
Scannable/alternative split comes from RUN_DIR/index-decision.json (decide_lookalikes.py).
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

IMAGE_DIR = os.environ.get("JAREC_IMAGE_DIR", "/data/reference-images/ja-20261107-recovery")
LANG = os.environ.get("JAREC_LANGUAGE", "ja")
PROFILES = ("conventional_window", "broad_center_hypothesis")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(run_dir, parent_dir, name):
    run, parent = Path(run_dir).resolve(), Path(parent_dir).resolve()
    out = run / name
    out.mkdir(exist_ok=False)
    cards = [c for c in json.loads((run / "cards.json").read_text()) if not c["problem"]]
    by_id = {c["id"]: c for c in cards}
    decision = json.loads((run / "index-decision.json").read_text())
    scannable = sorted(decision["scannable_ids"], key=lambda c: c.encode())

    # parent files must be the served ones
    pman = json.loads((parent / "vectors/pad/manifest.json").read_text())
    p_ids = np.load(parent / "vectors/pad/embedding_card_ids.npy").astype(str)
    p_pad = np.load(parent / "vectors/pad/embeddings.npy")
    assert sha_file(parent / "vectors/pad/embeddings.npy") == pman["embeddings_sha256"]
    assert sha_file(parent / "vectors/pad/embedding_card_ids.npy") == pman["ids_sha256"]
    assert list(p_ids) == pman["indexed_ids"] and len(p_ids) == pman["indexed_count"]
    aman = json.loads((parent / "artwork/manifest.json").read_text())
    assert sha_file(parent / "artwork/embeddings.npy") == aman["embeddings_sha256"]
    assert sha_file(parent / "artwork/records.json") == aman["records_sha256"]
    assert aman["base_embeddings_sha256"] == pman["embeddings_sha256"]
    assert not set(p_ids) & set(by_id)

    # new vectors (from build_vectors.py) in id order
    n_ids = np.load(run / "vectors/embedding-card-ids.npy").astype(str)
    n_pad = np.load(run / "vectors/pad-embeddings.npy")
    pos = {cid: i for i, cid in enumerate(n_ids)}
    art = np.load(run / "vectors/artwork-delta.npz")["embeddings"]
    art_recs = json.loads((run / "vectors/artwork-delta-records.json").read_text())
    art_by = {(r["card_id"], r["profile"]): (r, art[i]) for i, r in enumerate(art_recs)}

    # images
    img_dir = out / "images"
    img_dir.mkdir()
    image_sha = {}
    for card in cards:
        if card["local_file"]:
            src = run / "reference-images" / (card["id"].replace(":", "_") + ".jpg")
            dst = img_dir / src.name
            shutil.copyfile(src, dst)
            image_sha[card["id"]] = sha_file(dst)

    # pad vectors: parent order, then scannable ids
    ids = list(p_ids) + scannable
    assert len(ids) == len(set(ids))
    pad = np.concatenate([p_pad.astype(np.float32), np.asarray([n_pad[pos[c]] for c in scannable], np.float32).reshape(-1, 384)])
    vdir = out / "vectors/pad"
    vdir.mkdir(parents=True)
    np.save(vdir / "embedding_card_ids.npy", np.asarray(ids, dtype=str))
    np.save(vdir / "embeddings.npy", pad)
    with_image = len(image_sha)
    new_pman = dict(pman)
    new_pman.update(
        indexed_ids=ids, indexed_count=len(ids),
        card_count=pman["card_count"] + len(cards),
        missing_images=pman["missing_images"] + len(cards) - with_image,
        embeddings_sha256=sha_file(vdir / "embeddings.npy"), ids_sha256=sha_file(vdir / "embedding_card_ids.npy"),
        parent_embeddings_sha256=pman["embeddings_sha256"], parent_ids_sha256=pman["ids_sha256"],
        retrieval_segments=list(pman["retrieval_segments"]) + ([len(scannable)] if scannable else []),  # an empty segment is not a valid lineage
        catalogue_version=pman["catalogue_version"] + "-ja-recovery-" + name,
    )
    (vdir / "manifest.json").write_text(json.dumps(new_pman, ensure_ascii=False) + "\n")

    # artwork bundle
    p_art = np.load(parent / "artwork/embeddings.npy")
    p_recs = json.loads((parent / "artwork/records.json").read_text())
    add_recs, add_vecs = [], []
    for cid in scannable:
        card = by_id[cid]
        for profile in PROFILES:
            rec, vec = art_by[(cid, profile)]
            assert rec["reference_sha256"] == image_sha[cid]
            add_recs.append({"card_id": cid, "profile": profile, "language": LANG, "name": card["name"],
                             "set_name": card["set_name"], "collector_number": card["collector_number"],
                             "reference_sha256": image_sha[cid]})
            add_vecs.append(vec)
    adir = out / "artwork"
    adir.mkdir()
    np.save(adir / "embeddings.npy", np.concatenate([p_art.astype(np.float32), np.asarray(add_vecs, np.float32).reshape(-1, 384)]))
    all_recs = p_recs + add_recs
    (adir / "records.json").write_text(json.dumps(all_recs, ensure_ascii=False, separators=(",", ":")))
    new_aman = dict(aman)
    new_aman.update(
        base_embeddings_sha256=new_pman["embeddings_sha256"], base_ids_sha256=new_pman["ids_sha256"],
        embeddings_sha256=sha_file(adir / "embeddings.npy"), records_sha256=sha_file(adir / "records.json"),
        indexed_regions=len(all_recs), indexed_cards=len({r["card_id"] for r in all_recs}),
        parent_manifest_sha256=sha_file(parent / "artwork/manifest.json"),
    )
    (adir / "manifest.json").write_text(json.dumps(new_aman, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    # card rows and feature rows
    rows, feature_rows = [], []
    for card in sorted(cards, key=lambda c: c["id"].encode()):
        path = f"{IMAGE_DIR}/{card['id'].replace(':', '_')}.jpg" if card["id"] in image_sha else None
        rows.append({**card, "image_path": path, "image_sha256_stored": image_sha.get(card["id"]),
                     "treatment": ("scannable" if card["id"] in set(scannable) else
                                   "printing_alternative" if path else "no_image")})
        if path:
            feature_rows.append({"id": card["id"], "image_path": path, "rarity": ""})
    (out / "new-cards.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    (out / "feature-rows.json").write_text(json.dumps(feature_rows, ensure_ascii=False) + "\n")
    (out / "art-added.json").write_text(json.dumps([
        {**r, "source_vector_sha256": hashlib.sha256(np.asarray(v, dtype=">f4").tobytes()).hexdigest()}
        for r, v in zip(add_recs, add_vecs)], ensure_ascii=False) + "\n")

    report = {
        "release": name, "image_dir": IMAGE_DIR, "new_cards": len(cards), "with_image": with_image,
        "scannable": len(scannable), "printing_alternatives": with_image - len(scannable),
        "no_image": len(cards) - with_image, "pad_vectors": len(ids), "artwork_regions": len(all_recs),
        "cards_total": new_pman["card_count"],
        "files": {str(p.relative_to(out)): sha_file(p) for p in sorted(out.rglob("*"))
                  if p.is_file() and not p.is_relative_to(img_dir)},
        "images_bytes": sum(p.stat().st_size for p in img_dir.iterdir()),
    }
    (out / "release.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
