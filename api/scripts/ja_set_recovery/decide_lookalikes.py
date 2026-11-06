"""Decide which new recovery cards keep scan vectors (handoff 4.9 rule). Offline.

    python3 decide_lookalikes.py RUN_DIR SERVED_PAD_DIR

Pad cosine >= 0.95 links a new card to another new card or to an indexed Japanese card
(Japanese/English twins are not grouped). In a group that holds an indexed card, every new
member becomes a printing alternative (features, no vectors). Otherwise the earliest
printing keeps vectors and the others become alternatives. "Earliest" is the set's position
in the TCG Collector Japanese list (registry `line`, newest first), so a larger line is older.

SERVED_PAD_DIR holds embeddings.npy + embedding_card_ids.npy of the index being served.
Writes RUN_DIR/index-decision.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

T = 0.95


def main(run_dir, served_dir):
    run = Path(run_dir)
    served = Path(served_dir)
    registry = {g["group_id"]: g for g in json.loads((run / "set-registry.json").read_text())}
    cards = {c["id"]: c for c in json.loads((run / "cards.json").read_text())}
    ids = np.load(run / "vectors/embedding-card-ids.npy").astype(str)
    pad = np.load(run / "vectors/pad-embeddings.npy")
    base = np.load(served / "embeddings.npy")
    bids = np.load(served / "embedding_card_ids.npy").astype(str)
    ja = np.char.startswith(bids, "ja:")
    base, bids = base[ja], bids[ja]

    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    edges, nearest_existing = [], {}
    for start in range(0, len(ids), 1000):
        block = pad[start:start + 1000]
        to_old = block @ base.T
        to_new = block @ pad.T
        for k in range(len(block)):
            i = start + k
            cid = str(ids[i])
            find(cid)
            j = int(to_old[k].argmax())
            nearest_existing[cid] = [str(bids[j]), round(float(to_old[k, j]), 4)]
            for j in np.flatnonzero(to_old[k] >= T):
                parent[find(cid)] = find(str(bids[j]))
                edges.append([cid, str(bids[j]), round(float(to_old[k, j]), 4)])
            for j in np.flatnonzero(to_new[k] >= T):
                if j > i:
                    parent[find(cid)] = find(str(ids[j]))
                    edges.append([cid, str(ids[j]), round(float(to_new[k, j]), 4)])

    new = set(ids.tolist())
    groups = {}
    for cid in list(parent):
        groups.setdefault(find(cid), []).append(cid)

    def age(cid):
        card = cards[cid]
        return (-registry[card["group_id"]]["line"], cid)

    alternatives, group_rows = {}, []
    for members in groups.values():
        if len(members) < 2:
            continue
        old = sorted(m for m in members if m not in new)
        fresh = sorted(m for m in members if m in new)
        keep = None if old else min(fresh, key=age)
        for cid in fresh:
            if cid != keep:
                alternatives[cid] = old[0] if old else keep
        group_rows.append({"members": sorted(members), "existing": old, "vectors_kept_on": keep})

    scannable = sorted(c for c in new if c not in alternatives)
    decision = {
        "threshold": T, "served_index": str(served), "served_japanese_vectors": int(len(bids)),
        "new_cards": len(new), "scannable": len(scannable), "printing_alternatives": len(alternatives),
        "alternatives_with_existing_twin": sum(1 for v in alternatives.values() if v not in new),
        "scannable_ids": scannable,
        "alternative_of": dict(sorted(alternatives.items())),
        "groups": group_rows, "edges": edges, "nearest_existing": nearest_existing,
    }
    (run / "index-decision.json").write_text(json.dumps(decision, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: decision[k] for k in ("new_cards", "scannable", "printing_alternatives",
                                               "alternatives_with_existing_twin")}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
