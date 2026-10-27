"""On-phone index check (plan 2026-10-27, step 0).

Does a compressed copy of the server's card fingerprint index reach the same stage 1
vector decision as the float32 index?

Queries (vectors come from the server's DINOv2-small, ``DinoEmbedder.embed(crop, 'pad')``):

* ``android``: the stored Android manual uploads whose card the owner's list names. The crop is the
  98% centre crop of the upload (``stage1_bench/run_bench.whole_card``), the whole-card outline.
* ``panel``: the frozen 157-photo A55 panel. The crop is the phone's gallery quad, warped as in
  ``api/scripts/android_fastpath_replay.py`` (``server_quad_vectors``). Photos without a gallery
  quad have no crop and are skipped. The label is the panel's expected card.

Rule under test: the vector part of ``stage1_gate.decide`` (answer / twin / too_close /
contradiction / no_agree), with the text assumed to name the labelled card. This is an upper
bound on the text and covers the vector side only: the artwork check, printing groups, number
repair and the set-total rules are not run.

Variants: float32 (reference); int8 (per-dimension symmetric scale, int32 dot product, rescaled);
int8 search with the top 50 re-scored at float32 (the text card's float32 score is also taken);
float16.

Wrong passes: for each query the text is also set to each of the float32 top-5 other cards (a
wrong printing the phone could read). A new wrong pass is a variant that answers that wrong card
while float32 does not.

Photos and the index stay outside git. Only aggregate counts go to stdout; per-query records go
to ``--out`` (keep that outside the repository).

    api/.venv/bin/python api/scripts/on_phone_index/check_compressed_index.py \\
        --data-root <scanapp>/data --android-dir <copy of the Android uploads> \\
        --work <scratch dir> --out <scratch>/results.json
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import time

for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(_key, '1')

import numpy as np  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
sys.path.insert(0, str(API / 'scripts'))
sys.path.insert(0, str(API / 'scripts' / 'stage1_bench'))

from app.recognition.embed import DinoEmbedder  # noqa: E402
from app.recognition.stage1_gate import (  # noqa: E402
    CONTRADICTION, STAGE1_MARGIN, TWIN_COSINE, _pair_margin, _top, same_card)
import android_fastpath_replay as fp  # noqa: E402
import run_bench as rb  # noqa: E402

CHUNK = 8192
RESCORE_K = 50
RANK_POOL = 60
VARIANTS = ('float32', 'int8', 'int8_top50_f32', 'float16')
ANSWERED = ('answer', 'twin')
EMB_REL = 'data/android-embedding-research-20261023'


def canon(card_id: str) -> str:
    return card_id.removeprefix('en:')


def text_row_of(name: str | None, pos: dict[str, int]) -> str | None:
    if not name:
        return None
    for candidate in (name, canon(name), 'en:' + canon(name)):
        if candidate in pos:
            return candidate
    return None


def load_index(index_dir: Path, catalog: Path):
    ids = np.load(index_dir / 'embedding_card_ids.npy', allow_pickle=False).astype(str).tolist()
    emb = np.asarray(np.load(index_dir / 'embeddings.npy'), dtype=np.float32)
    emb /= np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-8, None)
    con = sqlite3.connect(f'file:{catalog}?mode=ro', uri=True)
    lang = {row[0]: row[1] for row in con.execute('SELECT id, language FROM cards')}
    con.close()
    pos: dict[str, int] = {}
    for row, card_id in enumerate(ids):
        pos.setdefault(card_id, row)
    return ids, emb, pos, lang


def quantize(emb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-dimension symmetric int8: emb[i, d] ~= q8[i, d] * scale[d]."""
    scale = np.abs(emb).max(axis=0) / 127.0
    scale = np.where(scale > 0, scale, 1.0).astype(np.float32)
    q8 = np.clip(np.rint(emb / scale), -127, 127).astype(np.int8)
    return q8, scale


def scores_float32(emb: np.ndarray, q: np.ndarray) -> np.ndarray:
    return emb @ q


def scores_int8(q8: np.ndarray, scale: np.ndarray, q: np.ndarray) -> np.ndarray:
    # emb . q ~= sum_d q8[i, d] * (scale[d] * q[d]); the query part is quantised once per search.
    qs = q * scale
    sq = float(np.abs(qs).max()) / 127.0
    qq = np.clip(np.rint(qs / sq), -127, 127).astype(np.int32)
    out = np.empty(q8.shape[0], dtype=np.float32)
    for start in range(0, q8.shape[0], CHUNK):
        block = q8[start:start + CHUNK].astype(np.int32) @ qq  # int32 accumulation, |sum| < 2^31
        out[start:start + CHUNK] = block.astype(np.float32) * np.float32(sq)
    return out


def scores_float16(emb16: np.ndarray, q: np.ndarray) -> np.ndarray:
    out = np.empty(emb16.shape[0], dtype=np.float32)
    for start in range(0, emb16.shape[0], CHUNK):
        out[start:start + CHUNK] = emb16[start:start + CHUNK].astype(np.float32) @ q
    return out


def scores_int8_top50(emb: np.ndarray, q8: np.ndarray, scale: np.ndarray, q: np.ndarray,
                      extra_rows: list[int]) -> np.ndarray:
    approx = scores_int8(q8, scale, q)
    cand = np.argpartition(-approx, RESCORE_K)[:RESCORE_K]
    rows = np.unique(np.concatenate([cand, np.asarray(extra_rows, dtype=np.int64)]))
    out = np.full(emb.shape[0], -2.0, dtype=np.float32)
    out[rows] = emb[rows] @ q
    return out


def distinct_top(scores: np.ndarray, ids: list[str], k: int) -> list[int]:
    """Rows of the best k distinct cards (printings with the same canonical id collapse)."""
    order = np.argpartition(-scores, RANK_POOL)[:RANK_POOL]
    order = order[np.argsort(-scores[order])]
    seen: set[str] = set()
    rows: list[int] = []
    for row in order:
        card = canon(ids[int(row)])
        if card in seen:
            continue
        seen.add(card)
        rows.append(int(row))
        if len(rows) == k:
            break
    return rows


def decide(scores, ids, emb, pos, lang, label, text_row):
    """The vector part of stage1_gate.decide (stage1b off). Returns (category, card, margin)."""
    top, top_score, margin = _top(scores, ids)
    if same_card(top, label):
        return ('answer' if margin >= STAGE1_MARGIN else 'too_close'), top, margin
    if text_row is None:
        return 'no_agree', None, margin
    top_row, text_pos = pos[top], pos[text_row]
    cosine = float(emb[top_row] @ emb[text_pos])
    lt, lx = lang.get(top), lang.get(text_row)
    if cosine >= TWIN_COSINE and lt is not None and lx is not None and lt != lx:
        if _pair_margin(scores, ids, top, text_row, top_score) >= STAGE1_MARGIN:
            return 'twin', text_row, margin
        return 'too_close', None, margin
    if top_score - float(scores[text_pos]) >= CONTRADICTION:
        return 'contradiction', None, margin
    return 'no_agree', None, margin


def android_queries(root: Path, embedder: DinoEmbedder, work: Path) -> list[dict]:
    cache = work / 'android-query-vectors.npz'
    cases = json.loads((root / 'android_cases.json').read_text())
    labelled = []
    for case in cases:
        name = (case.get('ocr_name') or case.get('top_name') or '').strip().lower()
        label = rb.OWNER.get(name) or rb.OWNER.get((case.get('top_name') or '').strip().lower())
        if label:
            labelled.append((case, label))
    if cache.exists():
        data = np.load(cache, allow_pickle=False)
        vectors = dict(zip(data['scans'].tolist(), data['vectors']))
    else:
        vectors = {}
        for case, _ in labelled:
            with Image.open(root / case['input']) as raw:
                photo = ImageOps.exif_transpose(raw).convert('RGB')
            vectors[case['scan']] = np.asarray(embedder.embed(rb.whole_card(photo), 'pad'), dtype=np.float32)
        np.savez(cache, scans=np.array(list(vectors)), vectors=np.stack(list(vectors.values())))
    return [{'set': 'android', 'id': case['scan'], 'label': label, 'vector': vectors[case['scan']]}
            for case, label in labelled]


def panel_queries(panel_root: Path, data_root: Path, model: Path, work: Path) -> list[dict]:
    parity = data_root / 'data/latency/android-recognition-parity-20261023'
    manifest = json.loads((parity / 'frozen-panel/manifest.json').read_text())['photos']
    per_photo = {row['id']: row for row in json.loads((parity / 'a55-fresh157-per-photo.json').read_text())['panel']}
    comparison = {row['id']: row for row in json.loads((parity / 'a55-per-photo-comparison.json').read_text())['rows']}
    rows = []
    for photo in manifest:
        flat = comparison[photo['id']]['android_gallery_quad'] if per_photo[photo['id']]['quad_sent'] else None
        if not flat or not photo['expected_card_ids']:
            continue
        rows.append({'id': photo['id'], 'file': photo['photo_file'], 'label': photo['expected_card_ids'][0],
                     'quad': ','.join(f'{v:.5f}' for v in flat), 'live': {'embedding_sent': True}})
    # The replay's own crop (f16 vectors, as the phone sends them), cached in the scratch folder.
    encoded = fp.server_quad_vectors(rows, panel_root / 'panel', model, work / 'panel-quad-vectors.json')
    out = []
    for row in rows:
        if row['id'] not in encoded:
            continue
        vector = np.frombuffer(base64.b64decode(encoded[row['id']]), dtype='<f2').astype(np.float32)
        out.append({'set': 'panel', 'id': row['id'], 'label': row['label'],
                    'vector': vector / max(float(np.linalg.norm(vector)), 1e-8)})
    return out


def evaluate(queries, ids, emb, pos, lang, emb16, q8, scale, timings):
    records = []
    for query in queries:
        q, label = query['vector'], query['label']
        label_row = text_row_of(label, pos)
        started = time.perf_counter()
        s32 = scores_float32(emb, q)
        timings['float32'].append(time.perf_counter() - started)
        adversarial_rows = []
        for row in distinct_top(s32, ids, 6):
            if len(adversarial_rows) == 5:
                break
            if not same_card(ids[row], label):
                adversarial_rows.append(row)
        extra = ([pos[label_row]] if label_row else []) + [pos[ids[row]] for row in adversarial_rows]
        started = time.perf_counter()
        s8 = scores_int8(q8, scale, q)
        timings['int8'].append(time.perf_counter() - started)
        started = time.perf_counter()
        s50 = scores_int8_top50(emb, q8, scale, q, extra)
        timings['int8_top50_f32'].append(time.perf_counter() - started)
        started = time.perf_counter()
        s16 = scores_float16(emb16, q)
        timings['float16'].append(time.perf_counter() - started)

        per_variant = {}
        for name, scores in (('float32', s32), ('int8', s8), ('int8_top50_f32', s50), ('float16', s16)):
            top_rows = distinct_top(scores, ids, 5)
            _, _, margin = _top(scores, ids)
            cat, answer, _ = decide(scores, ids, emb, pos, lang, label, label_row)
            adv = []
            for row in adversarial_rows:
                tcat, _, _ = decide(scores, ids, emb, pos, lang, label, ids[row])
                adv.append({'text': canon(ids[row]), 'cat': tcat, 'answered': tcat in ANSWERED})
            per_variant[name] = {
                'top1': canon(ids[top_rows[0]]), 'margin': float(margin),
                'top5': [canon(ids[r]) for r in top_rows],
                'cat': cat, 'answer': None if answer is None else canon(answer),
                'answered_wrong': cat in ANSWERED and not same_card(answer, label),
                'adv': adv,
            }
        records.append({'set': query['set'], 'id': query['id'], 'label': label,
                        'label_in_index': label_row is not None, 'variants': per_variant})
    return records


def summarise(records: list[dict], sizes: dict[str, int], timings: dict[str, list[float]], subset: str) -> dict:
    rows = [r for r in records if subset == 'all' or r['set'] == subset]
    out = {'queries': len(rows), 'label_missing_from_index': sum(not r['label_in_index'] for r in rows),
           'variants': {}}
    ref = [r['variants']['float32'] for r in rows]
    for name in VARIANTS:
        decisions = [r['variants'][name] for r in rows]
        agree = sum(d['cat'] == f['cat'] for d, f in zip(decisions, ref))
        answered_agree = sum((d['cat'] in ANSWERED) == (f['cat'] in ANSWERED) for d, f in zip(decisions, ref))
        top1 = sum(d['top1'] == f['top1'] for d, f in zip(decisions, ref))
        overlap = [len(set(d['top5']) & set(f['top5'])) / 5 for d, f in zip(decisions, ref)]
        dmargin = [abs(d['margin'] - f['margin']) for d, f in zip(decisions, ref)]
        adv_pairs = adv_agree = new_wrong = f32_wrong = 0
        for d, f in zip(decisions, ref):
            for dv, fv in zip(d['adv'], f['adv']):
                adv_pairs += 1
                adv_agree += dv['cat'] == fv['cat']
                new_wrong += dv['answered'] and not fv['answered']
                f32_wrong += fv['answered']
        times = timings[name]
        out['variants'][name] = {
            'decision_agree': agree,
            'decision_agree_pct': round(100 * agree / len(rows), 2) if rows else None,
            'answered_agree': answered_agree,
            'top1_agree': top1,
            'top1_agree_pct': round(100 * top1 / len(rows), 2) if rows else None,
            'top5_overlap_mean_pct': round(100 * statistics.mean(overlap), 2) if overlap else None,
            'margin_change_median': round(statistics.median(dmargin), 5) if dmargin else None,
            'margin_change_max': round(max(dmargin), 5) if dmargin else None,
            'categories': dict(Counter(d['cat'] for d in decisions)),
            'primary_wrong_answers': sum(d['answered_wrong'] for d in decisions),
            'adversarial_pairs': adv_pairs,
            'adversarial_decision_agree': adv_agree,
            'new_wrong_passes': new_wrong,
            'float32_wrong_passes_reference': f32_wrong,
            'size_bytes': sizes.get(name),
            'search_ms_median': round(1000 * statistics.median(times), 2) if times else None,
            'search_ms_p90': round(1000 * sorted(times)[int(0.9 * (len(times) - 1))], 2) if times else None,
        }
    return out


def gate(summary: dict) -> dict:
    result = {}
    for name in ('int8', 'int8_top50_f32', 'float16'):
        v = summary['all']['variants'][name]
        result[name] = bool(v['decision_agree_pct'] is not None and v['decision_agree_pct'] >= 99.0
                            and v['new_wrong_passes'] == 0)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-root', type=Path, required=True, help='the scanapp data folder (read only)')
    parser.add_argument('--android-dir', type=Path, required=True,
                        help='folder with android_cases.json and images/ (the stored Android uploads, copied read only)')
    parser.add_argument('--work', type=Path, required=True, help='scratch folder for caches and index copies (not in git)')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)

    root = args.data_root
    index_dir = root / EMB_REL / 'catalogue/vectors/pad'
    catalog = root / EMB_REL / 'catalogue/catalog.sqlite'
    model = root / EMB_REL / 'teacher/dinov2_small.onnx'
    manifest = json.loads((index_dir / 'manifest.json').read_text())
    if hashlib.sha256(model.read_bytes()).hexdigest() != manifest['dinov2_sha256']:
        raise SystemExit('model checksum does not match the index manifest')

    ids, emb, pos, lang = load_index(index_dir, catalog)
    print(f'index rows {len(ids)} x {emb.shape[1]}; model checksum matches the manifest')
    q8, scale = quantize(emb)
    emb16 = emb.astype(np.float16)
    np.save(args.work / 'index_int8.npy', q8)
    np.save(args.work / 'index_scale.npy', scale)
    np.save(args.work / 'index_float16.npy', emb16)
    int8_bytes = (args.work / 'index_int8.npy').stat().st_size + (args.work / 'index_scale.npy').stat().st_size
    float32_bytes = (index_dir / 'embeddings.npy').stat().st_size
    sizes = {'float32': float32_bytes, 'int8': int8_bytes,
             'int8_top50_f32': int8_bytes + float32_bytes,
             'float16': (args.work / 'index_float16.npy').stat().st_size}

    embedder = DinoEmbedder(str(model), 1, 1)
    queries = android_queries(args.android_dir, embedder, args.work)
    queries += panel_queries(root / 'data/latency/stage0-simulation-20261021', root, model, args.work)
    print(f'queries: {sum(q["set"] == "android" for q in queries)} android, '
          f'{sum(q["set"] == "panel" for q in queries)} panel')

    timings = {name: [] for name in VARIANTS}
    records = evaluate(queries, ids, emb, pos, lang, emb16, q8, scale, timings)
    summary = {subset: summarise(records, sizes, timings, subset) for subset in ('all', 'android', 'panel')}
    verdict = gate(summary)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'summary': summary, 'gate': verdict, 'records': records}, indent=1) + '\n')

    for subset in ('android', 'panel', 'all'):
        block = summary[subset]
        print(f'\n## {subset}: {block["queries"]} queries (label missing from index: {block["label_missing_from_index"]})')
        for name in VARIANTS:
            v = block['variants'][name]
            print(f'{name:16s} decision {v["decision_agree"]}/{block["queries"]} ({v["decision_agree_pct"]}%) '
                  f'top1 {v["top1_agree_pct"]}% top5 {v["top5_overlap_mean_pct"]}% '
                  f'dmargin med {v["margin_change_median"]} max {v["margin_change_max"]} '
                  f'new_wrong {v["new_wrong_passes"]}/{v["adversarial_pairs"]} '
                  f'size {v["size_bytes"]} search med {v["search_ms_median"]} ms p90 {v["search_ms_p90"]} ms')
            print(f'{"":16s} categories {v["categories"]}')
    print('\ngate (all scans; int8, int8+top50, float16):', verdict)


if __name__ == '__main__':
    main()
