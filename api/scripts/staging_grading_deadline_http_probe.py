"""Small live staging smoke test; uses only an isolated test session."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--photo-root', type=Path, help='Alternate directory containing the frozen photos')
    parser.add_argument('--url', default='https://scan.pokesingle.com')
    args = parser.parse_args()
    assert args.url == 'https://scan.pokesingle.com', 'This probe is staging-only'
    records = [json.loads(line) for line in (args.audit_dir/'combined/parallel-paired.jsonl').read_text().splitlines()]
    chosen = {'fresh100_205408031074', 'freshextra_0_70889495', 'fresh100_205148259527'}
    chosen.add(next(r['case']['id'] for r in records if r['case']['kind'] == 'raw'))
    for company in ('psa', 'beckett'):
        chosen.add(next(r['case']['id'] for r in records if r['parallel']['grading']['company'] == company))
    selected = [r for r in records if r['case']['id'] in chosen]
    # Use the same normal curl transport as the staging health checks. The
    # edge rejects the Python urllib client before requests reach the API.
    cookies = tempfile.TemporaryDirectory(prefix='scanapp-http-audit-')
    cookie_path = str(Path(cookies.name)/'cookies.txt')
    def request(path, photo=None):
        command = ['curl', '--max-time', '120', '-fsS', '-b', cookie_path, '-c', cookie_path]
        if photo is not None:
            command += ['-F', 'image=@'+str(photo)]
        command.append(args.url+path)
        return json.loads(subprocess.run(command, check=True, capture_output=True).stdout)
    observed = []
    for record in selected:
        case = record['case']
        photo = (args.photo_root/Path(case['photo_file']).name) if args.photo_root else (args.audit_dir/case['photo_file'])
        started = time.perf_counter()
        result = request('/api/v1/scans', photo)
        old = record['serial']
        assert result['best_match']['card_id'] == old['best_match']['card_id'], case['id']
        grading = result['grading']
        if grading['grading_status'] == 'ungraded':
            assert grading['company'] is None and grading['grade'] is None
            assert grading['is_graded'] is False and grading['warnings'] == []
            assert grading['source'] == 'none' and grading['label_text'] == []
        else:
            assert grading == old['grading'], case['id']
        assert result['timings_ms']['grading_wait_ms'] < 100
        assert not any('fallback' in k for k in grading)
        entry = {'case': case['id'], 'http_ms': round((time.perf_counter()-started)*1000,2), 'response': result}
        observed.append(entry)
        print(json.dumps({'case': case['id'], 'http_ms': entry['http_ms'], 'card_id': result['best_match']['card_id'],
                          'grading_status': grading['grading_status'], 'company': grading['company']}), flush=True)
    saved = {r['scan_id']: r for r in request('/api/v1/session/results')['results']}
    for entry in observed:
        result = entry['response']
        assert saved[result['id']]['grading'] == result['grading'], 'A late job must not overwrite Raw'
    (args.audit_dir/'http-smoke.json').write_text(json.dumps(observed, indent=2))
    cookies.cleanup()
    print(json.dumps({'passed': len(observed), 'persisted_grading_unchanged': True}))


if __name__ == '__main__':
    main()
