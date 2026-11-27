"""replay_panels.py for several shards with one catalogue load.

    python3 replay_lane.py OUT_DIR SHARD_DIR=NAME [SHARD_DIR=NAME ...]

Loads the cloud snapshot and the runtime once (as replay_panels.main does, without the trial
exclusion), then replays each shard into OUT_DIR/results-NAME.jsonl in replay_panels' row format.
The database is only read at start-up, so a short-lived read role covers the whole lane.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/work")
import replay_panels  # noqa: E402
from replay_panels import Databases, Runtime, Settings, hashlib, ids, recognize_bytes, time  # noqa: E402


def main(out_dir, *specs):
    out_dir = Path(out_dir)
    settings = Settings(store_captures=False, portfolio_database_url="")
    dbs = Databases(settings)
    runtime = Runtime(settings=settings)
    runtime.load(dbs.cloud_snapshot)
    if not runtime.ready:
        raise SystemExit(f"runtime not ready: {runtime.error}")
    runtime.bind_card_languages(dbs.catalog)
    print(json.dumps({"loaded": True}), flush=True)
    for spec in specs:
        shard, name = spec.split("=", 1)
        panel_dir = Path(shard)
        with (out_dir / f"results-{name}.jsonl").open("x") as out:
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
        print(json.dumps({"shard": name, "done": True}), flush=True)
    dbs.close()


if __name__ == "__main__":
    assert replay_panels.main  # the module is the reference implementation
    main(*sys.argv[1:])
