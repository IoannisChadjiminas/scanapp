"""Score a complete frozen mixed sample without inflating slab coverage with raw negatives."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input','sources','truth','code-snapshot','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--regression',action='store_true')
    parser.add_argument('--full-scan',action='store_true',
        help='Score grading returned by the complete recognition probe and its full-app snapshot')
    args=parser.parse_args()
    sources=json.loads(args.sources.read_text())
    truth=json.loads(args.truth.read_text())['cases']
    snapshot=json.loads(args.code_snapshot.read_text())
    assert snapshot['unchanged_after_run']
    code_root=ROOT if args.full_scan else ROOT/'api'
    assert all(hashlib.sha256((code_root/p).read_bytes()).hexdigest()==h
               for p,h in snapshot['code_hashes'].items())
    assert sources['truth_sha256']==hashlib.sha256(args.truth.read_bytes()).hexdigest()
    rows=[json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    if args.full_scan:
        assert snapshot['sources_sha256']==hashlib.sha256(args.sources.read_bytes()).hexdigest()
        rows=[{'id':p['id'],'grading':p['response']['grading'],
               'grading_ms':p['response']['timings_ms']['grading_ms']} for p in rows]
    by_id={p['id']:p for p in sources['photos']}
    assert len(rows)==len(truth)==len(by_id)==len({p['id'] for p in rows})==100
    assert set(truth)==set(by_id)=={p['id'] for p in rows}
    checked=[]
    for p in rows:
        s=by_id[p['id']];known=truth[p['id']];g=p['grading']
        assert hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest()==s['sha256']
        checked.append({**p,'manual_truth':known,'source_page':s['page_url'],
            'company_correct':g['company']==known['company'],
            'grade_correct':g['grade']==known['grade'],
            'wrong_company':g['company'] is not None and g['company']!=known['company'],
            'wrong_grade':g['grade'] is not None and g['grade']!=known['grade'],
            'false_slab_claim':known['kind']=='raw' and g['slab_detected'] is True})
    slabs=[p for p in checked if p['manual_truth']['kind']=='slab']
    raw=[p for p in checked if p['manual_truth']['kind']=='raw']
    def counts(items):
        return {'photos':len(items),'both_correct':sum(p['company_correct'] and p['grade_correct'] for p in items),
            'company_correct':sum(p['company_correct'] for p in items),'grade_correct':sum(p['grade_correct'] for p in items),
            'wrong_company':sum(p['wrong_company'] for p in items),'wrong_grade':sum(p['wrong_grade'] for p in items),
            'slab_detected':sum(p['grading']['slab_detected'] is True for p in items)}
    costs=sorted(p['grading_ms'] for p in checked)
    summary={'evaluation_kind':'tuned_regression' if args.regression else 'fresh_unseen_baseline',
        'photos':len(checked),'slabs':counts(slabs),
        'raw_cards':{'photos':len(raw),'false_slab_claims':sum(p['false_slab_claim'] for p in raw),
                     'false_company':sum(p['wrong_company'] for p in raw),'false_grade':sum(p['wrong_grade'] for p in raw)},
        'by_company':{c:counts([p for p in slabs if p['manual_truth']['company']==c]) for c in ('psa','beckett','cgc','tag','ace','ags')},
        'latency_ms':{'median':statistics.median(costs),'p95':costs[94],'max':max(costs)},
        'code_hashes':snapshot['code_hashes'],'source_sha256':hashlib.sha256(args.sources.read_bytes()).hexdigest(),
        'truth_sha256':sources['truth_sha256'],'code_unchanged_during_probe':True,
        'probe_kind':'complete_local_recognition' if args.full_scan else 'isolated_label_component',
        'limitations':'Local offline label evidence; marketplace convenience sample, not live app or population accuracy. No raw condition, authenticity, cert, subgrade or TAG-score accuracy claim.'}
    with args.output.open('x') as handle:json.dump({'summary':summary,'cases':checked},handle,indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
