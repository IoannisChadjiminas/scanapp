"""Compare proposed code with deployed code, without deploying or writing data.

Run inside the staging API container, with an isolated patch directory and the
audit report. Catalogue/vectors are loaded through the existing read-only role.
Scan results live only in in-memory SQLite; stored diagnostic inputs are read.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

from app.config import get_settings
from app.db import init_catalog, init_results
from app.planetscale import load_cloud_catalogue
from app.recognition.runtime import Runtime
from app.recognition import pipeline as baseline
from app.recognition.ocr import CardOcr as BaselineOcr
from app.recognition.rank import decide_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    settings = get_settings().model_copy(update={"store_captures": False})
    catalog = sqlite3.connect(":memory:")
    catalog.row_factory = sqlite3.Row
    init_catalog(catalog)
    snapshot = load_cloud_catalogue(settings, catalog)
    runtime = Runtime(settings)
    runtime.load(snapshot)
    runtime.bind_card_languages(catalog)
    runtime.require()
    scratch = sqlite3.connect(":memory:")
    scratch.row_factory = sqlite3.Row
    init_results(scratch)
    scratch.execute("INSERT INTO sessions VALUES ('edge-probe','test','test')")
    scratch.commit()
    deployed_decide = decide_status
    modules = {}
    # Loading new module objects preserves baseline function globals; these do
    # not replace module objects in the running service's separate process.
    for name in ("cardmarket", "recognition.embed", "recognition.ocr",
                 "recognition.rank", "recognition.orientation", "recognition.pipeline"):
        full_name = "app." + name
        path = args.patch / "api/app" / (name.replace(".", "/") + ".py")
        spec = importlib.util.spec_from_file_location(full_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
        modules[name] = module

    outputs = []
    try:
        for case in report["cases"]:
            scan_id = case["threshold_replay"]["scan_id"]
            # Validate file identity before joining a path supplied by a report.
            import uuid
            assert str(uuid.UUID(scan_id)) == scan_id
            source = settings.review_dir / "images" / f"{scan_id}.input.jpg"
            data = source.read_bytes()
            versions = {}
            for label, recognize, ocr_class, decide in (
                ("before", baseline.recognize_bytes, BaselineOcr, deployed_decide),
                ("after", modules["recognition.pipeline"].recognize_bytes,
                 modules["recognition.ocr"].CardOcr, modules["recognition.rank"].decide_status),
            ):
                if runtime.ocr is not None:
                    runtime.ocr.__class__ = ocr_class
                response = recognize(data, settings=settings, runtime=runtime,
                    catalog=catalog, results=scratch, session_id="edge-probe",
                    language=case["expected_language"], store_capture=False)
                top = response.suggestions[0] if response.suggestions else None
                same = top is not None and (
                    top.name == case["expected_name"] and
                    top.set_name == case["expected_set"] and
                    top.collector_number == case["expected_number"] and
                    top.language == case["expected_language"])
                saved = scratch.execute("SELECT combined_ranking_json FROM scans WHERE id=?",
                                        (response.id,)).fetchone()
                ranking = json.loads(saved[0])
                hypothetical = decide(ranking, enable_matched=True,
                    min_visual=settings.threshold_min_visual,
                    min_visual_ocr=settings.threshold_min_visual_ocr,
                    min_gap=settings.threshold_min_gap, retake=response.status == "retake")
                variants = [v.model_dump() for v in top.cardmarket_variants] if top else []
                versions[label] = {
                    "top_id": top.card_id if top else None,
                    "identity_correct": same, "status": response.status,
                    "hypothetical_status": hypothetical,
                    "false_confident_if_enabled": hypothetical == "matched" and
                        (case["negative_input"] or not same),
                    "variant_contamination": any("Victini" in v["url"] for v in variants)
                        if case["expected_id"] == "ja:SV-P-051" else False,
                    "variants": variants, "timings": response.timings_ms,
                    "ranking": [{k:r.get(k) for k in ("card_id", "visual_score",
                        "combined_score", "collector_conflict", "ocr_consistent")}
                        for r in ranking[:5]],
                }
            row = {"expected_id": case["expected_id"], "condition": case["condition"],
                   "negative_input": case["negative_input"], **versions}
            outputs.append(row)
            print(json.dumps(row), flush=True)
    finally:
        scratch.close()
        catalog.close()
    print(json.dumps({"summary": {"probes": len(outputs),
        "before_correct": sum(r["before"]["identity_correct"] for r in outputs if not r["negative_input"]),
        "after_correct": sum(r["after"]["identity_correct"] for r in outputs if not r["negative_input"]),
        "false_confident_after": sum(r["after"]["false_confident_if_enabled"] for r in outputs),
        "note": "Paired stored diagnostic JPEGs; not a live app deployment or camera benchmark."}}), flush=True)


if __name__ == "__main__":
    main()
