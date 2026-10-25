"""Phase 0 offline feasibility run for the on-phone card index.

Reads the server's card index (embeddings + catalogue), builds fp32 / fp16 / int8
indexes, embeds the frozen A55 panel (phone-style crops, with jitter frames), the
11 vintage and 8 golden phone vectors, and the internet corpus, then writes the
numbers to a JSON file. Index binaries and per-frame vectors stay in --scratch.

Usage (see README.md):
    python api/scripts/instant/phase0_run.py --data-root <scanapp/data> --scratch <dir> --out-json <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import index_formats as idx  # noqa: E402
import metrics as met  # noqa: E402
from embedder import FRAME_SPECS, OnnxEmbedder, cosine, frames_for  # noqa: E402

REPO_ROOT = HERE.parents[2]
EMB_DIR = Path("android-embedding-research-20261023")
MARGINS = (0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10)
STABLE = (1, 2, 3)
TWIN_COSINE = 0.9
LANG_FAMILY = {"en": "en", "ja": "ja", "zh-cn": "zh", "zh-tw": "zh"}
CATEGORIES = ("unique", "twin-en-ja", "twin-other", "reprint")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_catalogue(path: Path) -> dict[str, dict[str, str]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select id, provider_id, name, set_id, collector_number, language from cards"
        ).fetchall()
    finally:
        connection.close()
    return {
        card_id: {"provider": provider, "name": name, "set_id": set_id, "number": number, "language": language}
        for card_id, provider, name, set_id, number, language in rows
    }


def family_key(meta: dict[str, str]) -> tuple[str, str]:
    return meta["name"].strip().lower(), meta["number"].strip().lstrip("0").lower()


def categorize(group: str, info: dict, unit_first: dict[str, np.ndarray], families: dict) -> str:
    """Twins: same name and number, same artwork (cosine >= 0.9), other language. Reprints: same language, other set."""
    own = info[group]
    found = set()
    for other in families[own["key"]]:
        if other == group:
            continue
        if cosine(unit_first[group], unit_first[other]) < TWIN_COSINE:
            continue
        other_info = info[other]
        if {own["lang"], other_info["lang"]} == {"en", "ja"}:
            found.add("twin-en-ja")
        elif own["lang"] != other_info["lang"]:
            found.add("twin-other")
        elif own["set_id"] != other_info["set_id"]:
            found.add("reprint")
    for name in ("twin-en-ja", "twin-other", "reprint"):
        if name in found:
            return name
    return "unique"


def client_text_of(entry: dict) -> dict[str, str | None]:
    """The phone's own OCR read (name and collector number) for a panel photo, if present."""
    try:
        parsed = json.loads(entry.get("client_text") or "{}")
    except json.JSONDecodeError:
        return {"name": None, "number": None}
    name = (parsed.get("name") or "").strip().lower() or None
    number = (parsed.get("number") or "").split("/")[0].strip().lstrip("0").lower() or None
    return {"name": name, "number": number}


def text_group_mask(group_names: tuple[str, ...], info: dict, text: dict[str, str | None]) -> np.ndarray:
    """Groups allowed by the phone's text, as a cascade: name and number, number, name, then no filter."""
    names = [info[g]["name"].strip().lower() for g in group_names]
    numbers = [info[g]["number"].strip().lstrip("0").lower() for g in group_names]
    number_ok = np.array([n == text["number"] for n in numbers]) if text["number"] else None
    name_ok = np.array([n and n in text["name"] for n in names]) if text["name"] else None
    options = []
    if number_ok is not None and name_ok is not None:
        options.append(number_ok & name_ok)
    if number_ok is not None:
        options.append(number_ok)
    if name_ok is not None:
        options.append(name_ok)
    for option in options:
        if option.any():
            return option
    return np.ones(len(group_names), dtype=bool)


def score_panel(index, frame_vectors, labelled, families, info, category, text=None):
    """Top-1/top-5/margins for each labelled photo, optionally restricted to the phone's text candidates."""
    records: list[met.PhotoRecord] = []
    misses: list[dict] = []
    for item in labelled:
        label = item["label"]
        family = frozenset(families[info[label]["key"]])
        group_mask = None
        if text is not None:
            group_mask = text_group_mask(index.group_names, info, text[item["id"]])
            row_mask = group_mask[index.group_codes]
        frames: list[tuple[str, float]] = []
        top5: tuple[str, ...] = ()
        for frame_index, vector in enumerate(frame_vectors[item["id"]]):
            scores = idx.row_scores(index, vector)
            if group_mask is not None:
                scores = np.where(row_mask, scores, np.float32(-np.inf))
            hits = [h for h in idx.rank_groups(index, scores, k=5) if np.isfinite(h.score)]
            frames.append((hits[0].group if hits else "", idx.margin(hits)))
            if frame_index == 0:
                top5 = tuple(h.group for h in hits)
        record = met.PhotoRecord(
            photo_id=item["id"], label=label, category=category[label], family=family,
            top5=top5, frames=tuple(frames),
        )
        records.append(record)
        if not met.top1_correct(record):
            misses.append({
                "label_card": item["label_card"],
                "label_category": category[label],
                "top1_card_group": frames[0][0],
                "top1_in_family": met.top1_in_family(record),
                "label_rank_in_top5": (top5.index(label) + 1) if label in top5 else None,
                "margin_frame0": round(frames[0][1], 4),
            })
    return records, misses


def summarise_variant(indexes, frame_vectors, labelled, families, info, category, text=None) -> dict:
    variant: dict = {"accuracy": {}, "margins": {}, "rules": {}, "best_rule": {}, "misses_top1": {}}
    for fmt, index in indexes.items():
        records, misses = score_panel(index, frame_vectors, labelled, families, info, category, text)
        per_category = {}
        for name in CATEGORIES:
            subset = [r for r in records if r.category == name]
            per_category[name] = met.accuracy(subset) if subset else {"photos": 0}
        variant["accuracy"][fmt] = {"all": met.accuracy(records), "by_category": per_category}
        variant["margins"][fmt] = {
            "correct_top1": met.margin_distribution([r.frames[0][1] for r in records if met.top1_correct(r)]),
            "wrong_top1": met.margin_distribution([r.frames[0][1] for r in records if not met.top1_correct(r)]),
        }
        rules = met.scan_rules(records, MARGINS, STABLE)
        variant["rules"][fmt] = [r.__dict__ for r in rules]
        best = met.smallest_risk_rule(rules, max_wrong_rate=0.01)
        variant["best_rule"][fmt] = best.__dict__ if best else None
        variant["misses_top1"][fmt] = misses
    return variant


def run(args: argparse.Namespace) -> dict:
    data = args.data_root.resolve()
    vec_dir = data / EMB_DIR / "catalogue" / "vectors" / "pad"
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    started = time.time()
    report: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    # 1. Server index, catalogue metadata and binary check
    model_path = data / EMB_DIR / "teacher" / "dinov2_small.onnx"
    manifest = json.loads((vec_dir / "manifest.json").read_text())
    report["server_index"] = {
        "source": f"{EMB_DIR}/catalogue/vectors/pad (server export, read locally)",
        "catalogue_import_id": "PS-CATALOGUE-EN-JA-ENID2-20261019",
        "model_sha256_prefix_manifest": manifest["dinov2_sha256"][:16],
        "model_file_sha256_prefix": sha256(model_path)[:16],
        "model_revision": manifest["model_revision"],
        "preprocess": manifest["preprocess_config"],
        "catalogue_cards": manifest["card_count"],
        "indexed_rows": manifest["indexed_count"],
    }
    assert report["server_index"]["model_file_sha256_prefix"] == manifest["dinov2_sha256"][:16], "model mismatch"

    raw_vectors = np.load(vec_dir / "embeddings.npy")
    ids = [str(x) for x in np.load(vec_dir / "embedding_card_ids.npy", allow_pickle=True).tolist()]
    catalogue = load_catalogue(data / EMB_DIR / "catalogue" / "catalog.sqlite")
    missing_meta = [i for i in ids if i not in catalogue]
    groups = [catalogue[i]["provider"] if i in catalogue else i for i in ids]
    report["server_index"]["rows"] = len(ids)
    report["server_index"]["unique_ids"] = len(set(ids))
    report["server_index"]["catalogue_groups"] = len(set(groups))
    report["server_index"]["duplicate_rows_collapsed"] = len(ids) - len(set(groups))
    report["server_index"]["rows_without_catalogue_metadata"] = len(missing_meta)
    report["server_index"]["languages"] = dict(Counter(catalogue[i]["language"] for i in ids if i in catalogue))

    # 2. Three formats, saved to scratch (never committed)
    indexes: dict[str, idx.CardIndex] = {}
    report["formats"] = {}
    for fmt in idx.FORMATS:
        index = idx.build_index(fmt, raw_vectors, ids, groups)
        indexes[fmt] = index
        matrix_path = scratch / f"index-{fmt}.npy"
        np.save(matrix_path, index.matrix)
        size = index.nbytes()
        if index.row_scales is not None:
            np.save(scratch / "index-int8-scales.npy", index.row_scales)
        report["formats"][fmt] = {
            "bytes_in_memory": size,
            "megabytes": round(size / 1e6, 2),
            "matrix_dtype": str(index.matrix.dtype),
            "groups": len(index.group_names),
        }

    fp32 = indexes["fp32"]
    unit_all = fp32.matrix
    first_row: dict[str, int] = {}
    for row, code in enumerate(fp32.group_codes.tolist()):
        first_row.setdefault(fp32.group_names[code], row)
    unit_first = {group: unit_all[row] for group, row in first_row.items()}
    info = {}
    families: dict[tuple[str, str], list[str]] = defaultdict(list)
    for group in fp32.group_names:
        row_id = fp32.ids[first_row[group]]
        meta = catalogue.get(row_id, {"provider": group, "name": row_id, "set_id": "", "number": "", "language": "?"})
        key = family_key(meta) if meta["name"] else (row_id, "")
        info[group] = {
            "key": key,
            "lang": LANG_FAMILY.get(meta["language"], meta["language"]),
            "set_id": meta["set_id"],
            "name": meta["name"],
            "number": meta["number"],
        }
        families[key].append(group)
    group_category = {g: categorize(g, info, unit_first, families) for g in fp32.group_names}
    report["categories_in_index"] = dict(Counter(group_category.values()))

    # 3. Panel: phone-style crops, jitter frames, labels
    panel = json.loads((data / EMB_DIR / "panel-queries" / "queries.json").read_text())
    embedder = OnnxEmbedder(model_path)
    frame_vectors: dict[str, np.ndarray] = {}
    labelled: list[dict] = []
    no_crop = 0
    label_missing = 0
    timings_embed = []
    for entry in panel:
        warped = entry.get("warped_image_path")
        expected = entry.get("expected_card_ids") or []
        if not warped or not Path(warped).exists():
            no_crop += 1
            continue
        if not expected:
            label_missing += 1
            continue
        label_row = expected[0]
        label_group = catalogue[label_row]["provider"] if label_row in catalogue else label_row
        if label_group not in unit_first:
            label_missing += 1
            continue
        image = Image.open(warped)
        vectors = []
        for frame in frames_for(image):
            started_one = time.perf_counter()
            vectors.append(embedder.embed_image(frame, "pad"))
            timings_embed.append((time.perf_counter() - started_one) * 1000)
        frame_vectors[entry["id"]] = np.stack(vectors)
        labelled.append({"id": entry["id"], "label": label_group, "label_card": label_row})
    report["panel"] = {
        "photos_in_panel": len(panel),
        "with_warped_crop": len(labelled) + label_missing,
        "scored": len(labelled),
        "no_crop_excluded": no_crop,
        "label_missing_from_index_excluded": label_missing,
        "frames_per_photo": len(FRAME_SPECS),
        "embed_ms_median_mac": round(statistics.median(timings_embed), 1) if timings_embed else None,
    }
    np.savez(scratch / "panel-frames.npz", **{k: v for k, v in frame_vectors.items()})

    # 4. Evaluate each format on the scored panel: image only, then with the phone's own text
    panel_entries = {entry["id"]: entry for entry in panel}
    text_of = {item["id"]: client_text_of(panel_entries[item["id"]]) for item in labelled}
    report["variants"] = {
        "image_only": summarise_variant(indexes, frame_vectors, labelled, families, info, group_category),
        "text_filtered": summarise_variant(indexes, frame_vectors, labelled, families, info, group_category, text_of),
    }
    report["text_coverage"] = {
        "photos_with_name": sum(1 for v in text_of.values() if v["name"]),
        "photos_with_number": sum(1 for v in text_of.values() if v["number"]),
    }

    # 5. Categories of the scored panel labels and of the whole index
    report["panel_categories"] = dict(Counter(group_category[item["label"]] for item in labelled))

    # 6. Search timing on this Mac (brute force, one query at a time, median of many)
    queries = np.concatenate([frame_vectors[k] for k in list(frame_vectors)[:60]])
    timing = {}
    for fmt, index in indexes.items():
        samples = []
        for vector in queries[:200]:
            begin = time.perf_counter()
            idx.search(index, vector, k=5)
            samples.append((time.perf_counter() - begin) * 1000)
        samples.sort()
        timing[fmt] = {
            "queries": len(samples),
            "median_ms": round(statistics.median(samples), 2),
            "p90_ms": round(samples[int(0.9 * (len(samples) - 1))], 2),
            "scan_bytes": indexes[fmt].nbytes(),
        }
    report["search_timing_mac"] = timing

    # 7. Phone vs server: golden fixtures (vectors from the iPhone Core ML model)
    golden = np.load(data / "latency" / "ondevice-embedding-20261020" / "ondevice_golden.npz", allow_pickle=True)
    golden_rows = []
    for key, tensor, phone in zip(golden["keys"], golden["inputs"], golden["vectors"]):
        server_vector = embedder.embed_tensor(tensor[None].astype(np.float32))
        phone_unit = phone / np.linalg.norm(phone)
        hits = idx.search(fp32, phone_unit, k=5)
        expected_group = catalogue[str(key)]["provider"] if str(key) in catalogue else None
        golden_rows.append({
            "key_in_catalogue": str(key) in catalogue,
            "cosine_phone_vs_server": round(cosine(server_vector, phone_unit), 4),
            "top1_matches_key": bool(expected_group) and hits[0].group == expected_group,
        })
    report["golden_phone_check"] = {
        "fixtures": len(golden_rows),
        "min_cosine": min(r["cosine_phone_vs_server"] for r in golden_rows),
        "top1_matches_key": sum(r["top1_matches_key"] for r in golden_rows),
        "keys_in_catalogue": sum(r["key_in_catalogue"] for r in golden_rows),
    }

    # 8. Server-model fidelity: reference images against their stored index rows
    ref_dir = data / EMB_DIR / "reference-images"
    sample_ids = [i for i in ids if (ref_dir / f"{i}.webp").exists()][:30]
    row_of = {i: r for r, i in enumerate(ids)}
    fidelity = []
    for card_id in sample_ids:
        vector = embedder.embed_image(Image.open(ref_dir / f"{card_id}.webp"), "pad")
        fidelity.append(cosine(vector, raw_vectors[row_of[card_id]]))
    report["reference_fidelity"] = {
        "sampled": len(fidelity),
        "min_cosine": round(min(fidelity), 5) if fidelity else None,
        "median_cosine": round(statistics.median(fidelity), 5) if fidelity else None,
    }

    # 9. Internet corpus: full-photo embeddings (no labels, no card crop): agreement and margins only
    corpus_dir = data / "photo-corpus-fullsize-20261023" / "raw"
    corpus_paths = sorted(corpus_dir.glob("*.jpg"))
    corpus_top = defaultdict(list)
    corpus_margin = defaultdict(list)
    corpus_time = []
    for path in corpus_paths:
        began = time.perf_counter()
        vector = embedder.embed_image(Image.open(path), "pad")
        corpus_time.append((time.perf_counter() - began) * 1000)
        for fmt, index in indexes.items():
            hits = idx.search(index, vector, k=5)
            corpus_top[fmt].append(hits[0].group)
            corpus_margin[fmt].append(idx.margin(hits))
    agree = {fmt: sum(a == b for a, b in zip(corpus_top[fmt], corpus_top["fp32"])) for fmt in indexes}
    report["corpus_unlabelled"] = {
        "photos": len(corpus_paths),
        "embed_ms_median_mac": round(statistics.median(corpus_time), 1) if corpus_time else None,
        "top1_agreement_with_fp32": {fmt: round(agree[fmt] / len(corpus_paths), 4) for fmt in indexes},
        "margin_share_at_least": {
            fmt: {str(m): round(sum(v >= m for v in corpus_margin[fmt]) / len(corpus_paths), 4)
                  for m in (0.01, 0.02, 0.03, 0.05)}
            for fmt in indexes
        },
    }

    report["elapsed_s"] = round(time.time() - started, 1)
    report["misses_note"] = "card ids only; photo ids withheld from the write-up"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path, required=True, help="the scanapp data/ directory")
    parser.add_argument("--scratch", type=Path, required=True, help="where index binaries and frame vectors go (not git)")
    parser.add_argument("--out-json", type=Path, default=REPO_ROOT / "docs/experiments/instant-recognition-phase0-20261025.json")
    args = parser.parse_args(argv)
    report = run(args)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out_json} in {report['elapsed_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
