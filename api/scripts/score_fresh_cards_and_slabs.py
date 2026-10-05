"""Independent card truth scoring on every frozen photo, including coverage gaps."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input','sources','truth','code-snapshot','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--regression',action='store_true')
    args=parser.parse_args()
    snapshot=json.loads(args.code_snapshot.read_text());assert snapshot['unchanged_after_run']
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in snapshot['code_hashes'].items())
    sources=json.loads(args.sources.read_text());source_hash=hashlib.sha256(args.sources.read_bytes()).hexdigest()
    assert snapshot['sources_sha256']==source_hash
    truth=json.loads(args.truth.read_text());assert truth['sources_sha256']==source_hash
    labels={p['id']:p for p in truth['photos']};photos={p['id']:p for p in sources['photos']}
    rows=[json.loads(l) for l in args.input.read_text().splitlines() if l.strip()]
    assert len(rows)==len({p['id'] for p in rows})==len(labels)==len(photos)==100
    assert set(labels)==set(photos)=={p['id'] for p in rows}
    checked=[]
    def canonical(pid):return pid if pid.startswith(('en:','ja:')) else 'en:'+pid
    for p in rows:
        s=photos[p['id']];assert hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest()==s['sha256']
        expected=set(labels[p['id']]['expected_card_ids']);r=p['response'];b=r.get('best_match')
        best=canonical(b['card_id']) if b else None
        alternatives=[canonical(c['card_id']) for c in r.get('alternatives',[])]
        checked.append({**p,'manual_truth':s['manual_truth'],'source_page':s['page_url'],
            'expected_card_ids':sorted(expected),'scorable':bool(expected),
            'best_match_correct':best in expected if expected else None,
            'correct_in_best_or_alternatives':bool(expected.intersection([best]+alternatives)) if expected else None,
            'wrong_automatic_match':bool(expected) and r['status']=='matched' and best not in expected})
    def counts(items):
        scored=[p for p in items if p['scorable']]
        return {'photos':len(items),'scored':len(scored),'unscored':len(items)-len(scored),
            'correct_best_match':sum(p['best_match_correct'] is True for p in scored),
            'correct_in_best_or_alternatives':sum(p['correct_in_best_or_alternatives'] is True for p in scored),
            'wrong_best_match':sum(p['response'].get('best_match') is not None and not p['best_match_correct'] for p in scored),
            'no_best_match':sum(p['response'].get('best_match') is None for p in scored),
            'wrong_automatic_matches':sum(p['wrong_automatic_match'] for p in scored),
            'statuses':dict(Counter(p['response']['status'] for p in items))}
    timings=sorted(p['response']['timings_ms']['total_ms'] for p in checked)
    summary={'evaluation_kind':'tuned_regression' if args.regression else 'fresh_local_full_pipeline_baseline',
        **counts(checked),'by_kind':{k:counts([p for p in checked if p['manual_truth']['kind']==k]) for k in ('raw','slab')},
        'distinct_scorable_printings':len({c for p in checked for c in p['expected_card_ids']}),
        'latency_ms':{'median':statistics.median(timings),'p95':timings[94],'max':max(timings)},
        'code_hashes':snapshot['code_hashes'],'source_sha256':source_hash,
        'truth_sha256':hashlib.sha256(args.truth.read_bytes()).hexdigest(),
        'limitations':'Local offline recognition on Internet photos; not staging HTTP/Flutter/camera, random population, physical condition, finish, stamp or authenticity accuracy. Unbound catalogue truth retained and separately unscored. No test photo indexed.'}
    with args.output.open('x') as handle:json.dump({'summary':summary,'cases':checked},handle,indent=2)
    print(json.dumps({k:v for k,v in summary.items() if k!='code_hashes'},indent=2))

if __name__=='__main__':main()
