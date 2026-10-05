"""Compare user-visible results on the sealed 50-photo regression sample."""
from collections import Counter
import argparse
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, default=root / 'docs/physical-photo-fresh50-final.json')
parser.add_argument('--input', type=Path, default=root / 'docs/physical-photo-fresh50-recovered-references.json')
parser.add_argument('--output', type=Path, default=root / 'docs/physical-photo-fresh50-recovered-presentation-audit.json')
args = parser.parse_args()
old = json.loads(args.baseline.read_text())
new = json.loads(args.input.read_text())
old_cases = {c['name']: c for c in old['cases'] if c['group'] == 'physical_photo'}
cases = [c for c in new['cases'] if c['group'] == 'physical_photo']
assert len(cases) == len(old_cases) == 50

def correct(candidate, case):
    if not candidate:
        return False
    if candidate['card_id'] == case['expected_id']:
        return True
    # Equivalent provider-prefixed English IDs only, not different printings.
    return (case['expected_id'].startswith('en:') and
            candidate['card_id'] == case['expected_id'][3:])

def evaluate(case):
    row = case['after']
    best = row.get('best_match')
    hit = correct(best, case)
    return {'photo': case['name'], 'expected_id': case['expected_id'],
            'best_match_id': best['card_id'] if best else None,
            'best_match_correct': hit,
            'correct_in_best_or_alternatives': hit or any(correct(c, case) for c in row.get('alternatives', [])),
            'status': row['status'], 'match_state': row.get('match_state'),
            'automatic_wrong_match': row['status'] == 'matched' and not hit}

rows = [evaluate(c) for c in cases]
previous = {name: evaluate(c) for name, c in old_cases.items()}
report = {'scope': 'Same sealed 50-photo regression sample; local, not deployed. Not a new holdout or population accuracy estimate.',
          'baseline': str(args.baseline), 'input': str(args.input),
          'counts': {'photos': 50, 'best_match_correct': sum(r['best_match_correct'] for r in rows),
                     'best_match_wrong': sum(bool(r['best_match_id']) and not r['best_match_correct'] for r in rows),
                     'no_best_match': sum(not r['best_match_id'] for r in rows),
                     'correct_in_best_or_alternatives': sum(r['correct_in_best_or_alternatives'] for r in rows),
                     'automatic_matches': sum(r['status'] == 'matched' for r in rows),
                     'wrong_automatic_matches': sum(r['automatic_wrong_match'] for r in rows)},
          'statuses': dict(Counter(r['status'] for r in rows)),
          'improved_best_match': [r['photo'] for r in rows if r['best_match_correct'] and not previous[r['photo']]['best_match_correct']],
          'regressed_best_match': [r['photo'] for r in rows if not r['best_match_correct'] and previous[r['photo']]['best_match_correct']],
          'mewtwo_gg44': [r for r in rows if r['expected_id'] == 'en:swsh12.5gg-GG44'],
          'failures': [r for r in rows if not r['best_match_correct']],
          'negatives': new['negatives'], 'cases': rows}
target = args.output
target.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('cases', 'negatives')}, indent=2))
