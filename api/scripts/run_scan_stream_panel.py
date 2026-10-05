"""One upload per case through the public staging gateway; no confirmations."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--panel', type=Path, required=True)
    p.add_argument('--photos-root', type=Path, required=True)
    p.add_argument('--extra-photos', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    cases = [(c, a.photos_root) for c in json.loads(a.panel.read_text())]
    if a.extra_photos:
        cases.extend((c, a.extra_photos) for c in json.loads((a.extra_photos/'cases.json').read_text()))
    for c, root in cases: assert sha256_file(root/c['photo_file']) == c['sha256']
    rows = []
    with httpx.Client(timeout=90, follow_redirects=False) as client, a.output.open('x') as handle:
        for case, root in cases:
            start = time.perf_counter(); events = []
            with (root/case['photo_file']).open('rb') as photo, client.stream('POST',
                'https://scan.pokesingle.com/api/v1/scans',
                data={'stream_results':'true', 'language':'auto'},
                files={'image':(case['photo_file'], photo, 'image/jpeg')}) as response:
                response.raise_for_status()
                assert 'application/x-ndjson' in response.headers.get('content-type','')
                for line in response.iter_lines():
                    if not line: continue
                    event = json.loads(line); event['received_ms'] = (time.perf_counter()-start)*1000
                    events.append(event)
                    if event['type'] == 'error': raise RuntimeError('Stream error: '+event['code'])
            final = [e for e in events if e['type']=='final']; previews = [e for e in events if e['type']=='provisional']
            assert len(final)==1 and len(previews)<=1
            for e in previews:
                assert e['provisional'] and not e['printing_confirmed'] and e['requires_confirmation']
                assert 'id' not in e and all('cardmarket_url' not in c for c in e['candidates'])
            result = final[0]['result']; cid = (result.get('best_match') or {}).get('card_id')
            normalized = 'en:'+cid if cid and ':' not in cid else cid
            assert not case['expected_card_ids'] or normalized in case['expected_card_ids'], case['id']
            row = dict(case=case, response=result, events=events,
                first_provisional_ms=previews[0]['received_ms'] if previews else None,
                http_ms=(time.perf_counter()-start)*1000)
            rows.append(row); handle.write(json.dumps(row)+'\n'); handle.flush()
            print(json.dumps(dict(id=case['id'],card_id=cid,status=result['status'],
                preview_ms=round(row['first_provisional_ms']) if previews else None,
                http_ms=round(row['http_ms']))), flush=True)
            time.sleep(2)
    previews = [r['first_provisional_ms'] for r in rows if r['first_provisional_ms'] is not None]
    summary = dict(scans=len(rows), previews=len(previews), final_results=len(rows),
        median_preview_ms=statistics.median(previews) if previews else None,
        max_preview_ms=max(previews) if previews else None,
        median_total_ms=statistics.median(r['http_ms'] for r in rows),
        max_total_ms=max(r['http_ms'] for r in rows),
        catalogue_mutated=False, operational_test_scans_retained=True,
        limitations='Single-pass small live sample; provisional identities can change after OCR. Not a five-second maximum or unseen accuracy guarantee.')
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)); print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
