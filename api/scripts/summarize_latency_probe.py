"""Summarize a frozen latency regression, retaining known baseline misses."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)]


def canonical_id(card_id):
    if card_id and ':' not in card_id:
        return 'en:'+card_id
    return card_id


def summarize(rows):
    totals = Counter()
    repeats = Counter()
    deltas = []
    longest = []
    for row in rows:
        old, new = row['serial'], row['parallel']
        differences = [k for k in old if k not in {'id','timings_ms'} and old[k] != new[k]]
        if differences:
            deltas.append({'id': row['case']['id'], 'fields': differences,
                'best_unchanged': old['best_match'] == new['best_match'],
                'grade_unchanged': old['grading'] == new['grading']})
        seen = set()
        for event in row.get('ocr_profile', {}).get('parallel', []):
            totals[event['model']] += event['ms']
            key = (event['model'], tuple(event['shape']), event['sha256'])
            if key in seen:
                repeats[event['model']] += event['ms']
            seen.add(key)
            longest.append({**event, 'case_id': row['case']['id']})
    quality = {}
    for kind in ('raw', 'slab'):
        group = [r for r in rows if r['case']['kind'] == kind]
        scored = [r for r in group if r['case']['expected_card_ids']]
        quality[kind] = {'photos': len(group), 'scorable': len(scored),
            'best_matches_unchanged': sum(r['serial']['best_match'] == r['parallel']['best_match'] for r in group),
            'gradings_unchanged': sum(r['serial']['grading'] == r['parallel']['grading'] for r in group),
            'correct': {mode: sum(canonical_id((r[mode]['best_match'] or {}).get('card_id'))
                                in r['case']['expected_card_ids'] for r in scored)
                        for mode in ('serial','parallel')}}
    latency = {}
    for mode in ('serial','parallel'):
        latency[mode] = {}
        for kind in ('all','raw','slab'):
            times = [r['elapsed_ms'][mode] for r in rows if kind == 'all' or r['case']['kind'] == kind]
            if times:
                latency[mode][kind] = {'median_ms': round(statistics.median(times),2),
                    'p95_ms': round(percentile(times,.95),2), 'max_ms': round(max(times),2),
                    'under_5_seconds': sum(t <= 5000 for t in times), 'photos': len(times)}
    return {'photos':len(rows), 'response_deltas':deltas, 'quality':quality,
            'latency':latency, 'ocr_model_ms':dict(totals), 'exact_repeated_model_ms':dict(repeats),
            'longest_model_passes':sorted(longest,key=lambda e:e['ms'],reverse=True)[:12],
            'limitations':'Frozen convenience-photo regression. Reused baseline timing is not a contemporaneous paired performance test. Not unseen camera accuracy or a five-second SLA.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = summarize([json.loads(line) for line in args.input.read_text().splitlines()])
    serialized = json.dumps(report,indent=2)
    if args.output:
        with args.output.open('x') as handle:
            handle.write(serialized+'\n')
    print(serialized)
