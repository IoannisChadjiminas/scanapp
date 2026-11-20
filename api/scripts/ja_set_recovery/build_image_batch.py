"""Build the local files for an image batch on top of the served recovery release. No DB access.

    python3 build_image_batch.py RUN_DIR PARENT_RELEASE_DIR FILL_JSONL MODEL_ONNX NAME IMAGE_DIR_NAME

For cards that already exist in the catalogue without an image (from fill_official_images.py):
store each image as a full-quality JPEG (quality 95, as the earlier waves), take pad, square and
artwork vectors from that JPEG, and apply the same rules as the kept release (JAREC2):

- vectors only for cards in the modern eras (Mega Evolution, Scarlet & Violet, Sword & Shield,
  Sun & Moon); others become printing alternatives (image + features, no vectors);
- a modern card whose pad cosine to an indexed Japanese card, or to another new card in this
  batch, is >= 0.95 is also a printing alternative (earliest batch card keeps vectors).

PARENT_RELEASE_DIR holds the served vectors/pad and artwork (from build_release.py).
Writes RUN_DIR/<NAME>/: images/, vectors/pad/, artwork/, updates.json, feature-rows.json,
art-added.json, release.json.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

API = Path(__file__).resolve().parents[2]
REPO = API.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(REPO))
from app.recognition.artwork import PROFILES, crop_profile  # noqa: E402
from app.recognition.embed import DinoEmbedder  # noqa: E402
from catalogue.bootstrap.checks import BLUR_LIMIT, MIN_SIDE, load_facts  # noqa: E402

MODERN = {"Mega Evolution Era", "Scarlet & Violet Era", "Sword & Shield Era", "Sun & Moon Era"}
T = 0.95
LANG = os.environ.get("JAREC_LANGUAGE", "ja")  # "en": English rows; twins are looked for within that language


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vh(vector):
    return hashlib.sha256(np.asarray(vector, dtype=">f4").tobytes()).hexdigest()


def main(run_dir, parent_dir, fill_file, model_path, name, image_dir_name):
    run, parent = Path(run_dir).resolve(), Path(parent_dir).resolve()
    out = run / name
    out.mkdir(exist_ok=False)
    registry = {g["group_id"]: g for g in json.loads((run / "set-registry.json").read_text())}
    fills = [json.loads(l) for l in Path(fill_file).open()]
    image_root = f"/data/reference-images/{image_dir_name}"
    model = DinoEmbedder(model_path, 4, 1)

    img_dir = out / "images"
    img_dir.mkdir()
    batch = []
    for fill in sorted(fills, key=lambda f: f["id"].encode()):
        src = REPO / fill["file"]
        dst = img_dir / (fill["id"].replace(":", "_") + ".jpg")
        if src.suffix.lower() in (".jpg", ".jpeg"):
            shutil.copyfile(src, dst)
        else:
            with Image.open(src) as im:
                im.convert("RGB").save(dst, "JPEG", quality=95)
        facts = load_facts(dst)
        assert min(facts.width, facts.height) >= MIN_SIDE and facts.blur is not None and facts.blur >= BLUR_LIMIT, fill["id"]
        with Image.open(dst) as im:
            rgb = im.convert("RGB")
            pad = model.embed(rgb, "pad").astype(np.float32)
            art = {p: model.embed(crop_profile(rgb, p), "pad").astype(np.float32) for p in PROFILES}
        batch.append({"fill": fill, "file": dst, "sha": sha_file(dst), "pad": pad, "art": art,
                      "era": registry[fill["group_id"]]["era"], "line": registry[fill["group_id"]]["line"]})

    p_ids = np.load(parent / "vectors/pad/embedding_card_ids.npy").astype(str)
    p_pad = np.load(parent / "vectors/pad/embeddings.npy")
    pman = json.loads((parent / "vectors/pad/manifest.json").read_text())
    assert sha_file(parent / "vectors/pad/embeddings.npy") == pman["embeddings_sha256"]
    ja = np.char.startswith(p_ids, LANG + ":")
    ja_ids, ja_pad = p_ids[ja], p_pad[ja]
    assert not {b["fill"]["id"] for b in batch} & set(p_ids)

    # earliest printing first (larger registry line = older), then id
    order = sorted(batch, key=lambda b: (-b["line"], b["fill"]["id"]))
    kept = []
    for b in order:
        cid = b["fill"]["id"]
        sims = ja_pad @ b["pad"]
        j = int(sims.argmax())
        b["nearest_indexed"] = [str(ja_ids[j]), round(float(sims[j]), 4)]
        twin_new = next((k["fill"]["id"] for k in kept if float(k["pad"] @ b["pad"]) >= T), None)
        if b["era"] not in MODERN:
            b["treatment"], b["reason"] = "printing_alternative", f"older era ({b['era']}); vectors held like JAREC2"
        elif sims[j] >= T:
            b["treatment"], b["reason"] = "printing_alternative", f"pad cosine {sims[j]:.4f} to indexed {ja_ids[j]}"
        elif twin_new:
            b["treatment"], b["reason"] = "printing_alternative", f"pad cosine >= {T} to {twin_new} in this batch"
        else:
            b["treatment"], b["reason"] = "scannable", "modern era, no twin at 0.95"
            kept.append(b)
    scannable = sorted((b for b in batch if b["treatment"] == "scannable"), key=lambda b: b["fill"]["id"].encode())

    vdir = out / "vectors/pad"
    vdir.mkdir(parents=True)
    ids = list(p_ids) + [b["fill"]["id"] for b in scannable]
    pad = np.concatenate([p_pad.astype(np.float32), np.asarray([b["pad"] for b in scannable], np.float32).reshape(-1, 384)])
    np.save(vdir / "embedding_card_ids.npy", np.asarray(ids, dtype=str))
    np.save(vdir / "embeddings.npy", pad)
    new_pman = dict(pman)
    new_pman.update(indexed_ids=ids, indexed_count=len(ids), missing_images=pman["missing_images"] - len(batch),
                    embeddings_sha256=sha_file(vdir / "embeddings.npy"), ids_sha256=sha_file(vdir / "embedding_card_ids.npy"),
                    parent_embeddings_sha256=pman["embeddings_sha256"], parent_ids_sha256=pman["ids_sha256"],
                    retrieval_segments=list(pman["retrieval_segments"]) + ([len(scannable)] if scannable else []),
                    catalogue_version=pman["catalogue_version"] + "-" + name)
    (vdir / "manifest.json").write_text(json.dumps(new_pman, ensure_ascii=False) + "\n")

    aman = json.loads((parent / "artwork/manifest.json").read_text())
    p_art = np.load(parent / "artwork/embeddings.npy")
    p_recs = json.loads((parent / "artwork/records.json").read_text())
    add_recs, add_vecs = [], []
    for b in scannable:
        for profile in PROFILES:
            add_recs.append({"card_id": b["fill"]["id"], "profile": profile, "language": LANG,
                             "name": b["fill"]["official_name_ja"], "set_name": b["fill"]["set_name"],
                             "collector_number": b["fill"]["id"].rsplit("-", 1)[-1], "reference_sha256": b["sha"]})
            add_vecs.append(b["art"][profile])
    adir = out / "artwork"
    adir.mkdir()
    np.save(adir / "embeddings.npy", np.concatenate([p_art.astype(np.float32), np.asarray(add_vecs, np.float32).reshape(-1, 384)]))
    recs = p_recs + add_recs
    (adir / "records.json").write_text(json.dumps(recs, ensure_ascii=False, separators=(",", ":")))
    new_aman = dict(aman)
    new_aman.update(base_embeddings_sha256=new_pman["embeddings_sha256"], base_ids_sha256=new_pman["ids_sha256"],
                    embeddings_sha256=sha_file(adir / "embeddings.npy"), records_sha256=sha_file(adir / "records.json"),
                    indexed_regions=len(recs), indexed_cards=len({r["card_id"] for r in recs}),
                    parent_manifest_sha256=sha_file(parent / "artwork/manifest.json"))
    (adir / "manifest.json").write_text(json.dumps(new_aman, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (out / "art-added.json").write_text(json.dumps([{**r, "source_vector_sha256": vh(v)} for r, v in zip(add_recs, add_vecs)],
                                                   ensure_ascii=False) + "\n")

    updates = [{"id": b["fill"]["id"], "image_path": f"{image_root}/{b['file'].name}", "image_sha256": b["sha"],
                "name_ja": b["fill"]["official_name_ja"], "name_en": b["fill"]["name"], "treatment": b["treatment"],
                "reason": b["reason"], "nearest_indexed": b["nearest_indexed"], "era": b["era"],
                "source": {k: b["fill"][k] for k in ("detail_url", "image_url", "official_card_id", "official_number", "sha256")}}
               for b in sorted(batch, key=lambda b: b["fill"]["id"].encode())]
    (out / "updates.json").write_text(json.dumps(updates, ensure_ascii=False, indent=1) + "\n")
    (out / "feature-rows.json").write_text(json.dumps([{"id": u["id"], "image_path": u["image_path"], "rarity": ""}
                                                       for u in updates], ensure_ascii=False) + "\n")
    report = {"name": name, "image_dir": image_root, "cards": len(batch), "scannable": len(scannable),
              "printing_alternatives": len(batch) - len(scannable), "pad_vectors": len(ids), "artwork_regions": len(recs),
              "parent_pad_sha256": pman["embeddings_sha256"]}
    (out / "release.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:7])
