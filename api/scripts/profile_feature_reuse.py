"""Read-only, paired verification of exact feature reuse on frozen real photos.

This is a component benchmark, not an end-to-end accuracy/latency claim. Every
pair uses identical uploaded pixels, reference IDs, RNG seed and geometry rules.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file
from app.recognition.local_match import LocalArtworkVerifier, FULL_ART_BOX, FULL_ART_RARITIES
from app.recognition.reference_features import ReferenceFeatureStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--catalogue', type=Path, required=True)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.records.read_text().splitlines()]
    for record in records:
        case = record['case']
        assert sha256_file(args.audit_dir / case['photo_file']) == case['sha256']
    connection = sqlite3.connect(f'file:{args.catalogue}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    rows = [dict(row) for row in connection.execute('SELECT * FROM cards')]
    connection.close()
    cards = {row['id']: row for row in rows}
    store = ReferenceFeatureStore.load(args.features, rows)
    verifier = LocalArtworkVerifier(Path('/data'), feature_store=store)
    verifier.reference_boxes = {row['id']: FULL_ART_BOX for row in rows
        if str(row.get('rarity') or '').casefold() in FULL_ART_RARITIES}
    cv2.setNumThreads(1)
    results = []
    with args.output.open('x') as handle:
        for record in records:
            case = record['case']
            ids = list(dict.fromkeys(candidate['card_id']
                for candidate in record['after']['suggestions']))[:8]
            references = [(cid, cards[cid]['image_path']) for cid in ids if cid in cards]
            with Image.open(args.audit_dir / case['photo_file']) as image:
                photo = image.convert('RGB')
            # Cache all exact query profiles once, then prove that extraction
            # reuse changes neither geometry outcomes nor match order.
            verifier._query_cache.clear(); verifier._query_cache_bytes = 0
            verifier._cache.clear()
            store._arrays.clear(); store._arrays_bytes = 0
            cv2.setRNGSeed(0)
            start = time.perf_counter()
            cold = verifier.verify(photo, references)
            cold_ms = (time.perf_counter() - start) * 1000
            cv2.setRNGSeed(0)
            start = time.perf_counter()
            warm = verifier.verify(photo, references)
            warm_ms = (time.perf_counter() - start) * 1000
            assert cold == warm, case['id']
            # Frame recovery must also retain every projected pixel/corner.
            frame_equal = None
            if references and case['kind'] in ('reported_phone', 'phone_capture'):
                verifier._query_cache.clear(); verifier._query_cache_bytes = 0
                diagnostics_a, diagnostics_b = [], []
                cv2.setRNGSeed(0)
                a = verifier.propose_frame(photo, references[0], diagnostics_a)
                cv2.setRNGSeed(0)
                b = verifier.propose_frame(photo, references[0], diagnostics_b)
                assert diagnostics_a == diagnostics_b
                assert (a is None) == (b is None)
                if a is not None:
                    np.testing.assert_array_equal(np.asarray(a), np.asarray(b))
                frame_equal = True
            result = dict(id=case['id'], kind=case['kind'], references=len(references),
                cold_ms=cold_ms, warm_ms=warm_ms, matches=[asdict(match) for match in warm],
                exact_matches_equal=True, frame_equal=frame_equal)
            results.append(result)
            handle.write(json.dumps(result) + '\n'); handle.flush()
            print(json.dumps(dict(id=case['id'], number=len(results), total=len(records),
                cold_ms=round(cold_ms), warm_ms=round(warm_ms))), flush=True)
    summary = dict(photos=len(results), exact_equal=sum(r['exact_matches_equal'] for r in results),
        frame_equal=sum(r['frame_equal'] is True for r in results),
        cold_median_ms=statistics.median(r['cold_ms'] for r in results),
        warm_median_ms=statistics.median(r['warm_ms'] for r in results),
        median_saved_ms=statistics.median(r['cold_ms']-r['warm_ms'] for r in results),
        limitations='Component verification on frozen real photos; not unseen or end-to-end accuracy. '
            'Cold/warm ordering does not isolate file/CPU warmup; checksum validation retained.')
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
