"""Step 1 bench for Android live card detection (docs/android-live-card-detection-plan-20261026.md).

Runs an OpenCV card finder (Canny, contours, four-corner polygon fit, aspect 0.62-0.82,
area >= 20% of the frame, as in ios/Runner/CardWarp.swift) on the full-size corpus,
scored against the iOS gallery detector's quad (Vision, dumped by vision_reference.swift
and picked with a port of pickGalleryCard's border/size rules). It also runs on frames
without a full card, cut from the corpus photos.

usage: python bench.py --corpus data/photo-corpus-fullsize-20261023 \
           --candidates candidates.json --out results.json [--edge 320]
Photos and per-photo results stay out of git; the write-up quotes counts only.
"""
import argparse
import csv
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

MIN_ASPECT, MAX_ASPECT, MIN_AREA = 0.62, 0.82, 0.20
BORDER_SLACK = 0.02
GALLERY_MIN_AREA = 0.08


# ---------------------------------------------------------------- geometry
def order(pts):
    """Top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=float).reshape(4, 2)
    c = pts.mean(axis=0)
    pts = pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]  # clockwise on screen
    start = int(np.argmin(pts.sum(axis=1)))
    return np.roll(pts, -start, axis=0)


def area(q):
    x, y = q[:, 0], q[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def side_aspect(q, w, h):
    p = q * [w, h]
    a = (np.linalg.norm(p[1] - p[0]) + np.linalg.norm(p[2] - p[3])) / 2
    b = (np.linalg.norm(p[3] - p[0]) + np.linalg.norm(p[2] - p[1])) / 2
    return min(a, b) / max(max(a, b), 1e-9)


def corner_error(a, b, w, h):
    """Mean corner distance as a share of the frame diagonal; best of the four rotations."""
    a, b = a * [w, h], b * [w, h]
    diag = math.hypot(w, h)
    return min(np.linalg.norm(np.roll(a, k, axis=0) - b, axis=1).mean() for k in range(4)) / diag


def iou(a, b, w, h):
    m1 = np.zeros((h, w), np.uint8)
    m2 = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m1, [np.round(a * [w, h]).astype(np.int32)], 1)
    cv2.fillPoly(m2, [np.round(b * [w, h]).astype(np.int32)], 1)
    union = np.logical_or(m1, m2).sum()
    return float(np.logical_and(m1, m2).sum() / union) if union else 0.0


# ---------------------------------------------------------------- reference
def touches_border(q):
    xs, ys = q[:, 0], q[:, 1]
    sides = (xs.min() <= BORDER_SLACK) + (xs.max() >= 1 - BORDER_SLACK) + \
            (ys.min() <= BORDER_SLACK) + (ys.max() >= 1 - BORDER_SLACK)
    return sides >= 2


def pick_reference(cands, w, h):
    """Port of the border/size rules of pickGalleryCard: drop quads that touch two or more
    borders, cover > 95% or < 8% of the photo; the largest (centre-nearest on a tie) wins.
    The slab-label and holder rules are not ported (the largest quad is the holder anyway)."""
    kept = []
    for c in cands:
        q = order(np.array(c[1:9]).reshape(4, 2))
        a = area(q)
        if touches_border(q) or a > 0.95 or a < GALLERY_MIN_AREA:
            continue
        kept.append((a, -np.linalg.norm(q.mean(axis=0) - 0.5), q))
    if not kept:
        return None, "none"
    kept.sort(key=lambda t: (round(t[0] / 0.02), t[1]), reverse=True)
    return kept[0][2], "found"


# ---------------------------------------------------------------- finder
def find_cards(gray, variant="canny"):
    """Card-shaped convex quads in a small grey frame, corners in 0..1, best first."""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edge_maps = []
    if variant == "canny":
        med = float(np.median(blur))
        edge_maps.append(cv2.Canny(blur, int(max(0, 0.66 * med)), int(min(255, 1.33 * med))))
    else:  # "multi": several thresholds, merged, then closed so a broken outline joins up
        em = np.zeros_like(blur)
        for lo, hi in ((20, 60), (40, 120), (80, 200)):
            em = cv2.bitwise_or(em, cv2.Canny(blur, lo, hi))
        edge_maps.append(em)
    out = []
    for edges in edge_maps:
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        if variant != "canny":
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in cnts:
            if cv2.contourArea(cnt) < MIN_AREA * w * h * 0.8:
                continue
            hull = cv2.convexHull(cnt)
            per = cv2.arcLength(hull, True)
            approx = None
            for eps in (0.02, 0.03, 0.04, 0.05):
                ap = cv2.approxPolyDP(hull, eps * per, True)
                if len(ap) == 4:
                    approx = ap
                    break
            if approx is None:
                continue
            q = order(approx.reshape(4, 2) / [w, h])
            if area(q) < MIN_AREA or not cv2.isContourConvex(approx):
                continue
            if not (MIN_ASPECT <= side_aspect(q, w, h) <= MAX_ASPECT):
                continue
            out.append(q)
    out.sort(key=area, reverse=True)
    return out


def shrink(img, edge):
    h, w = img.shape[:2]
    s = edge / max(h, w)
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img


# ---------------------------------------------------------------- negatives
def negatives(img, ref):
    """Frames without a full card, cut from a photo whose card quad is known:
    background strips outside the card, and frames that hold only part of it."""
    h, w = img.shape[:2]
    xs, ys = ref[:, 0] * w, ref[:, 1] * h
    l, r, t, b = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    pad = 8
    out = []
    for name, box in (("bg_left", (0, 0, l - pad, h)), ("bg_right", (r + pad, 0, w, h)),
                      ("bg_top", (0, 0, w, t - pad)), ("bg_bottom", (0, b + pad, w, h))):
        x0, y0, x1, y1 = box
        if (x1 - x0) >= 0.3 * w and (y1 - y0) >= 0.3 * h:
            out.append((name, img[y0:y1, x0:x1]))
    cx, cy = (l + r) // 2, (t + b) // 2
    out.append(("half_card_left", img[:, :cx]))
    out.append(("half_card_top", img[:cy, :]))
    return out


# ---------------------------------------------------------------- main
def pct(v, p):
    return float(np.percentile(v, p)) if len(v) else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--edge", type=int, default=320, help="long edge of the frame the finder sees")
    a = ap.parse_args()
    corpus = Path(a.corpus)
    cands = json.loads(Path(a.candidates).read_text())
    buckets = {r["photo"].split("/")[-1]: r["bucket"] for r in csv.DictReader(open(corpus / "manifest.csv"))}

    report = {"edge": a.edge, "variants": {}}
    for variant in ("canny", "multi"):
        rows, neg_rows, times = [], [], []
        for name in sorted(cands):
            img = cv2.imread(str(corpus / "raw" / name))
            if img is None:
                continue
            h0, w0 = img.shape[:2]
            ref, why = pick_reference(cands[name], w0, h0)
            small = shrink(img, a.edge)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            sh, sw = gray.shape
            t0 = time.perf_counter()
            found = find_cards(gray, variant)
            times.append((time.perf_counter() - t0) * 1000)
            row = {"id": name[:-4], "bucket": buckets.get(name, ""), "has_ref": ref is not None,
                   "found": bool(found), "err": None, "iou": None}
            if found and ref is not None:
                # best candidate against the reference (the live app picks by its own rules)
                errs = [corner_error(f, ref, sw, sh) for f in found]
                row["err_first"] = errs[0]
                row["err"] = min(errs)
                row["iou"] = iou(found[int(np.argmin(errs))], ref, sw, sh)
                row["iou_first"] = iou(found[0], ref, sw, sh)
            rows.append(row)
            if ref is not None:
                for kind, crop in negatives(img, ref):
                    g = cv2.cvtColor(shrink(crop, a.edge), cv2.COLOR_BGR2GRAY)
                    n = find_cards(g, variant)
                    neg_rows.append({"id": name[:-4], "kind": kind, "false": bool(n)})
        report["variants"][variant] = summarise(rows, neg_rows, times)
        report["variants"][variant]["rows"] = rows
        report["variants"][variant]["neg_rows"] = neg_rows
    Path(a.out).write_text(json.dumps(report, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    report = json.loads(Path(a.out).read_text())
    for v, s in report["variants"].items():
        print(v, json.dumps({k: x for k, x in s.items() if k not in ("rows", "neg_rows")}, indent=1))


def summarise(rows, neg_rows, times):
    ref = [r for r in rows if r["has_ref"]]
    noref = [r for r in rows if not r["has_ref"]]
    err = [r["err"] for r in ref if r["err"] is not None]
    err1 = [r["err_first"] for r in ref if r["err"] is not None]
    kinds = {}
    for n in neg_rows:
        k = kinds.setdefault(n["kind"], [0, 0])
        k[0] += 1
        k[1] += n["false"]
    by_bucket = {}
    for r in rows:
        b = by_bucket.setdefault(r["bucket"], [0, 0, 0, 0])
        b[0] += 1
        b[1] += r["found"]
        b[2] += r["has_ref"]
        b[3] += r["found"] and r["has_ref"]
    return {
        "photos": len(rows),
        "with_reference": len(ref),
        "no_reference": len(noref),
        "find_rate_all": sum(r["found"] for r in rows) / len(rows),
        "found_all": sum(r["found"] for r in rows),
        "find_rate_reference_subset": sum(r["found"] for r in ref) / max(len(ref), 1),
        "found_reference_subset": sum(r["found"] for r in ref),
        "found_no_reference_subset": sum(r["found"] for r in noref),
        "correct_within_2pct": sum(e <= 0.02 for e in err) , "correct_within_5pct": sum(e <= 0.05 for e in err),
        "correct_first_within_5pct": sum(e <= 0.05 for e in err1),
        "err_best_median": pct(err, 50), "err_best_p90": pct(err, 90),
        "err_first_median": pct(err1, 50), "err_first_p90": pct(err1, 90),
        "negatives": {k: {"frames": v[0], "false_outlines": v[1]} for k, v in kinds.items()},
        "negatives_total": [len(neg_rows), sum(n["false"] for n in neg_rows)],
        "finder_ms_median": pct(times, 50), "finder_ms_p90": pct(times, 90),
        "by_bucket_[n,found,ref,found_and_ref]": by_bucket,
    }


if __name__ == "__main__":
    main()
