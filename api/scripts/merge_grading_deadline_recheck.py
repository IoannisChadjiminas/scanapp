"""Audit a full deadline replay plus all affected holder-review branch retests."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def card(response):
    return {k: v for k, v in response.items() if k not in {'id', 'timings_ms', 'grading'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', type=Path, required=True)
    parser.add_argument('--recheck', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    original = [json.loads(line) for line in args.full.read_text().splitlines()]
    recheck = [json.loads(line) for line in args.recheck.read_text().splitlines()]
    ids = {r['case']['id'] for r in original}
    assert len(original) == len(ids) == 150
    replacements = {r['case']['id']: r for r in recheck}
    assert len(replacements) == len(recheck) and replacements.keys() <= ids
    affected = {r['case']['id'] for r in original
                if r['parallel']['status'] == 'printing_ambiguous'
                and r['parallel']['grading']['company'] is not None}
    assert affected <= replacements.keys(), 'All affected branches must be retested'
    assert 'fresh100_205408031074' in replacements
    for old in original:
        new = replacements.get(old['case']['id'])
        if new:
            assert old['case'] == new['case']
            assert card(old['serial']) == card(new['serial'])
        elif card(old['serial']) != card(old['parallel']):
            raise AssertionError('Uncovered card regression')
    combined = [replacements.get(r['case']['id'], r) for r in original]
    plain_raw = {'is_graded': False, 'grading_status': 'ungraded'}
    # Derive the complete established plain-Raw schema, not a special fallback.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.recognition.grading import GradingEvidence
    plain_raw = GradingEvidence(**plain_raw).model_dump(mode='json')
    for record in combined:
        old, new = record['serial'], record['parallel']
        assert card(old) == card(new), record['case']['id']
        assert new['grading'] == plain_raw or new['grading'] == old['grading'], record['case']['id']
        assert new['timings_ms']['grading_wait_ms'] < 100, 'No wait on unfinished grading'
    summary = {
        'photos': 150,
        'counts': dict(Counter(r['case']['kind'] for r in combined)),
        'card_responses_equal': 150,
        'card_deadline': True,
        'diagnostic_detector_max_side': False,
        'affected_branches_rechecked': sorted(affected),
        'retested_photos': len(recheck),
        'ungraded': sum(r['parallel']['grading'] == plain_raw for r in combined),
        'grading_equal': sum(r['serial']['grading'] == r['parallel']['grading'] for r in combined),
        'latency_ms': {mode: {
            'median': round(statistics.median(r['elapsed_ms'][mode] for r in combined), 2),
            'max': round(max(r['elapsed_ms'][mode] for r in combined), 2),
            'under_5000': sum(r['elapsed_ms'][mode] <= 5000 for r in combined),
        } for mode in ('serial', 'parallel')},
        'limitations': 'Full 150-photo replay with every affected completed-holder review branch retested after restoring identity OCR. Frozen convenience photos; reused baseline, not an unseen accuracy test or latency SLA.',
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir/'parallel-paired.jsonl').open('x') as handle:
        for record in combined:
            handle.write(json.dumps(record)+'\n')
    (args.output_dir/'parallel-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
