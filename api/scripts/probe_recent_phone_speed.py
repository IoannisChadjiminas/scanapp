"""Serial staging diagnostic scans; never confirm results or edit catalogue."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from app.recognition.artifacts import sha256_file


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--photos',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    cases=json.loads((args.photos/'cases.json').read_text())
    for c in cases: assert sha256_file(args.photos/c['photo_file'])==c['sha256']
    with tempfile.TemporaryDirectory(prefix='scan-speed029-') as temp, args.output.open('x') as output:
        cookie=Path(temp)/'session.private'
        for c in cases:
            dest=Path(temp)/'response.json';start=time.perf_counter()
            code=subprocess.check_output(['curl','--silent','--show-error','--max-time','90',
                '--cookie',str(cookie),'--cookie-jar',str(cookie),'--output',str(dest),
                '--write-out','%{http_code}','--form','image=@'+str((args.photos/c['photo_file']).resolve()),
                'https://scan.pokesingle.com/api/v1/scans'],text=True)
            assert code=='200',code
            response=json.loads(dest.read_text())
            record=dict(case=c,response=response,http_ms=(time.perf_counter()-start)*1000)
            output.write(json.dumps(record)+'\n');output.flush()
            print(json.dumps(dict(id=c['id'],status=response['status'],
                best=(response.get('best_match')or{}).get('card_id'),http_ms=round(record['http_ms']),
                ocr_ms=round(response['timings_ms']['ocr_ms']))),flush=True)
            time.sleep(2)


if __name__=='__main__':main()
