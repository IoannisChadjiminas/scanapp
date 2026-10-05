"""Offline crop audit: read-only source volume, no network, in-memory results.

Run with the API's pinned dependencies, mounting /data and this checkout read-only.
This is a synthetic safety/coverage benchmark, not real-camera accuracy.
"""
from __future__ import annotations

from dataclasses import fields
import argparse
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image

from app.config import Settings
from app.db import init_results
from app.recognition.artifacts import ArtifactSnapshot, resolve_bundle_dir, validate_embeddings
from app.recognition.pipeline import recognize_bytes
from app.recognition.printing import ART_BOX, printing_key
from app.recognition.runtime import Runtime


FIXTURES = ("en:base1-58", "en:30th-c-014", "en:PPS2-BRS-121",
            "en:sv01-036", "ja:SV-P-051")
CROPS = {
    "full": (0, 0, 1, 1),
    "art_only": ART_BOX,
    "top_half": (0, 0, 1, .55),
    "bottom_half": (0, .5, 1, 1),
    "partial_crop": (0, .08, 1, .92),
    "central_patch": (.3, .3, .7, .7),
}


def crop_image(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = image.size
    return image.crop(tuple(round(v * (w if i % 2 == 0 else h)) for i, v in enumerate(box)))


def load_readonly_runtime(settings: Settings, catalog: sqlite3.Connection) -> Runtime:
    # RapidOCR initializes a visualization font even when no visualization is
    # requested. Disable only that unused drawing setup in this network-isolated
    # benchmark; recognition models/text/confidences are unchanged.
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *args, **kwargs: "unused-benchmark-drawing-font"
    bundle = resolve_bundle_dir(settings.vectors_dir)
    manifest = json.loads((bundle / "manifest.json").read_text())
    vectors = np.load(bundle / "embeddings.npy", mmap_mode="r")
    ids = np.load(bundle / "embedding_card_ids.npy")
    validate_embeddings(vectors, ids)
    snapshot_values = {f.name: manifest.get(f.name) for f in fields(ArtifactSnapshot)
                       if f.name not in {"embeddings", "card_ids", "manifest", "bundle_dir"}}
    snapshot_values.update(preprocess_config=settings.preprocess_config,
                           use_ocr=settings.use_ocr,
                           catalogue_version=str(manifest.get("catalogue_version") or "local"),
                           model_revision=str(manifest.get("model_revision") or "local"),
                           model_name=settings.model_name)
    snapshot = ArtifactSnapshot(**snapshot_values, embeddings=vectors, card_ids=ids,
                                manifest=manifest, bundle_dir=bundle)
    runtime = Runtime(settings)
    runtime.load(snapshot)
    runtime.bind_card_languages(catalog)
    runtime.require()
    return runtime


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path)
    args = parser.parse_args()
    settings = Settings(data_dir=Path("/data"), store_captures=False,
                        catalogue_backend="sqlite", enable_matched=True)
    source = sqlite3.connect("file:/data/catalog.sqlite?mode=ro", uri=True)
    catalog = sqlite3.connect(":memory:")
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    catalog.execute("PRAGMA query_only=ON")
    runtime = load_readonly_runtime(settings, catalog)
    results = sqlite3.connect(":memory:")
    results.row_factory = sqlite3.Row
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('crop-audit', 'test', 'test')")
    results.commit()
    baseline = None
    if args.baseline_dir:
        import app.recognition.rank as current_rank
        rank_path = args.baseline_dir / "api/app/recognition/rank.py"
        spec = importlib.util.spec_from_file_location("app.recognition.rank", rank_path)
        baseline_rank = importlib.util.module_from_spec(spec)
        sys.modules["app.recognition.rank"] = baseline_rank
        try:
            spec.loader.exec_module(baseline_rank)
            pipeline_path = args.baseline_dir / "api/app/recognition/pipeline.py"
            spec = importlib.util.spec_from_file_location("app.recognition.baseline_pipeline", pipeline_path)
            baseline_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(baseline_module)
            baseline = baseline_module.recognize_bytes
        finally:
            sys.modules["app.recognition.rank"] = current_rank
    cases = []
    for card_id in FIXTURES:
        truth = catalog.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if truth is None or not Path(truth["image_path"] or "").is_file():
            raise RuntimeError(f"Required crop fixture is unavailable: {card_id}")
        truth = dict(truth)
        with Image.open(truth["image_path"]) as original:
            image = original.convert("RGB")
        for condition, box in CROPS.items():
            cropped = crop_image(image, box)
            payload = io.BytesIO()
            cropped.save(payload, format="JPEG", quality=90)
            before = None
            if baseline:
                before_response = baseline(payload.getvalue(), settings=settings,
                    runtime=runtime, catalog=catalog, results=results,
                    session_id="crop-audit", language=truth["language"],
                    skip_detect=True, store_capture=False)
                before_top = before_response.suggestions[0] if before_response.suggestions else None
                before = {"status": before_response.status.value,
                          "top_id": before_top.card_id if before_top else None,
                          "candidate_recalled": before_top is not None and
                            (before_top.set_name, before_top.collector_number, before_top.language) ==
                            (truth["set_name"], truth["collector_number"], truth["language"])}
            started = time.perf_counter()
            response = recognize_bytes(payload.getvalue(), settings=settings,
                runtime=runtime, catalog=catalog, results=results,
                session_id="crop-audit", language=truth["language"],
                skip_detect=True, store_capture=False)
            saved = results.execute("SELECT combined_ranking_json FROM scans WHERE id=?", (response.id,)).fetchone()
            ranking = json.loads(saved[0])
            top = ranking[0] if ranking else None
            top_correct = top is not None and printing_key(top) == printing_key(truth)
            review = response.printing_review
            returned = review.plausible_printings if review else response.suggestions
            recalled = any((p.set_name, p.collector_number, p.language) ==
                           (truth["set_name"], truth["collector_number"], truth["language"]) for p in returned)
            case = {"expected_id": card_id, "condition": condition,
                    "status": response.status.value, "top_id": top["card_id"] if top else None,
                    "top_correct": top_correct, "candidate_recalled": recalled,
                    "false_specific_claim": response.status.value == "matched" and not top_correct,
                    "printing_review": review.model_dump(mode="json") if review else None,
                    "local_artwork_matches": json.loads(results.execute("SELECT ocr_json FROM scans WHERE id=?",
                        (response.id,)).fetchone()[0]).get("local_artwork_matches", []),
                    "ocr_failed": response.ocr.failed,
                    "before": before,
                    "timings_ms": response.timings_ms,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
            cases.append(case)
            print(json.dumps({"case": case}), flush=True)
    negatives = []
    for label, pixels in (
        ("blank", np.full((700, 500, 3), 240, dtype=np.uint8)),
        ("random_noise", np.random.default_rng(12).integers(0, 255, (700, 500, 3), dtype=np.uint8)),
    ):
        payload = io.BytesIO()
        Image.fromarray(pixels).save(payload, format="JPEG", quality=90)
        response = recognize_bytes(payload.getvalue(), settings=settings,
            runtime=runtime, catalog=catalog, results=results,
            session_id="crop-audit", language="en", skip_detect=True, store_capture=False)
        negatives.append({"condition": label, "status": response.status.value,
                          "false_specific_claim": response.status.value == "matched"})
        print(json.dumps({"negative": negatives[-1]}), flush=True)
    print(json.dumps({"summary": {"probes": len(cases),
        "top_correct": sum(c["top_correct"] for c in cases),
        "candidate_recalled": sum(c["candidate_recalled"] for c in cases),
        "negative_probes": len(negatives),
        "false_specific_claims": sum(c["false_specific_claim"] for c in [*cases, *negatives]),
        "printing_ambiguous": sum(c["status"] == "printing_ambiguous" for c in cases),
        "baseline_candidate_recalled": sum(c["before"]["candidate_recalled"] for c in cases if c["before"]),
        "regressed_candidate_recall": sum(c["before"]["candidate_recalled"] and not c["candidate_recalled"]
                                        for c in cases if c["before"]),
        "source": "local read-only SQLite/reference/vector volume; not PlanetScale or live staging",
        "visualization_font_setup_disabled": True,
        "note": "Synthetic reference crops. Low-resolution retakes count as retrieval misses; no confidence calibration claim."}}), flush=True)
    results.close()
    catalog.close()


if __name__ == "__main__":
    main()
