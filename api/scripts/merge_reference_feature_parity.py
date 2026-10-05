"""Aggregate every paired diagnostic shard without excluding failures."""
import argparse
import json
from pathlib import Path
import sys

from compare_reference_feature_storage import selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--shards', type=int, required=True)
    args = parser.parse_args()
    summaries = [json.loads((args.audit_dir / f'shard-{i}/parity-summary.json').read_text())
                 for i in range(args.shards)]
    audits = [json.loads((args.audit_dir / f'shard-{i}/features-audit.json').read_text())
              for i in range(args.shards)]
    assert all(a['code_hashes'] == audits[0]['code_hashes'] and
               a['catalogue_sha256'] == audits[0]['catalogue_sha256'] and
               a['versions'] == audits[0]['versions'] for a in audits)
    cases = [json.loads(line) for i in range(args.shards)
             for line in (args.audit_dir / f'shard-{i}/features.jsonl').read_text().splitlines()]
    assert len(cases) == 150 == len({c['case']['id'] for c in cases})
    assert {c['case']['id'] for c in cases} == {c['id'] for c in selection()}
    summary = dict(photos=sum(s['photos'] for s in summaries),
        equal_responses=sum(s['equal_responses'] for s in summaries),
        grading_equal=sum(s['grading_equal'] for s in summaries),
        deltas=[d for s in summaries for d in s['deltas']],
        accuracy={kind: {key: sum(s['accuracy'][kind][key] for s in summaries)
                         for key in ('photos','scorable','correct_best_match','unscored')}
                  for kind in ('raw','slab')},
        no_reference_image_reads=all(s['no_reference_image_reads'] for s in summaries),
        limitations=summaries[0]['limitations'], versions=audits[0]['versions'])
    with (args.audit_dir / 'parity-summary.json').open('x') as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    if summary['deltas']:
        sys.exit('Storage-path regression detected; do not activate')


if __name__ == '__main__':
    main()
