"""Offline full-pipeline replay of the regression panels against one catalogue release.

Runs in a separate, memory-capped container from the served API image on staging, with the
API's environment and the release's four catalogue keys. It starts the runtime the way the
app does (Databases -> cloud snapshot -> Runtime.load -> bind_card_languages) and calls the
real recognize_bytes with persist=False and the route defaults, so no scan permit, results
database or capture is involved. Writes one JSON line per photo:

    python3 replay_panels.py /work/panels /work/replay-<release>.jsonl

REPLAY_EXCLUDE_IDS=<json list> drops those cards' vectors in memory for a trial (see main).

/work/panels holds panel-<n>.json files and a photos/ folder with each case's photo_file.
"""
import dataclasses
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")
from app.config import Settings  # noqa: E402
from app.db import Databases  # noqa: E402
from app.recognition.pipeline import recognize_bytes  # noqa: E402
from app.recognition.runtime import Runtime  # noqa: E402


def ids(items):
    return [getattr(item, "card_id", None) for item in (items or [])]


def main(panel_dir, output):
    panel_dir, output = Path(panel_dir), Path(output)
    settings = Settings(store_captures=False, portfolio_database_url="")
    dbs = Databases(settings)
    snapshot = dbs.cloud_snapshot
    exclude_file = os.environ.get("REPLAY_EXCLUDE_IDS")
    if exclude_file:
        # Trial only: drop these cards' full-card vectors in memory (pair with an artwork bundle
        # built without them) to test them as printing alternatives before building a candidate.
        drop = set(json.loads(Path(exclude_file).read_text()))
        keep = [i for i, cid in enumerate(snapshot.card_ids) if str(cid) not in drop]
        print(json.dumps({"excluded_vectors": len(snapshot.card_ids) - len(keep)}), flush=True)
        segments = list(snapshot.manifest["retrieval_segments"])
        segments[-1] -= len(snapshot.card_ids) - len(keep)  # the trial cards are all in the newest segment
        if segments[-1] == 0:
            segments.pop()
        assert segments and all(i >= len(snapshot.card_ids) - snapshot.manifest["retrieval_segments"][-1]
                                        for i, cid in enumerate(snapshot.card_ids) if str(cid) in drop)
        snapshot = dataclasses.replace(snapshot, embeddings=snapshot.embeddings[keep],
                                       card_ids=snapshot.card_ids[keep], indexed_count=len(keep),
                                       manifest={**snapshot.manifest, "retrieval_segments": segments})
    runtime = Runtime(settings=settings)
    runtime.load(snapshot)
    if not runtime.ready:
        raise SystemExit(f"runtime not ready: {runtime.error}")
    runtime.bind_card_languages(dbs.catalog)
    with output.open("x") as out:
        for panel in sorted(panel_dir.glob("panel-*.json")):
            for case in json.loads(panel.read_text()):
                data = (panel_dir / "photos" / case["photo_file"]).read_bytes()
                assert hashlib.sha256(data).hexdigest() == case["sha256"], case["id"]
                started = time.perf_counter()
                response = recognize_bytes(data, settings=settings, runtime=runtime, catalog=dbs.catalog,
                                           results=None, session_id="replay", persist=False, language="auto",
                                           client_text=None, client_text_reason="absent", graded=None, card_quad=None)
                status = response.status.value if hasattr(response.status, "value") else str(response.status)
                best = getattr(response, "best_match", None)
                printing = getattr(response, "printing_review", None)
                row = {"panel": panel.stem, "id": case["id"], "expected": case.get("expected_card_ids"),
                       "status": status, "best": getattr(best, "card_id", None),
                       "suggestions": ids(getattr(response, "suggestions", None)),
                       "alternatives": ids(getattr(response, "alternatives", None)),
                       "printing": ids(getattr(printing, "plausible_printings", None)) if printing else [],
                       "ms": round((time.perf_counter() - started) * 1000)}
                out.write(json.dumps(row) + "\n")
                out.flush()
                print(json.dumps({k: row[k] for k in ("panel", "id", "status", "best", "ms")}), flush=True)
    dbs.close()


if __name__ == "__main__":
    main(*sys.argv[1:3])
