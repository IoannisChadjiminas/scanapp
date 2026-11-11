"""Embed the recovery's new-card images. Local files only. No database writes.

Adapted from data/catalogue-gaps/tcgdex-empty-sets-20261017/build_vectors.py (same model,
modes, artwork profiles and output files). Checked on 2026-11-06: re-embedding two of
that wave's images here gives cosine 1.0 against its stored pad vectors.

    python3 build_vectors.py RUN_DIR MODEL_ONNX [WORKER/WORKERS]

With WORKER/WORKERS (for example 0/5) a process embeds only its share of the chunks and
stops; run once more without it to merge.

Reads RUN_DIR/cards.json (cards with an image and no problem). Like the earlier waves, each
image is first stored as the JPEG staging will serve (RUN_DIR/reference-images/<id with _>.jpg)
and the vectors are taken from that JPEG. Full resolution, JPEG quality 95 (owner: keep reference
quality for vectors); JPEG originals are copied unchanged.
Writes RUN_DIR/vectors/. Works in chunks of 500 cards under vectors/chunks/ so an interrupted
run resumes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

API = Path(__file__).resolve().parents[2]
REPO = API.parent
sys.path.insert(0, str(API))
from app.recognition.artifacts import sha256_file  # noqa: E402
from app.recognition.artwork import PROFILES, crop_profile  # noqa: E402
from app.recognition.embed import DinoEmbedder  # noqa: E402

sys.path.insert(0, str(REPO))
from catalogue.bootstrap.checks import BLUR_LIMIT, MIN_SIDE, load_facts  # noqa: E402

CHUNK = 500


def vh(vector: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(vector, dtype=">f4").tobytes()).hexdigest()


def main(run_dir: str, model_path: str, share: str | None = None) -> None:
    run = Path(run_dir).resolve()
    out = run / "vectors"
    chunks = out / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    images = run / "reference-images"
    images.mkdir(exist_ok=True)
    cards = [c for c in json.loads((run / "cards.json").read_text()) if c["local_file"] and not c["problem"]]
    cards.sort(key=lambda card: card["id"].encode())
    assert len(cards) == len({card["id"] for card in cards})
    model = DinoEmbedder(model_path, 2, 1)
    worker, workers = (int(x) for x in share.split("/")) if share else (0, 1)
    for start in range(0, len(cards), CHUNK):
        part = chunks / f"{start:05d}.npz"
        if part.exists() or (start // CHUNK) % workers != worker:
            continue
        pads, squares, arts, records = [], [], [], []
        for card in cards[start:start + CHUNK]:
            src = REPO / card["local_file"]
            dst = images / (card["id"].replace(":", "_") + ".jpg")
            if not dst.exists():
                tmp_img = dst.with_suffix(".tmp")
                if src.suffix.lower() in (".jpg", ".jpeg"):
                    shutil.copyfile(src, tmp_img)
                else:
                    with Image.open(src) as im:
                        im.convert("RGB").save(tmp_img, "JPEG", quality=95)
                tmp_img.rename(dst)
            facts = load_facts(dst)
            assert min(facts.width, facts.height) >= MIN_SIDE and facts.blur is not None and facts.blur >= BLUR_LIMIT, card["id"]
            with Image.open(dst) as image:
                rgb = image.convert("RGB")
                pad = model.embed(rgb, "pad").astype(np.float32)
                square = model.embed(rgb, "square").astype(np.float32)
                for profile in PROFILES:
                    vector = model.embed(crop_profile(rgb, profile), "pad").astype(np.float32)
                    assert vector.shape == (384,) and np.isfinite(vector).all()
                    arts.append(vector)
                    records.append({
                        "card_id": card["id"], "profile": profile, "language": "ja",
                        "name": card["name"], "set_name": card["set_name"],
                        "collector_number": card["collector_number"],
                        "source_vector_sha256": vh(vector), "source_file": card["local_file"],
                        "reference_sha256": sha256_file(dst),
                    })
            for vector in (pad, square):
                assert vector.shape == (384,) and np.isfinite(vector).all()
                assert abs(float(np.linalg.norm(vector)) - 1) < 0.01
            pads.append(pad)
            squares.append(square)
        tmp = part.with_suffix(".tmp.npz")
        np.savez(tmp, pad=np.asarray(pads, np.float32), square=np.asarray(squares, np.float32),
                 art=np.asarray(arts, np.float32), records=np.asarray([json.dumps(r, ensure_ascii=False) for r in records]))
        tmp.rename(part)
        print(json.dumps({"embedded": min(start + CHUNK, len(cards)), "of": len(cards)}), flush=True)
    if share:
        return

    parts = [np.load(chunks / f"{s:05d}.npz") for s in range(0, len(cards), CHUNK)]
    empty = np.zeros((0, 384), np.float32)  # a batch with no usable image (display-only rows) has no chunks
    pad = np.concatenate([p["pad"] for p in parts]) if parts else empty
    square = np.concatenate([p["square"] for p in parts]) if parts else empty
    arts = np.concatenate([p["art"] for p in parts]) if parts else empty
    records = [json.loads(r) for p in parts for r in p["records"]]
    ids = np.asarray([card["id"] for card in cards], dtype=str)
    assert len(pad) == len(square) == len(ids) and len(arts) == len(records) == len(ids) * len(PROFILES)
    np.save(out / "pad-embeddings.npy", pad)
    np.save(out / "square-embeddings.npy", square)
    np.save(out / "embedding-card-ids.npy", ids)
    np.savez_compressed(out / "artwork-delta.npz", embeddings=arts)
    (out / "artwork-delta-records.json").write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"cards": len(cards), "artwork": len(records)}), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
