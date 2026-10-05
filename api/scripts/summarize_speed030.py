"""Assemble audited release evidence; no remote writes or scan mutations."""
import json
from pathlib import Path


def load(path): return json.loads(path.read_text())
def lines(path): return [json.loads(line) for line in path.read_text().splitlines()]
def checks(before, after):
    b, a = before.get('best_match') or {}, after.get('best_match') or {}
    return dict(status=before['status']==after['status'], ocr=before['ocr']==after['ocr'],
        grading=before['grading']==after['grading'],
        printing_review=before.get('printing_review')==after.get('printing_review'),
        best_card=b.get('card_id')==a.get('card_id'), url=b.get('cardmarket_url')==a.get('cardmarket_url'))


def main():
    root = Path(__file__).resolve().parents[2]; audit = root/'data/latency'
    publication = load(audit/'speed030-publication.json')
    replay = lines(audit/'speed030-paired.jsonl')
    before = {}; normal = []; streaming = []
    for i, case in enumerate(load(root/'data/catalogue-completion/20261004-01/staging-fixed-panel.json'), 1):
        b = load(audit/f'staging-speed030-before/response-{i:02}.json')
        a = load(audit/f'staging-speed030-after/response-{i:02}.json')
        before[case['id']] = b
        normal.append(dict(id=case['id'],checks=checks(b,a)))
    recent_before = {r['case']['id']:r for r in lines(audit/'speed030-recent-before.jsonl')}
    for r in lines(audit/'speed030-recent-after.jsonl'):
        b = recent_before[r['case']['id']]; before[r['case']['id']] = b['response']
        normal.append(dict(id=r['case']['id'], checks=checks(b['response'],r['response']),
            before_http_ms=b['http_ms'],after_http_ms=r['http_ms']))
    for r in lines(audit/'staging-speed030-stream.jsonl'):
        streaming.append(dict(id=r['case']['id'],checks=checks(before[r['case']['id']],r['response']),
                              preview_ms=r['first_provisional_ms'],http_ms=r['http_ms']))
    report = dict(release='STAGING-SPEED-030', publication=publication,
        api_tests_passed=1165,flutter_tests_passed=201,flutter_analysis='No issues',
        ios_release_build='Unsigned build succeeded; not installed on the testing phone',
        enabled=['Card OCR priority over optional label retries',
                 'Opt-in same-upload NDJSON preview + final; legacy JSON unchanged'],
        disabled_experiments=dict(staged_original='No qualifying real-panel retry omission; remains opt-in/off',
            narrow_footer=load(audit/'speed030-targeted-footer.summary.json')),
        offline_pair=load(audit/'speed030-paired.summary.json'),
        offline_exact_ocr=sum(r['before']['response']['ocr']==r['after']['response']['ocr'] for r in replay),
        offline_exact_hits=sum(r['before']['evidence']['hits']==r['after']['evidence']['hits'] for r in replay),
        offline_exact_grading=sum(r['before']['response']['grading']==r['after']['response']['grading'] for r in replay),
        legacy_live_pairs=normal,stream_live_pairs=streaming,
        live_stream_summary=load(audit/'staging-speed030-stream.summary.json'),
        preserved=['Catalogue, vectors and Cardmarket mappings','Recognition thresholds and OCR models',
                   'Printing/finish guards','Current hardware and unrelated services'],
        limitations=['Small frozen/live samples, not unseen accuracy or P95/maximum guarantees',
            'Preview is a visual suggestion: OCR may change identity, language or printing',
            'Optional grading may finish less often under card priority; Raw/manual choice remains the deadline policy',
            'Full result remains above five seconds on some scans; live speed measurements are mixed',
            'Initial publication guard detected deployment-driver files in its verification list and reverted; corrected v2 is healthy'],
        app_changes='Flutter architecture/testing/serialization skills kept provisional data separate from final confirmable scan results')
    assert publication['published'] and publication['catalogue_unchanged']
    assert all(all(r['checks'].values()) for r in normal+streaming), 'Review a live contract regression'
    assert report['offline_pair']['exact_match_contracts']==28
    output = audit/'speed030-summary.json'
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(report=str(output), legacy_checks=len(normal),stream_checks=len(streaming),
        preview_median_ms=report['live_stream_summary']['median_preview_ms'],
        full_max_ms=report['live_stream_summary']['max_total_ms'])))


if __name__ == '__main__': main()
