#!/usr/bin/env python3
"""Rank unresolved listing photos against both active DINOv2 catalogue indexes.

Run with the API's installed Python dependencies and PYTHONPATH pointing at api/.
Only reads model/index artifacts. Outputs candidates, never verified mappings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image

from app.recognition.artifacts import resolve_bundle_dir, validate_embeddings
from app.recognition.embed import DinoEmbedder


def load_index(data: Path, mode: str):
    bundle = resolve_bundle_dir(data / 'vectors' / mode)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest['preprocess_config'] != mode:
        raise ValueError('Index preprocessing does not match requested mode')
    matrix = np.load(bundle / 'embeddings.npy')
    ids = np.load(bundle / 'embedding_card_ids.npy')
    validate_embeddings(matrix, ids)
    return matrix, ids, {'bundle': str(bundle), 'manifest': manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('/data'))
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--photos', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    pad, ids, pad_meta = load_index(args.data, 'pad')
    square, square_ids, square_meta = load_index(args.data, 'square')
    if set(ids.tolist()) != set(square_ids.tolist()):
        raise ValueError('Pad and square indexes cover different cards')
    if not np.array_equal(ids, square_ids):
        order = {str(ident): i for i, ident in enumerate(square_ids)}
        square = square[[order[str(ident)] for ident in ids]]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'index-evidence.json').write_text(json.dumps({'pad': pad_meta, 'square': square_meta}, indent=2))
    embedder = DinoEmbedder(str(args.data / 'models' / 'dinov2_small.onnx'), args.threads, 1)
    rows = json.loads(args.review.read_text())['rows']
    rows = [r for r in rows if r['status'] not in {'proposed_match', 'non_catalogue_item'}]
    if args.limit:
        rows = rows[:args.limit]
    start = time.monotonic()
    counts = {'ranked': 0, 'photo_unavailable': 0, 'error': 0}
    with (args.output / 'visual-candidates.jsonl').open('w') as out:
        for i, row in enumerate(rows, 1):
            url = row['listing_image_url']
            path = args.photos / (hashlib.sha256(url.encode()).hexdigest()[:20] + '.img')
            result = {'url': row['url'], 'name': row['name'], 'expansion': row['expansion'], 'metadata_status': row['status']}
            if not path.exists():
                result['status'] = 'photo_unavailable'
            else:
                try:
                    with Image.open(path) as image:
                        pad_scores = pad @ embedder.embed(image, 'pad')
                        square_scores = square @ embedder.embed(image, 'square')
                    scores = (pad_scores + square_scores) / 2
                    indices = np.argsort(-scores)[:8]
                    result.update(status='ranked', photo_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  candidates=[{'card_id': str(ids[j]), 'score': round(float(scores[j]), 6),
                                               'pad_score': round(float(pad_scores[j]), 6),
                                               'square_score': round(float(square_scores[j]), 6)} for j in indices],
                                  gap=round(float(scores[indices[0]] - scores[indices[1]]), 6))
                except Exception as exc:
                    result.update(status='error', error=str(exc))
            counts[result['status']] += 1
            out.write(json.dumps(result, ensure_ascii=False) + '\n')
            out.flush()
            if i % 100 == 0 or i == len(rows):
                print(json.dumps({'processed': i, 'total': len(rows), 'seconds': round(time.monotonic()-start, 1), **counts}), flush=True)
    (args.output / 'summary.json').write_text(json.dumps({'total': len(rows), **counts}, indent=2))


if __name__ == '__main__':
    main()
