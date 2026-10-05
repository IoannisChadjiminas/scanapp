"""Run the fixed catalogue rollout panel, serially, against authorized staging.

Creates test scans under a new session. Keeps responses and upload-to-result time;
does not confirm scans, modify catalogue mappings, or remove saved test data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--panel', type=Path, required=True)
    p.add_argument('--photos-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    cases = json.loads(a.panel.read_text())
    if len(cases) != 5 or len({c['id'] for c in cases}) != 5:
        raise ValueError('Use the fixed five-case rollout panel')
    for c in cases:
        path = a.photos_root / c['photo_file']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != c['sha256']:
            raise ValueError('Frozen panel photo mismatch')
    a.output.mkdir(parents=True, exist_ok=False)
    cookie = a.output / 'test-session.cookies.private'
    cookie.touch(mode=0o600)
    records = []
    for n, c in enumerate(cases, 1):
        dest = a.output / f'response-{n:02}.json'
        start = time.monotonic()
        call = subprocess.run([
            'curl', '--silent', '--show-error', '--max-time', '90',
            '--cookie', str(cookie), '--cookie-jar', str(cookie),
            '--output', str(dest), '--write-out', '%{http_code}',
            '--form', 'image=@' + str((a.photos_root / c['photo_file']).resolve()),
            'https://scan.pokesingle.com/api/v1/scans',
        ], capture_output=True, text=True)
        elapsed = round((time.monotonic() - start) * 1000, 2)
        response = json.loads(dest.read_text()) if call.returncode == 0 and call.stdout == '200' else None
        best = (response or {}).get('best_match') or {}
        cid = best.get('card_id')
        cid = 'en:' + cid if cid and ':' not in cid else cid
        row = dict(case_id=c['id'], kind=c['kind'], expected_card_ids=c['expected_card_ids'],
                   photo_sha256=c['sha256'], http_status=call.stdout, curl_exit=call.returncode,
                   upload_to_result_ms=elapsed, response_file=dest.name,
                   card_id=cid, correct=cid in c['expected_card_ids'],
                   status=(response or {}).get('status'), timings_ms=(response or {}).get('timings_ms'))
        records.append(row)
        with (a.output / 'results.jsonl').open('a') as h:
            h.write(json.dumps(row) + '\n')
        print(json.dumps(row), flush=True)
        if not response:
            raise RuntimeError('Staging panel request failed; saved response, no automatic retry')
        # Allow optional grading to settle and avoid a queued panel workload.
        time.sleep(2)
    (a.output / 'summary.json').write_text(json.dumps(dict(
        scans=len(records), correct=sum(r['correct'] for r in records),
        max_upload_to_result_ms=max(r['upload_to_result_ms'] for r in records),
        operational_test_scans_retained=True, catalogue_mutated=False,
        hardware_changed=False, thresholds_changed=False,
    ), indent=2))


if __name__ == '__main__':
    main()
