"""Render measured grading coverage and the residual manual-review queue."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--controls',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',default='v2',choices=['v2','v3'])
    parser.add_argument('--tests',type=int,default=646)
    parser.add_argument('--grading-tests',type=int,default=93)
    parser.add_argument('--baseline-correct',type=int,default=26)
    parser.add_argument('--baseline-version',default='v1')
    parser.add_argument('--snapshot',type=Path)
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    stats = results['summary']
    control = json.loads(args.controls.read_text())['summary']
    photos = {p['id']:p for p in json.loads((ROOT/'docs/grading-label100-frozen-sources-20261002.json').read_text())['photos']}
    rows = [
        f'# Grading recovery {args.version} — 2 October 2026', '',
        f"Correct company and grade together: **{stats['both_correct']}/100**, compared with **{args.baseline_correct}/100** in {args.baseline_version}. "
        f"Correct company: **{stats['company_correct']}/100**; correct grade: **{stats['grade_correct']}/100**. "
        f"Wrong returned company: **{stats['company_wrong']}**; wrong returned grade: **{stats['grade_wrong']}**. "
        f"**{stats['incomplete_without_wrong_field']} labels still require review**; this is not complete or near-100% recognition.", '',
        '| Grader | Photos | Company correct | Grade correct | Both correct | Pending |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for company,c in stats['by_company'].items():
        rows.append(f"| {company} | {c['photos']} | {c['company_correct']} | {c['grade_correct']} | {c['both_correct']} | {c['incomplete_without_wrong_field']} |")
    rows += ['', '## Generic changes', '',
        '- Safe registered/trademark typography, older CGC headings, plus-grade and AGS native descriptor support. No fuzzy issuer aliases or numeric grade inferred from a descriptor.',
        ('- Bounded label proposals from geometry and located OCR fields; padding retains top/bottom marks and small labels in wide photos. Numeral recovery uses observed component/edge bounds near a visible descriptor, then requires two matching literal reads of original pixels. Direct recognition does not mutate shared detector flags. Maximum six OCR image passes, including errors, with one-call exit for clear labels.' if args.version == 'v3' else
         '- Bounded label proposals from geometry and located OCR fields, perspective rectification, contrast and observed right-column digit recovery; maximum six OCR calls, including errors, with one-call exit for clear labels.'),
        '- Official PSA, Beckett, TAG, ACE and AGS shape templates; independently supported label text is mandatory. Colour and recognized card identity cannot supply the company. Template matches are not authenticity verification.',
        '- Certificate-scoped issuer transfer, cross-view conflict checks and exclusion of card-body EX suffixes below the label. Subgrades and TAG scores cannot become an overall grade.',
        '- Additive API company_source field; native grade/descriptor retained, unreadable/conflicting fields null. Unknown is not ungraded and raw physical condition remains not_assessed.', '',
        '## Validation and limitations', '',
        f'{args.tests} API tests pass, including {args.grading_tests} grading tests. Tests cover upright slabs in landscape photos, rotation, six-call bounds, trademark/legacy labels, native descriptors, logo polarity, uncorroborated digit rejection, descriptor/number contradictions, seller-watermark/card-text rejection, conflicting holders, API serialization/history and card-ranking isolation.', '',
        f"The separate existing 100-photo control set contains 20 labelled slabs and **80 raw/unlabelled photos**. "
        f"False slab claims: **{control['false_slab_claims']}/80**; wrong returned companies/grades: "
        f"**{control['wrong_company']}/{control['wrong_grade']}**. This small reused control set is not proof of a zero population false-positive rate.", '',
        f"Label-component latency: median **{stats['latency_ms']['median']:.0f} ms**, p95 "
        f"**{stats['latency_ms']['p95']:.0f} ms**, maximum **{stats['latency_ms']['max']:.0f} ms** "
        'under concurrent local Docker inference. Not staging HTTP or end-to-end scan latency. Recovery increases tail cost; USE_GRADING=false disables it.', '',
        'The 100-label photos and manual truth were frozen before v1. They are now tuning/regression data, **not an unseen accuracy test**. The final snapshot verifies code/assets did not change during the run; the scorer also verifies truth and every image hash. No certificates/card IDs are hardcoded into inference. Certification-digit, descriptor, subgrade and TAG-score accuracy are not independently scored. No authentication or physical raw-condition claim.', '',
        'Remaining failures concern missed/too-small issuer marks, stylized/embossed digits and incorrectly localized/poor-resolution labels. Null does not establish that the photo is unreadable to a human. A stronger trained label/digit detector and a fresh independent benchmark are still needed; the pending rows below must not be called fixed.', '',
        ('A prior wider-crop/threshold experiment produced an incorrect CGC gold-digit read (4 on a Pristine 10) and was rejected. V3 replaces that recovery with repeated direct recognition of original pixels inside an observed character region; top-descriptor/numeric contradictions still abstain instead of inferring a 10. Contrast losing a tiny plus sign at the same observed condition field cannot erase an original read, but separate locations remain conflicts. Only officially sourced seal/emblem variants supplement the existing logo references. The numbers here exclude rejected/intermediate experiments.' if args.version == 'v3' else
         'A wider-crop experiment produced one incorrect CGC gold-digit read (4 on a Pristine 10). That experiment was rejected. Final recovery requires the thresholded digit to be independently read from original colour pixels in the same position; top-descriptor/numeric contradictions abstain instead of inferring a 10. The final numbers here exclude rejected/intermediate experiments.'), '',
        'All changes are local. No deployment, database mutation, credential creation or grading-company certificate lookup occurred.', '',
        '## Residual manual-review queue', '',
        'Open the original full photo or source listing. Request a straight, close label photo without glare when a field cannot be established. These are per-photo OCR gaps, not incorrect catalogue mappings.', '',
        '| Photo | Expected company / grade | Observed company / grade | Warnings |',
        '|---|---|---|---|',
    ]
    for case in results['cases']:
        if case['company_correct'] and case['grade_correct']:
            continue
        known,actual = case['manual_truth'],case['grading']
        photo = ROOT/photos[case['id']]['path']
        warnings = ', '.join(actual['warnings']) or 'missing field'
        rows.append(f"| [{case['id']}]({photo}) · [source]({case['source_page']}) | "
                    f"{known['company']} / {known['grade']} | {actual['company']} / {actual['grade']} | {warnings} |")
    rows += ['', '## Reproducible artifacts', '',
        f'- [All 100 JSON responses, truth, warning codes, hashes and timings]({args.results.name})',
        f'- [Final code/asset snapshot]({args.snapshot.name if args.snapshot else "grading-label100-v2-validated-code-snapshot-20261002.json"})',
        f'- [Raw-card/slab control results]({args.controls.name})',
        '- [Original v1 baseline](grading-label100-baseline-20261002.json)',
        '- [API contract and policy](scan-grading-evidence.md)',
        '- Official logo URLs, extraction transforms and hashes: `api/app/recognition/assets/grading-logos/sources.json`', '',
    ]
    args.output.write_text('\n'.join(rows))
    print(json.dumps({'report':str(args.output),'pending':stats['incomplete_without_wrong_field']}))


if __name__ == '__main__':
    main()
