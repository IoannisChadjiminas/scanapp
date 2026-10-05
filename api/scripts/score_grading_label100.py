"""Score frozen truth/photos as baseline or explicitly labelled tuned regression."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]

def counts(rows):
    return {
        'photos':len(rows),
        'company_correct':sum(p['company_correct'] for p in rows),
        'company_missing':sum(p['grading']['company'] is None for p in rows),
        'company_wrong':sum(p['company_wrong'] for p in rows),
        'grade_correct':sum(p['grade_correct'] for p in rows),
        'grade_missing':sum(p['grading']['grade'] is None for p in rows),
        'grade_wrong':sum(p['grade_wrong'] for p in rows),
        'both_correct':sum(p['company_correct'] and p['grade_correct'] for p in rows),
        'any_wrong_field':sum(p['company_wrong'] or p['grade_wrong'] for p in rows),
        'incomplete_without_wrong_field':sum(not (p['company_wrong'] or p['grade_wrong'])
            and not (p['company_correct'] and p['grade_correct']) for p in rows),
        'slab_detected':sum(p['grading']['slab_detected'] is True for p in rows),
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--code-snapshot',type=Path,
                        help='Completed probe snapshot for a tuned regression, not unseen accuracy')
    args = parser.parse_args()
    sources_path = ROOT/'docs/grading-label100-frozen-sources-20261002.json'
    frozen = json.loads(sources_path.read_text())
    truth_path = ROOT/'docs/grading-label100-manual-truth-20261002.json'
    truth = json.loads(truth_path.read_text())['cases']
    assert hashlib.sha256(truth_path.read_bytes()).hexdigest() == frozen['truth_sha256']
    snapshot = json.loads(args.code_snapshot.read_text()) if args.code_snapshot else None
    if snapshot:
        assert snapshot['unchanged_after_run'] is True, 'probe did not finish with stable source'
    code_hashes = snapshot['code_hashes'] if snapshot else frozen['code_hashes']
    for name,digest in code_hashes.items():
        assert hashlib.sha256((ROOT/'api'/name).read_bytes()).hexdigest() == digest, name
    sources = {p['id']:p for p in frozen['photos']}
    rows = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    assert len(rows) == len({p['id'] for p in rows}) == 100
    assert set(truth) == set(sources) == {p['id'] for p in rows}
    checked = []
    for p in rows:
        known, actual = truth[p['id']], p['grading']
        path = ROOT / sources[p['id']]['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sources[p['id']]['sha256']
        checked.append({**p, 'manual_truth':known,
            'source_page':sources[p['id']]['page_url'],
            'image_sha256':sources[p['id']]['sha256'],
            'company_correct':actual['company'] == known['company'],
            'grade_correct':actual['grade'] == known['grade'],
            'company_wrong':actual['company'] is not None and actual['company'] != known['company'],
            'grade_wrong':actual['grade'] is not None and actual['grade'] != known['grade']})
    costs = sorted(p['grading_ms'] for p in checked)
    summary = {
        **counts(checked),
        'by_company':{c:counts([p for p in checked if p['manual_truth']['company']==c])
                      for c in ('psa','beckett','cgc','tag','ace','ags')},
        'latency_ms':{'median':statistics.median(costs),'p95':costs[94], 'max':max(costs)},
        'statuses':dict(Counter(p['grading']['grading_status'] for p in checked)),
        'warnings':dict(Counter(w for p in checked for w in p['grading']['warnings'])),
        'code_hashes':code_hashes,
        'evaluation_kind':'tuned_regression' if snapshot else 'unseen_baseline',
        'code_and_truth_unchanged_after_freeze':not bool(snapshot),
        'code_unchanged_during_probe':bool(snapshot),
        'truth_and_photos_unchanged_after_freeze':True,
        'raw_results_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'frozen_sources_sha256':hashlib.sha256(sources_path.read_bytes()).hexdigest(),
        'limitations':[
            ('Reused tuning/regression photos; not unseen accuracy or an estimate of all camera scans.'
             if snapshot else 'New, manually reviewed convenience seller-photo holdout; not an estimate of all camera scans.'),
            'Only company and overall numeric grade have independent scored truth.',
            'Null fields are abstentions/missing output, not necessarily unreadable to a human.',
            'No authentication, physical raw-condition, native descriptor, certification digit, subgrade or TAG-score accuracy claim.',
            'Isolated local label component, not staging API HTTP/end-to-end card matching latency.',
            'Photos retain original backgrounds, glare and framing; contact-sheet crops were for manual review only.',
        ],
    }
    args.output.write_text(json.dumps({'summary':summary,'cases':checked},indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__ == '__main__': main()
