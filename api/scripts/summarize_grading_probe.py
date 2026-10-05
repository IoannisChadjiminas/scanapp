"""Score label OCR against independently transcribed physical-photo labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,action='append',required=True)
    parser.add_argument('--truth',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--code-snapshot',type=Path,action='append',
                        help='Completed, stable probe snapshot for every input run')
    args = parser.parse_args()
    truth = json.loads(args.truth.read_text())['cases']
    rows = [json.loads(line) for path in args.input for line in path.read_text().splitlines()]
    assert len({row['id'] for row in rows}) == len(rows), 'duplicate case identifiers'
    assert set(truth).issubset({row['id'] for row in rows}), 'missing labelled cases'
    checks = []
    for row in rows:
        known = truth.get(row['id'])
        observed = row['grading']
        checks.append({**row, 'manual_truth':known,
            'wrong_company':bool(observed['company'] is not None and
                (known is None or observed['company'] != known['company'])),
            'wrong_grade':bool(observed['grade'] is not None and
                (known is None or observed['grade'] != known['grade'])),
            'false_slab_claim':known is None and observed['slab_detected'] is True})
    supported = [row for row in checks if row['manual_truth'] and row['manual_truth']['company']]
    graded = [row for row in checks if row['grading']['grade'] is not None]
    costs = sorted(row['grading_ms'] for row in rows)
    root = Path(__file__).resolve().parents[1]
    files = ['app/recognition/grading.py','app/recognition/ocr.py','app/schemas.py',
             'scripts/probe_grading_labels.py','scripts/summarize_grading_probe.py']
    code_hashes = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    if args.code_snapshot:
        assert len(args.code_snapshot) == len(args.input), 'one snapshot required per run'
        snapshots = [json.loads(p.read_text()) for p in args.code_snapshot]
        assert all(s['unchanged_after_run'] for s in snapshots), 'unfinished or unstable run'
        code_hashes = snapshots[0]['code_hashes']
        assert all(s['code_hashes'] == code_hashes for s in snapshots), 'different runtime revisions'
        assert all(hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
                   for name,digest in code_hashes.items()), 'runtime changed after probing'
    summary = {
        'limitations':'Tuned convenience seller-photo diagnostic, not independent general accuracy. '
            'Physical samples cover PSA/CGC only; six graders have parser tests. '
            'No authentication, raw condition, subgrade or certification digit accuracy claim.',
        'photos':len(rows), 'visually_reviewed_slabs':len(truth),
        'supported_company_slabs':len(supported),
        'company_correct':sum(row['grading']['company'] == row['manual_truth']['company'] for row in supported),
        'grade_correct_supported':sum(row['grading']['grade'] == row['manual_truth']['grade'] for row in supported),
        'grade_returned':len(graded),
        'wrong_company':sum(row['wrong_company'] for row in checks),
        'wrong_grade':sum(row['wrong_grade'] for row in checks),
        'false_slab_claims':sum(row['false_slab_claim'] for row in checks),
        'latency_ms':{'median':costs[len(costs)//2], 'p95':costs[min(len(costs)-1,int(.95*len(costs)))]},
        'grading_statuses':dict(Counter(row['grading']['grading_status'] for row in rows)),
        'manual_truth_sha256':hashlib.sha256(args.truth.read_bytes()).hexdigest(),
        'code_hashes':code_hashes,
        'code_unchanged_during_probe':bool(args.code_snapshot),
    }
    args.output.write_text(json.dumps({'summary':summary,'cases':checks},indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
