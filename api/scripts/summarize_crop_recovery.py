"""Validate and summarize completed crop controls against the frozen audit."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('input','baseline','photo-report','output'):
        parser.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args()
    records=[json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    cases=[r['case'] for r in records if 'case' in r]
    negatives=[r['negative'] for r in records if 'negative' in r]
    summaries=[r['summary'] for r in records if 'summary' in r]
    baseline=json.loads(args.baseline.read_text())
    key=lambda c:(c['expected_id'],c['condition'])
    before={key(c):c for c in baseline['cases']}
    after={key(c):c for c in cases}
    if len(cases)!=30 or len(after)!=30 or set(before)!=set(after) or len(summaries)!=1 or len(negatives)!=2:
        raise ValueError('Require the complete, unique 30-case frozen audit and two negatives')
    photo=json.loads(args.photo_report.read_text())
    source_root=Path(__file__).resolve().parents[1]
    for name,expected in photo['summary']['code_hashes'].items():
        if digest(source_root/name)!=expected:
            raise ValueError('Selected recognition source changed since photo run: '+name)
    retained=('expected_id','condition','status','top_id','top_correct','candidate_recalled','false_specific_claim')
    gains=[list(k) for k,c in after.items() if c['candidate_recalled'] and not before[k]['candidate_recalled']]
    regressions=[list(k) for k,c in after.items() if not c['candidate_recalled'] and before[k]['candidate_recalled']]
    baseline_recalled=sum(c['candidate_recalled'] for c in before.values())
    # The raw runner was invoked without --baseline-dir. Replace its empty
    # comparison counters with the actual frozen report comparison, not zero.
    summary=dict(summaries[0], baseline_candidate_recalled=baseline_recalled,
                 regressed_candidate_recall=len(regressions))
    report={
        'summary':summary,
        'baseline_candidate_recalled':baseline_recalled,
        'recall_gains':gains,
        'recall_regressions':regressions,
        'art_only':{metric:sum(bool(c[metric]) for c in cases if c['condition']=='art_only')
                    for metric in ('candidate_recalled','false_specific_claim')},
        'art_only_automatic_claims':sum(c['status']=='matched' for c in cases if c['condition']=='art_only'),
        'cases':[{k:c[k] for k in retained} for c in cases],
        'negatives':negatives,
        'provenance':{'raw_run_sha256':digest(args.input),'baseline_sha256':digest(args.baseline),
                      'selected_photo_report_sha256':digest(args.photo_report),
                      'analysis_sha256':digest(Path(__file__)),
                      'recognition_code_hashes':photo['summary']['code_hashes'],
                      'artwork_manifest':photo['summary']['artwork_manifest']},
        'scope':'Synthetic reference controls, not independent camera accuracy. All data mounts read-only, network disabled.'}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('summary','baseline_candidate_recalled','recall_gains','recall_regressions','art_only')}))


if __name__=='__main__':
    main()
