"""Score one candidate replay of the three stored panels against the last accepted run.

    python3 -I score_gate.py PANEL_WORK_DIR BASELINE_DIR CANDIDATE_DIR OUT_DIR [BASELINE_PREFIX CANDIDATE_PREFIX [LABELS_DIR]]

PANEL_WORK_DIR is `data/catalogue-gaps/proof-panel-20261109/work`: its `shards/` and `shards2/`
folders hold the panel files that were replayed (the same shard layout as the step-1 gate).
Results files are `results-<prefix>-<name>.jsonl`, one JSON line per photo (replay_panels.py).

LABELS_DIR (optional) holds panel-dev.json, panel-dev2.json, panel-dev3.json with the current labels;
a case found there takes its expected cards from that file (15 dev3 labels were corrected after the
shards were cut). Without it the shard files' labels are used.

Panels: dev = shards dev0, dev1, dev2, devr8 (681); dev2 = shards2 d0, d1 (238);
dev3 = shards s5-0..s5-4 (972). A case is `right_first` when the first answer is an expected card,
`wrong_first` when it names a card and no expected card is offered anywhere.

Writes gate.json (per panel and cell, before -> after, Wilson upper bound of wrong first) and
changed-answers.json (every photo whose answer differs in any field). The gate passes when no
right-first answer became not-right-first, no expected card stopped being offered, no cell is
lower and every upper bound is under 3%. Changed answers are then judged by hand against the
table in section 4 of the plan: this script never marks one accepted.
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

PANELS = {
    "dev": [("shards", "dev0", "dev0"), ("shards", "dev1", "dev1"), ("shards", "dev2", "dev2"),
            ("shards", "devr8", "dev8")],
    "dev2": [("shards2", "d0", "dev20"), ("shards2", "d1", "dev21")],
    "dev3": [("shards", f"s5-{i}", f"dev3{i}") for i in range(5)],
}
SIZES = {"dev": 681, "dev2": 238, "dev3": 972}
FIELDS = ("status", "best", "suggestions", "alternatives", "printing")


def canonical(card_id):
    return "en:" + card_id if card_id and ":" not in card_id else card_id


def load_cases(work, folder, shard):
    out = {}
    for path in (Path(work) / folder / shard).glob("panel-*.json"):
        data = json.loads(path.read_text())
        for case in data.get("cases", data) if isinstance(data, dict) else data:
            out[case["id"]] = case
    return out


def load_results(directory, prefix, name):
    if name in ("dev20", "dev21"):  # the dev2 panel files carry a d2 marker: results-d2s1-dev20, results-d2dev20
        path = Path(directory) / (f"results-d2{prefix}-{name}.jsonl" if prefix else f"results-d2{name}.jsonl")
    else:
        path = Path(directory) / (f"results-{prefix}-{name}.jsonl" if prefix else f"results-{name}.jsonl")
    rows = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        rows[row["id"]] = row
    return rows


def outcome(row, expected):
    top = canonical(row["best"] or (row["suggestions"] or [None])[0])
    offered = {canonical(v) for v in [row["best"]] + row["suggestions"] + row["alternatives"] + row["printing"] if v}
    return {"right_first": top in expected,
            "wrong_first": bool(top and not offered & expected),
            "right_offered": bool(offered & expected)}


def upper_bound(wrong, total):
    z = 1.959963984540054
    p = wrong / total
    return (p + z * z / (2 * total) + z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / (1 + z * z / total)


def main(work, baseline_dir, candidate_dir, out_dir, base_prefix="s1", cand_prefix=None, labels_dir=None):
    cand_prefix = cand_prefix or ""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report, changes, regressions, lost, lower = {}, [], [], [], []
    for panel, shards in PANELS.items():
        totals = {s: defaultdict(int) for s in ("before", "after")}
        cells = defaultdict(lambda: {"before": defaultdict(int), "after": defaultdict(int)})
        seen = 0
        current = {}
        if labels_dir:
            current = {c["id"]: c for c in json.loads((Path(labels_dir) / f"panel-{panel}.json").read_text())}
        for folder, shard, result_name in shards:
            cases = load_cases(work, folder, shard)
            before = load_results(baseline_dir, base_prefix, result_name)
            cand_name = result_name
            after = load_results(candidate_dir, cand_prefix, cand_name) if cand_prefix else \
                load_results(candidate_dir, "", cand_name)
            if set(before) != set(cases) or set(after) != set(cases):
                raise SystemExit(f"coverage differs in {folder}/{shard}: {len(cases)} cases, "
                                 f"{len(before)} before, {len(after)} after")
            for cid, case in cases.items():
                expected = {canonical(v) for v in current.get(cid, case)["expected_card_ids"]}
                a, b = outcome(before[cid], expected), outcome(after[cid], expected)
                cell = f"{case['stratum']}:{case['language']}"
                for side, res in (("before", a), ("after", b)):
                    totals[side]["photos"] += 1
                    cells[cell][side]["photos"] += 1
                    for key, value in res.items():
                        totals[side][key] += int(value)
                        cells[cell][side][key] += int(value)
                if a["right_offered"] and not b["right_offered"]:
                    lost.append(cid)
                if a["right_first"] and not b["right_first"]:
                    regressions.append(cid)
                if any(before[cid][k] != after[cid][k] for k in FIELDS):
                    changes.append({"id": cid, "panel": panel, "expected": sorted(expected),
                                    "before": {k: before[cid][k] for k in FIELDS},
                                    "after": {k: after[cid][k] for k in FIELDS},
                                    "before_score": a, "after_score": b})
                seen += 1
        if seen != SIZES[panel]:
            raise SystemExit(f"panel {panel} has {seen} photos, expected {SIZES[panel]}")
        for cell, v in cells.items():
            if v["after"]["right_first"] < v["before"]["right_first"] or v["after"]["wrong_first"] > v["before"]["wrong_first"]:
                lower.append(f"{panel}:{cell}")
        report[panel] = {"photos": seen,
                         "right_first": [totals["before"]["right_first"], totals["after"]["right_first"]],
                         "wrong_first": [totals["before"]["wrong_first"], totals["after"]["wrong_first"]],
                         "right_offered": [totals["before"]["right_offered"], totals["after"]["right_offered"]],
                         "wrong_first_upper_bound": round(upper_bound(totals["after"]["wrong_first"], seen), 4)}
    result = {"panels": report, "right_first_regressions": regressions, "right_no_longer_offered": lost,
              "cells_lower": lower, "changed_answers": len(changes),
              "numerical_gates_pass": not (regressions or lost or lower)
              and all(p["wrong_first_upper_bound"] < 0.03 for p in report.values())}
    (out / "gate.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "changed-answers.json").write_text(json.dumps(changes, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:8])
