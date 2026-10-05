"""Public staging HTTP smoke test of phone scans plus completed slab labels."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time


def canonical(cid):
    return 'en:'+cid if cid and ':' not in cid else cid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir',type=Path,required=True)
    p.add_argument('--captures',type=Path,required=True)
    p.add_argument('--frozen-photos',type=Path,required=True)
    args=p.parse_args()
    url='https://scan.pokesingle.com'
    rows=[json.loads(line) for line in (args.audit_dir/'ocr-framing.jsonl').read_text().splitlines()]
    slab_ids={'fresh100_277613285848','fresh100_277888034880','freshextra_0_70889495'}
    selected=[r for r in rows if r['case']['kind']=='phone_capture' or r['case']['id'] in slab_ids]
    assert len(selected)==6
    observed=[]
    with tempfile.TemporaryDirectory(prefix='scanapp-http-audit-') as temp:
        cookie=str(Path(temp)/'cookies.txt')
        def request(path,photo=None):
            command=['curl','--max-time','120','-fsS','-b',cookie,'-c',cookie]
            if photo:
                command+=['-F','image=@'+str(photo)]
            command.append(url+path)
            return json.loads(subprocess.run(command,check=True,capture_output=True).stdout)
        for row in selected:
            case=row['case']
            root=args.captures/'images' if case['kind']=='phone_capture' else args.frozen_photos
            photo=root/Path(case['photo_file']).name
            started=time.perf_counter()
            result=request('/api/v1/scans',photo)
            elapsed=round((time.perf_counter()-started)*1000,2)
            assert canonical(result['best_match']['card_id'])==canonical(row['after']['best_match']['card_id']),case['id']
            if case['kind']=='phone_capture':
                assert canonical(result['best_match']['card_id']) in case['expected_card_ids']
            grading=result['grading']
            if grading['grading_status']=='ungraded':
                assert grading['is_graded'] is False and grading['company'] is None and grading['grade'] is None
                assert grading['source']=='none' and grading['warnings']==[] and grading['label_text']==[]
            elif case['id'] in slab_ids:
                assert grading==row['before']['grading'],case['id']
            assert result['timings_ms']['grading_wait_ms']<100
            assert result['timings_ms']['ocr_passes_count']>=2
            entry={'case':case['id'],'http_ms':elapsed,'response':result}
            observed.append(entry)
            print(json.dumps({'case':case['id'],'card_id':result['best_match']['card_id'],'http_ms':elapsed,
                'ocr_ms':result['timings_ms']['ocr_ms'],'passes':result['timings_ms']['ocr_passes_count'],
                'grading_status':grading['grading_status'],'company':grading['company']}),flush=True)
        saved={r['scan_id']:r for r in request('/api/v1/session/results')['results']}
        for row in observed:
            r=row['response']
            assert saved[r['id']]['grading']==r['grading']
            assert saved[r['id']]['best_match']['card_id']==r['best_match']['card_id']
    (args.audit_dir/'http-smoke.json').write_text(json.dumps(observed,indent=2))
    print(json.dumps({'passed':len(observed),'saved_results_unchanged':True}))


if __name__=='__main__':
    main()
