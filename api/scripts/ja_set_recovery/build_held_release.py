"""Build the local files that give the held older-era Japanese cards their vectors. No DB access.

    python3 build_held_release.py RUN_DIR SERVED_PACKAGE ALL_ERAS_PACKAGE JAREC2_PACKAGE MODEL_ONNX NAME \
        BATCH_DIR [BATCH_DIR ...]

Step 5 of docs/ja-recovery-older-era-ranking-plan-20261107.md: the older-era cards held out of the
scan index since JAREC2 get pad vectors and two artwork regions, on top of the served release.

- SERVED_PACKAGE: the files behind the served catalogue (JAREC4's package; JAREC5 changed names
  only). Its pad and artwork manifests must match their files.
- Held cards from the first release: in ALL_ERAS_PACKAGE (JAREC, the all-eras candidate the
  gates were replayed on) and not in JAREC2_PACKAGE. Their vectors and artwork rows are copied
  from ALL_ERAS_PACKAGE unchanged: the exact vectors the gate replays used.
- Held cards from later image batches (BATCH_DIR/updates.json with "older era" reasons): vectors
  are taken from the batch's stored JPEG with the same model and profiles as every earlier wave.
  The release rule applies as before: a card whose pad cosine to an indexed Japanese card, or to
  another card added here, is >= 0.95 stays a printing alternative.

With HOLD_FILE set (a JSON list of {"id", "reason"}, step 5a), those cards keep no vectors and stay
printing alternatives with that reason.

Writes RUN_DIR/<NAME>/: vectors/pad/, artwork/, held.json, art-added.json, release.json.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
from app.recognition.artwork import PROFILES, crop_profile  # noqa: E402
from app.recognition.embed import DinoEmbedder  # noqa: E402

T = 0.95


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vh(vector):
    return hashlib.sha256(np.asarray(vector, dtype=">f4").tobytes()).hexdigest()


def load_package(path):
    pman = json.loads((path / "vectors/pad/manifest.json").read_text())
    ids = np.load(path / "vectors/pad/embedding_card_ids.npy").astype(str)
    pad = np.load(path / "vectors/pad/embeddings.npy")
    assert sha_file(path / "vectors/pad/embeddings.npy") == pman["embeddings_sha256"], path
    assert sha_file(path / "vectors/pad/embedding_card_ids.npy") == pman["ids_sha256"], path
    assert list(ids) == pman["indexed_ids"], path
    aman = json.loads((path / "artwork/manifest.json").read_text())
    art = np.load(path / "artwork/embeddings.npy")
    recs = json.loads((path / "artwork/records.json").read_text())
    assert sha_file(path / "artwork/embeddings.npy") == aman["embeddings_sha256"], path
    assert sha_file(path / "artwork/records.json") == aman["records_sha256"], path
    assert len(recs) == len(art) == aman["indexed_regions"], path
    return pman, ids, pad, aman, art, recs


def main(run_dir, served_dir, all_eras_dir, jarec2_dir, model_path, name, *batch_dirs):
    run = Path(run_dir).resolve()
    out = run / name
    out.mkdir(exist_ok=False)
    cards = {c["id"]: c for c in json.loads((run / "cards.json").read_text())}
    pman, p_ids, p_pad, aman, p_art, p_recs = load_package(Path(served_dir).resolve())
    _, a_ids, a_pad, _, a_art, a_recs = load_package(Path(all_eras_dir).resolve())
    j2_ids = set(np.load(Path(jarec2_dir).resolve() / "vectors/pad/embedding_card_ids.npy").astype(str))
    served = set(p_ids)

    # held cards from the first release: vectors exactly as replayed
    hold = {h["id"]: h["reason"] for h in json.loads(Path(os.environ["HOLD_FILE"]).read_text())} if os.environ.get("HOLD_FILE") else {}
    held_all = [cid for cid in a_ids if cid not in j2_ids]
    assert held_all and all(c.startswith("ja:") for c in held_all) and not set(held_all) & served
    held_a = [cid for cid in held_all if cid not in hold]
    a_pos = {cid: i for i, cid in enumerate(a_ids)}
    pads = {cid: a_pad[a_pos[cid]].astype(np.float32) for cid in held_a}
    held_a_set = set(held_a)
    arts = [(r, a_art[i].astype(np.float32)) for i, r in enumerate(a_recs) if r["card_id"] in held_a_set]
    assert {r["card_id"] for r, _ in arts} == held_a_set and len(arts) == 2 * len(held_a)
    held = [{"id": cid, "source": "all-eras package (replayed)", "nearest_indexed": None} for cid in held_a]

    # held cards from later image batches: new vectors, same rule as every wave
    model = DinoEmbedder(model_path, 4, 1)
    index_ids = [c for c in p_ids if c.startswith("ja:")] + held_a
    index = np.concatenate([p_pad[[i for i, c in enumerate(p_ids) if c.startswith("ja:")]], np.asarray([pads[c] for c in held_a])])
    batch = []
    for bdir in batch_dirs:
        bdir = Path(bdir).resolve()
        for u in json.loads((bdir / "updates.json").read_text()):
            if u["treatment"] == "printing_alternative" and u["reason"].startswith("older era"):
                batch.append((bdir, u))
    alternatives, kept_b = [{"id": cid, "reason": hold[cid], "nearest_indexed": None} for cid in held_all if cid in hold], []
    for bdir, u in sorted(batch, key=lambda x: x[1]["id"].encode()):
        cid = u["id"]
        assert cid not in served and cid not in held_a_set, cid
        if cid in hold:
            alternatives.append({"id": cid, "reason": hold[cid], "nearest_indexed": None})
            continue
        jpg = bdir / "images" / (cid.replace(":", "_") + ".jpg")
        assert sha_file(jpg) == u["image_sha256"], cid
        with Image.open(jpg) as im:
            rgb = im.convert("RGB")
            pad = model.embed(rgb, "pad").astype(np.float32)
            art = {p: model.embed(crop_profile(rgb, p), "pad").astype(np.float32) for p in PROFILES}
        sims = index @ pad
        j = int(sims.argmax())
        twin = next((k for k in kept_b if float(pads[k] @ pad) >= T), None)
        if sims[j] >= T or twin:
            alternatives.append({"id": cid, "reason": f"pad cosine {max(float(sims[j]), T):.4f} to "
                                 f"{twin or index_ids[j]}", "nearest_indexed": [index_ids[j], round(float(sims[j]), 4)]})
            continue
        pads[cid] = pad
        kept_b.append(cid)
        card = cards[cid]
        for profile in PROFILES:
            arts.append(({"card_id": cid, "profile": profile, "language": "ja", "name": u["name_ja"],
                          "set_name": card["set_name"], "collector_number": card["collector_number"],
                          "reference_sha256": u["image_sha256"]}, art[profile]))
        held.append({"id": cid, "source": f"{bdir.name} (new vectors)", "nearest_indexed": [index_ids[j], round(float(sims[j]), 4)]})

    new = sorted(pads, key=lambda c: c.encode())
    vdir = out / "vectors/pad"
    vdir.mkdir(parents=True)
    ids = list(p_ids) + new
    np.save(vdir / "embedding_card_ids.npy", np.asarray(ids, dtype=str))
    np.save(vdir / "embeddings.npy", np.concatenate([p_pad.astype(np.float32), np.asarray([pads[c] for c in new], np.float32)]))
    new_pman = dict(pman)
    new_pman.update(indexed_ids=ids, indexed_count=len(ids),
                    embeddings_sha256=sha_file(vdir / "embeddings.npy"), ids_sha256=sha_file(vdir / "embedding_card_ids.npy"),
                    parent_embeddings_sha256=pman["embeddings_sha256"], parent_ids_sha256=pman["ids_sha256"],
                    retrieval_segments=list(pman["retrieval_segments"]) + [len(new)],
                    catalogue_version=pman["catalogue_version"] + "-" + name)
    (vdir / "manifest.json").write_text(json.dumps(new_pman, ensure_ascii=False) + "\n")

    order = {c: i for i, c in enumerate(new)}
    arts.sort(key=lambda rv: (order[rv[0]["card_id"]], list(PROFILES).index(rv[0]["profile"]) if rv[0]["profile"] in PROFILES else 9))
    add_recs, add_vecs = [r for r, _ in arts], [v for _, v in arts]
    adir = out / "artwork"
    adir.mkdir()
    np.save(adir / "embeddings.npy", np.concatenate([p_art.astype(np.float32), np.asarray(add_vecs, np.float32)]))
    recs = p_recs + add_recs
    (adir / "records.json").write_text(json.dumps(recs, ensure_ascii=False, separators=(",", ":")))
    new_aman = dict(aman)
    new_aman.update(base_embeddings_sha256=new_pman["embeddings_sha256"], base_ids_sha256=new_pman["ids_sha256"],
                    embeddings_sha256=sha_file(adir / "embeddings.npy"), records_sha256=sha_file(adir / "records.json"),
                    indexed_regions=len(recs), indexed_cards=len({r["card_id"] for r in recs}),
                    parent_manifest_sha256=sha_file(Path(served_dir).resolve() / "artwork/manifest.json"))
    (adir / "manifest.json").write_text(json.dumps(new_aman, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (out / "art-added.json").write_text(json.dumps([{**r, "source_vector_sha256": vh(v)} for r, v in zip(add_recs, add_vecs)],
                                                   ensure_ascii=False) + "\n")
    (out / "held.json").write_text(json.dumps({"vectors_added": held, "still_alternatives": alternatives},
                                              ensure_ascii=False, indent=1) + "\n")
    report = {"name": name, "served_pad_sha256": pman["embeddings_sha256"], "held_from_all_eras": len(held_a),
              "hold_list": len(hold), "held_by_hold_list": sum(1 for a in alternatives if a["id"] in hold),
              "held_from_batches": len(batch), "batch_vectors_added": len(kept_b), "batch_twins_kept_alternative": len(alternatives),
              "pad_vectors": len(ids), "artwork_regions": len(recs), "artwork_added": len(add_recs)}
    (out / "release.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:7], *sys.argv[7:])
