"""Step 1 of the older-era ranking plan: can the SIFT verifier pick the right artwork family?

Runs like replay_panels.py (served API image, one catalogue release, persist=False). For each
photo it runs the real recognize_bytes once, keeping the final frame, the full-card query
vector and the retrieval mask the pipeline used, then offline:

1. retrieves deeper: full card k=FULL_K (100), artwork stream k=ART_K (50), same mask;
2. collapses candidates into artwork families (pad cosine >= TWIN between full-card vectors),
   best-scoring member first, and keeps the top FAMILIES (24);
3. runs runtime.artwork_verifier.verify over one reference per family with limit=FAMILIES;
4. records the expected card's raw ranks, its family's rank, every verified family's
   artwork_inliers, and whether the expected family leads by inliers with a margin.

    python3 verify_families.py /work/panels /work/families-<release>.jsonl

Nothing in the pipeline changes; the wrappers only record arguments.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/app")
import app.recognition.orientation as orientation  # noqa: E402
import app.recognition.pipeline as pipeline  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Databases  # noqa: E402
from app.recognition.embed import top_k  # noqa: E402
from app.recognition.runtime import Runtime  # noqa: E402

FULL_K, ART_K, FAMILIES, TWIN = 100, 50, 24, 0.95
MARGIN, MIN_INLIERS = 1.5, 12


def main(panel_dir, output):
    panel_dir, output = Path(panel_dir), Path(output)
    settings = Settings(store_captures=False, portfolio_database_url="")
    dbs = Databases(settings)
    runtime = Runtime(settings=settings)
    runtime.load(dbs.cloud_snapshot)
    if not runtime.ready:
        raise SystemExit(f"runtime not ready: {runtime.error}")
    runtime.bind_card_languages(dbs.catalog)
    snapshot = runtime.snapshot
    position = {str(cid): i for i, cid in enumerate(snapshot.card_ids)}
    verifier, art_index = runtime.artwork_verifier, runtime.artwork_index

    seen = {}
    real_top_k = pipeline.top_k

    def recording_top_k(embeddings, query, k=20, keep=None, segments=None):
        if k == 20:
            seen["query"], seen["keep"], seen["segments"] = np.array(query), keep, segments
        return real_top_k(embeddings, query, k=k, keep=keep, segments=segments)
    pipeline.top_k = orientation.top_k = recording_top_k
    real_search = art_index.search

    def recording_search(image, embedder, **kw):
        seen["image"], seen["search_kw"] = image, kw
        return real_search(image, embedder, **kw)
    art_index.search = recording_search

    def image_path(card_id):
        row = dbs.catalog.execute("SELECT image_path FROM cards WHERE id=?", (card_id,)).fetchone()
        return str(row["image_path"] or "") if row else ""

    with output.open("x") as out:
        for panel in sorted(panel_dir.glob("panel-*.json")):
            for case in json.loads(panel.read_text()):
                data = (panel_dir / "photos" / case["photo_file"]).read_bytes()
                assert hashlib.sha256(data).hexdigest() == case["sha256"], case["id"]
                seen.clear()
                response = pipeline.recognize_bytes(
                    data, settings=settings, runtime=runtime, catalog=dbs.catalog, results=None,
                    session_id="replay", persist=False, language="auto", client_text=None,
                    client_text_reason="absent", graded=None, card_quad=None)
                status = response.status.value if hasattr(response.status, "value") else str(response.status)
                best = getattr(getattr(response, "best_match", None), "card_id", None)
                expected = set(case.get("expected_card_ids") or [])
                row = {"panel": panel.stem, "id": case["id"], "expected": sorted(expected),
                       "status": status, "best": best}
                if "query" not in seen or "image" not in seen:
                    row["skipped"] = "no retrieval recorded: " + ",".join(sorted(seen)) or "nothing"
                    out.write(json.dumps(row) + "\n"); out.flush()
                    print(json.dumps(row), flush=True)
                    continue
                idx, scores = top_k(snapshot.embeddings, seen["query"], k=FULL_K, keep=seen["keep"],
                                    segments=seen["segments"])
                full = [(str(snapshot.card_ids[i]), float(s)) for i, s in zip(idx, scores)]
                kw = {**seen["search_kw"], "k": ART_K}
                hits, _ = real_search(seen["image"], runtime.require()[1], **kw)
                art = [(h.card_id, float(h.score)) for h in hits]
                merged = {}
                for cid, s in full + art:
                    merged[cid] = max(s, merged.get(cid, -1.0))
                order = sorted(merged.items(), key=lambda x: -x[1])
                families = []  # [representative id, member ids, best score]
                for cid, s in order:
                    vec = snapshot.embeddings[position[cid]] if cid in position else None
                    home = None
                    if vec is not None:
                        for fam in families:
                            rep = fam[0]
                            if rep in position and float(snapshot.embeddings[position[rep]] @ vec) >= TWIN:
                                home = fam
                                break
                    if home is None:
                        families.append([cid, [cid], s])
                    else:
                        home[1].append(cid)
                top = families[:FAMILIES]
                refs = [(fam[0], image_path(fam[0])) for fam in top]
                started = time.perf_counter()
                matches = verifier.verify(seen["image"], refs, limit=FAMILIES)
                verify_ms = round((time.perf_counter() - started) * 1000)
                inliers = {m.card_id: m.artwork_inliers for m in matches}
                ranked = sorted(((inliers.get(f[0], 0), i) for i, f in enumerate(top)), reverse=True)

                def rank_of(items):
                    return next((i + 1 for i, (cid, _) in enumerate(items) if cid in expected), None)
                exp_family = next((i for i, f in enumerate(families) if expected & set(f[1])), None)
                lead_n, lead_i = ranked[0] if ranked else (0, None)
                second_n = ranked[1][0] if len(ranked) > 1 else 0
                decisive = lead_n >= MIN_INLIERS and lead_n >= MARGIN * max(second_n, 1)
                row.update({
                    "full_rank": rank_of(full), "art_rank": rank_of(art), "merged_rank": rank_of(order),
                    "families": len(families), "expected_family_rank": None if exp_family is None else exp_family + 1,
                    "expected_family_inliers": inliers.get(top[exp_family][0], 0) if exp_family is not None and exp_family < FAMILIES else None,
                    "leader_family": None if lead_i is None or not lead_n else top[lead_i][1][:6],
                    "leader_inliers": lead_n, "runner_up_inliers": second_n, "decisive": decisive,
                    "leader_is_expected": bool(lead_n and exp_family == lead_i),
                    "verified": [[top[i][0], n, len(top[i][1])] for n, i in ranked if n][:8],
                    "verify_ms": verify_ms})
                out.write(json.dumps(row) + "\n"); out.flush()
                print(json.dumps({k: row.get(k) for k in ("id", "status", "best", "full_rank", "expected_family_rank",
                                                           "leader_inliers", "runner_up_inliers", "leader_is_expected",
                                                           "decisive", "verify_ms")}), flush=True)
    dbs.close()


if __name__ == "__main__":
    main(*sys.argv[1:3])
