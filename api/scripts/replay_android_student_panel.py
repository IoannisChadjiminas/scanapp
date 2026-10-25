"""Offline candidate-model replay on the frozen 157-photo stage-0 panel.

This is a research replay: it does not modify serving code, call the network,
or write scans. Candidate vectors and warped query images must be built from
the exact LiteRT export before running it.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.recognition import stage1_answer
from app.recognition.client_embedding import parse_client_embedding
from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier
from app.recognition.stage1_gate import GateOptions, same_card
from app.scan_summary import parse_quad


def replay(*, panel: Path, query_manifest: Path, vectors_file: Path,
           model_id: str, output: Path) -> dict:
    rows = [json.loads(line) for line in (panel / "stage0.jsonl").read_text().splitlines()]
    cases = {row["id"]: row for row in json.loads((panel / "cases.json").read_text())}
    queries = {row["id"]: row for row in json.loads(query_manifest.read_text())}
    full = {
        row["id"]: row
        for row in map(json.loads, (panel / "replay.jsonl").read_text().splitlines())
    }
    baseline = {row["id"]: row for row in json.loads((panel / "stage1.json").read_text())[
        "comparison"]["AB"]["margin_ge_0.02"]["answers"]}
    baseline.update({row["id"]: row for row in json.loads((panel / "stage1b.json").read_text())["answers"]})
    if len(rows) != 157 or len(baseline) != 53:
        raise ValueError(f"Frozen panel drift: {len(rows)} photos, {len(baseline)} baseline early answers")

    vector_archive = np.load(vectors_file, allow_pickle=False)
    ids = vector_archive["ids"].astype(str).tolist()
    embeddings = np.asarray(vector_archive["vectors"], dtype=np.float32)
    query_ids = vector_archive["query_ids"].astype(str).tolist()
    query_vectors = np.asarray(vector_archive["query_vectors"], dtype=np.float32)
    recorded_model_hash = str(vector_archive["model_sha256"])
    expected_hash = model_id.split("/", 1)[0]
    if not recorded_model_hash.startswith(expected_hash):
        raise ValueError("Candidate model ID does not match the TFLite artifact hash")
    if len(ids) != len(set(ids)) or embeddings.shape != (len(ids), 384):
        raise ValueError("Invalid reference index shape or IDs")
    if len(query_ids) != len(set(query_ids)) or query_vectors.shape != (len(query_ids), 384):
        raise ValueError("Invalid query-vector shape or IDs")
    if not np.isfinite(embeddings).all() or not np.isfinite(query_vectors).all():
        raise ValueError("Candidate index contains a non-finite vector")
    norms = np.linalg.norm(embeddings, axis=1)
    query_norms = np.linalg.norm(query_vectors, axis=1)
    if np.any(norms < .98) or np.any(norms > 1.02) or np.any(query_norms < .98) or np.any(query_norms > 1.02):
        raise ValueError("Candidate index or query vectors are not unit-normalized")

    original_parser = parse_client_embedding
    stage1_answer.parse_client_embedding = lambda raw: original_parser(raw, expected_model=model_id)
    source = sqlite3.connect(f'file:{panel / "kit/catalog.sqlite"}?mode=ro', uri=True)
    catalog = sqlite3.connect(":memory:")
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    totals_path = Path(__file__).resolve().parents[1] / "tests/fixtures/stage1-set-totals-20261022.json"
    totals = json.loads(totals_path.read_text())
    catalog.executemany(
        "INSERT OR REPLACE INTO set_totals(language,set_id,official_total,fetched_at) VALUES (?,?,?,?)",
        [(row["language"], row["set_id"], row["official_total"], "2026-10-22") for row in totals],
    )
    # Reuse the frozen panel's original artwork bundle so the candidate and
    # DINOv2 baseline stage-1b checks see the same reference files/features.
    verifier = LocalArtworkVerifier(panel / "kit")
    verifier.reference_boxes = {
        row["id"]: FULL_ART_BOX
        for row in catalog.execute("SELECT id,rarity FROM cards")
        if str(row["rarity"] or "").casefold() in FULL_ART_RARITIES
    }
    runtime = SimpleNamespace(
        snapshot=SimpleNamespace(embeddings=embeddings, card_ids=ids),
        artwork_verifier=verifier,
        stage1_catalogue=None,
        stage1_catalogue_options=None,
    )
    settings = SimpleNamespace(
        stage1b_text_verify=True,
        stage1_set_totals=True,
        stage1_normalize_duplicates=True,
        stage1_printing_groups=True,
        stage1_promo_numbers=True,
        stage1_diagnostics=True,
    )
    vector_position = {ident: index for index, ident in enumerate(query_ids)}
    result_rows = {}
    for row in rows:
        ident = row["id"]
        query = queries.get(ident)
        vector = None
        if query is not None and query.get("warped_image_path") and ident in vector_position:
            vector = query_vectors[vector_position[ident]]
        raw_embedding = None
        if vector is not None:
            payload = np.asarray(vector, dtype="<f2").tobytes()
            raw_embedding = json.dumps({"model": model_id, "vector": base64.b64encode(payload).decode("ascii")})
        source_photo = (query or {}).get("source_photo_path")
        image_bytes = Path(source_photo).read_bytes() if source_photo and Path(source_photo).is_file() else b""
        decision = stage1_answer.evaluate_stage1(
            settings=settings,
            runtime=runtime,
            catalog=catalog,
            client_text=row.get("client_text"),
            client_embedding=raw_embedding,
            card_quad=parse_quad(row.get("card_quad")),
            image_bytes=image_bytes,
        )
        expected = cases[ident]["expected_card_ids"]
        offered = decision.printing_ids or ((decision.card_id,) if decision.card_id else ())
        correct = None if not decision.answered else any(
            same_card(candidate, truth) for candidate in offered for truth in expected
        )
        result_rows[ident] = {
            **asdict(decision),
            "correct": correct,
            "expected_card_ids": expected,
            "full_pipeline_card_id": full.get(ident, {}).get("card_id"),
            "has_candidate_vector": vector is not None,
            "has_quad": bool(row.get("card_quad")),
        }

    answers = {ident: row for ident, row in result_rows.items() if row["answered"]}
    wrong = [ident for ident, row in answers.items() if row["correct"] is not True]
    summary = {
        "model_id": model_id,
        "photos": len(rows),
        "query_vectors": len(query_ids),
        "answers": len(answers),
        "answers_by_stage": dict(Counter(row["stage"] for row in answers.values())),
        "wrong": len(wrong),
        "wrong_ids": wrong,
        "baseline_answers": len(baseline),
        "baseline_answers_retained": sum(
            ident in answers and same_card(answers[ident]["card_id"], baseline[ident]["card"])
            for ident in baseline
        ),
        "added_vs_baseline": [ident for ident in answers if ident not in baseline],
        "lost_vs_baseline": [ident for ident in baseline if ident not in answers],
        "unavailable_without_quad": sum(not row.get("card_quad") for row in rows),
        "errors_not_a_pass": bool(wrong),
        "limitation": "Synthetic model scoring uses the frozen historical crop/text/quad panel; corpus web photos remain unlabeled and real staging requests are not sent.",
    }
    output.write_text(json.dumps({"summary": summary, "panel": result_rows}, indent=2) + "\n")
    catalog.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(replay(
        panel=args.panel,
        query_manifest=args.query_manifest,
        vectors_file=args.vectors,
        model_id=args.model_id,
        output=args.output,
    ), indent=2))


if __name__ == "__main__":
    main()
