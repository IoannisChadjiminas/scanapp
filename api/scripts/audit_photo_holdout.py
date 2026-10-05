"""Audit displayed best matches on a completed new holdout, not internal rank."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

def correct(candidate, case):
    if not candidate:
        return False
    expected = case['expected_id']
    # Legacy English provider-prefixed aliases only, not another printing.
    return candidate['card_id'] == expected or (
        expected.startswith('en:') and candidate['card_id'] == expected[3:])

def evaluate(case, side):
    response = case[side]
    best = response.get('best_match')
    hit = correct(best, case)
    return {'photo':case['name'], 'expected_id':case['expected_id'],
        'best_match_id':best['card_id'] if best else None,
        'best_match_correct':hit,
        'correct_in_best_or_alternatives':hit or any(correct(c,case) for c in response.get('alternatives',[])),
        'status':response['status'],'match_state':response.get('match_state'),
        'automatic_wrong_match':response['status']=='matched' and not hit,
        'artwork_covered':case['truth_in_artwork_pilot'],
        'language':case['provenance']['language'],'layout':case['provenance']['layout'],
        'page_url':case['provenance']['page_url'],
        'full_shortlist_recall':response['full_shortlist_printing_recall'],
        'artwork_shortlist_recall':response['artwork_shortlist_printing_recall'],
        'identity_evidence':response['identity_evidence'],
        'ocr':response['ocr'], 'query_size':response['query_size'],
        'frame_selection':response['frame_selection'],
        'best_cardmarket_url':best.get('cardmarket_url') if best else None}

def counts(rows):
    return {'photos':len(rows),'best_match_correct':sum(r['best_match_correct'] for r in rows),
        'best_match_wrong':sum(bool(r['best_match_id']) and not r['best_match_correct'] for r in rows),
        'no_best_match':sum(not r['best_match_id'] for r in rows),
        'correct_in_best_or_alternatives':sum(r['correct_in_best_or_alternatives'] for r in rows),
        'automatic_matches':sum(r['status']=='matched' for r in rows),
        'wrong_automatic_matches':sum(r['automatic_wrong_match'] for r in rows),
        'statuses':dict(Counter(r['status'] for r in rows))}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--code-baseline',type=Path,required=True)
    parser.add_argument('--catalogue',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--regression',action='store_true',
                        help='Explicitly score tuned regression photos, not a fresh holdout.')
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    sources = json.loads(args.sources.read_text())
    old_code = json.loads(args.code_baseline.read_text())['summary']['code_hashes']
    code_unchanged = report['summary']['code_hashes'] == old_code
    assert code_unchanged or args.regression, 'Scanner changed after the prior regression'
    assert report['summary']['source_labels_sha256'] == hashlib.sha256(args.sources.read_bytes()).hexdigest()
    cases = [c for c in report['cases'] if c['group']=='physical_photo' and c['condition']=='raw_photo']
    assert len(cases) == len(sources['photos']) == 50
    assert {c['name'] for c in cases} == {p['id'] for p in sources['photos']}
    labels = {p['id']:p for p in sources['photos']}
    for c in cases:
        assert c['expected_id'] == labels[c['name']]['expected_card_id']
        assert c['provenance']['sha256'] == labels[c['name']]['sha256']
    before, rows = ([evaluate(c,side) for c in cases] for side in ('before','after'))
    catalogue = sqlite3.connect('file:'+str(args.catalogue.resolve())+'?mode=ro',uri=True)
    indexed_truths = {c['expected_id']:catalogue.execute('SELECT has_image,image_path,cardmarket_url FROM cards WHERE id=?',(c['expected_id'],)).fetchone() for c in cases}
    output = {'scope':('Tuned 50-photo regression, NOT fresh holdout accuracy. ' if args.regression else 'Fresh frozen 50-photo Internet physical-card convenience holdout. ') + 'Local offline API recognition, not deployed Flutter/camera/HTTP tests. Exact set/number/language evaluated; finish/authenticity not ground truth.',
        'counts':counts(rows),
        'full_card_only':None if report['summary'].get('baseline_comparison') else counts(before),
        'previous_frozen_enabled':counts(before) if report['summary'].get('baseline_comparison') else None,
        'distinct_printing_ids':len({c['expected_id'] for c in cases}),
        'strata':{f'{field}:{value}':counts([r for r in rows if r[field]==value])
            for field in ('language','layout','artwork_covered') for value in sorted({r[field] for r in rows})},
        'code_unchanged_from_generic_fix_regression':code_unchanged,
        'regression_run':args.regression,
        'changed_code_files':[p for p,h in report['summary']['code_hashes'].items() if old_code.get(p)!=h],
        'source_labels_sha256':report['summary']['source_labels_sha256'],
        'all_50_retained':True,'failures':[r for r in rows if not r['best_match_correct']],
        'wrong_automatic_cases':[r for r in rows if r['automatic_wrong_match']],
        'negatives':report['negatives'],'cases':rows,
        'latency_ms':report['overall']['after']['latency_ms'],
        'catalogue_missing_reference_truths':[i for i,r in indexed_truths.items() if not r or not r[0] or not r[1]],
        'catalogue_missing_cardmarket_truths':[i for i,r in indexed_truths.items() if r and not r[2]],
        'limitations_context':('The inherited source limitations describe the original untouched holdout. '
            'This report is a tuned regression: failure photos informed generic fixes but were not indexed as catalogue references.'
            if args.regression else 'The source limitations describe this untouched holdout.'),
        'limitations':sources['limitations']}
    with args.output.open('x') as handle: json.dump(output,handle,indent=2,ensure_ascii=False)
    print(json.dumps({k:v for k,v in output.items() if k not in ('cases','failures','negatives')},indent=2))

if __name__ == '__main__': main()
