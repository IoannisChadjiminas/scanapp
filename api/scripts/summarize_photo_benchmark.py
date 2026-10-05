"""Summarize a completed frozen paired photo run, without retaining OCR rule text."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


def rollup(cases):
    output = {'photos': len(cases)}
    for side in ('before', 'after'):
        rows = [case[side] for case in cases]
        totals = sorted(row['timings_ms']['total_ms'] for row in rows)
        output[side] = {
            metric: sum(row[metric] for row in rows) for metric in
            ('top_correct', 'candidate_recalled', 'automatic_claim',
             'automatic_wrong_printing', 'full_shortlist_printing_recall',
             'artwork_shortlist_printing_recall')}
        output[side]['statuses'] = dict(Counter(row['status'] for row in rows))
        output[side]['latency_ms'] = {
            'median': round(statistics.median(totals), 2) if totals else None,
            'sample_p95_nearest_rank': totals[math.ceil(.95 * len(totals)) - 1] if totals else None,
            'max': max(totals) if totals else None,
            'stage_medians': {stage: round(statistics.median(
                row['timings_ms'].get(stage, 0) for row in rows), 2) if rows else None
                for stage in ('detect_ms', 'frame_proposal_ms', 'embed_ms', 'artwork_embed_ms',
                              'artwork_retrieve_ms', 'ocr_ms', 'local_artwork_ms', 'cardmarket_ms',
                              'boundary_proposal_ms', 'boundary_selection_ms', 'boundary_retry_ms', 'first_pass_ms')}
        }
    output['recall_gains'] = [c['name'] for c in cases
        if not c['before']['candidate_recalled'] and c['after']['candidate_recalled']]
    output['recall_regressions'] = [c['name'] for c in cases
        if c['before']['candidate_recalled'] and not c['after']['candidate_recalled']]
    return output


def summarize(records):
    summaries = [r['summary'] for r in records if 'summary' in r]
    if len(summaries) != 1:
        raise ValueError('Require one completed-run summary; partial runs are not reports')
    cases = [r['case'] for r in records if 'case' in r]
    raw = [c for c in cases if c['group'] == 'physical_photo' and c['condition'] == 'raw_photo']
    summary = summaries[0]
    if len(raw) != summary['sample']['photos'] or len({c['name'] for c in raw}) != len(raw):
        raise ValueError('Missing or repeated selected physical photos')
    strata = {}
    for field in ('layout', 'language'):
        for value in sorted({c['provenance'][field] for c in raw}):
            strata[f'{field}:{value}'] = rollup([c for c in raw if c['provenance'][field] == value])
    for covered in (True, False):
        strata[f'artwork_coverage:{covered}'] = rollup([c for c in raw
            if c['truth_in_artwork_pilot'] == covered])
    for slab in (True, False):
        strata[f'slab:{slab}'] = rollup([c for c in raw
            if ('slab' in c['provenance']['conditions']) == slab])
    failures = []
    for c in raw:
        if not c['after']['candidate_recalled'] or c['after']['automatic_wrong_printing']:
            failures.append({key: c[key] for key in ('name', 'expected_id', 'truth_in_artwork_pilot', 'provenance')}
                | {'status': c['after']['status'], 'top_id': c['after']['top_id'],
                   'top_correct': c['after']['top_correct'],
                   'automatic_wrong_printing': c['after']['automatic_wrong_printing'],
                   'message': c['after']['message'], 'ocr': c['after']['ocr'],
                   'local_verified': bool(c['after']['local_artwork_matches'])})
    # Remove verbatim card rules from all copies, including the failure queue.
    for c in cases:
        for side in ('before', 'after'):
            c[side]['ocr'].pop('lines', None)
            # Keep only structured fractions from diagnostic hit traces, not
            # copyright/rules/serial labels captured during debugging.
            if 'ocr_hits' in c[side]:
                c[side]['ocr_hits'] = [h for h in c[side]['ocr_hits'] if
                    h.get('region') == 'collector' and '/' in h.get('text','')
                    and len(h.get('text','')) <= 20]
    for failure in failures:
        failure['ocr'].pop('lines', None)
    return {'summary': summary, 'overall': rollup(raw), 'strata': strata,
            'failures': failures, 'cases': cases,
            'negatives': [r['negative'] for r in records if 'negative' in r]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--framing', type=Path,
                        help='Separate forced-truth diagnostic; never included as benchmark successes')
    parser.add_argument('--coverage', type=Path, help='Read-only full-index ID coverage audit')
    args = parser.parse_args()
    report = summarize([json.loads(line) for line in args.input.read_text().splitlines() if line.strip()])
    if args.framing:
        framing = [json.loads(line) for line in args.framing.read_text().splitlines() if line.strip()]
        raw = [c for c in report['cases'] if c['condition'] == 'raw_photo']
        if {r['photo'] for r in framing} != {c['name'] for c in raw}:
            raise ValueError('Framing diagnostic must cover exactly the frozen raw sample')
        failed = {c['name'] for c in raw if not c['after']['candidate_recalled']}
        report['framing_diagnostic'] = {
            'scope': 'Oracle-assisted correct-reference geometry on detector output; not retrieval accuracy',
            'detected': sum(r['detected'] for r in framing),
            'forced_truth_verified': sum(bool(r['forced_truth_geometry']) for r in framing),
            'failed_returned_recall_but_forced_truth_verified': [r['photo'] for r in framing
                if r['photo'] in failed and r['forced_truth_geometry']],
            'records': framing}
    if args.coverage:
        report['full_index_coverage'] = json.loads(args.coverage.read_text())
    report['analysis_audit'] = {
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'raw_run_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'framing_sha256': hashlib.sha256(args.framing.read_bytes()).hexdigest() if args.framing else None,
        'coverage_sha256': hashlib.sha256(args.coverage.read_bytes()).hexdigest() if args.coverage else None}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'overall': report['overall'], 'strata': report['strata']}, indent=2))


if __name__ == '__main__':
    main()
