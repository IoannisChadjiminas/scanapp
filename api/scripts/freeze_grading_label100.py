"""Freeze the manually labelled, unseen 100-photo grading diagnostic."""
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / 'datasets/review/grading-label100-20261002'
OUT = POOL / 'frozen-photos'

def main():
    selection = json.loads((ROOT / 'docs/grading-label100-selection-20261002.json').read_text())['photos']
    truth_path = ROOT / 'docs/grading-label100-manual-truth-20261002.json'
    truth = json.loads(truth_path.read_text())['cases']
    assert len(selection) == len(truth) == 100
    assert {p['id'] for p in selection} == set(truth)
    prior_sha, prior_urls = set(), set()
    for manifest in (ROOT / 'datasets/review').rglob('downloads*.json'):
        if POOL in manifest.parents:
            continue
        for p in json.loads(manifest.read_text()).get('photos', []):
            if p.get('sha256'): prior_sha.add(p['sha256'])
            if p.get('image_url'): prior_urls.add(p['image_url'])
    files = ['app/recognition/grading.py', 'app/recognition/ocr.py',
             'app/recognition/pipeline.py', 'app/schemas.py', 'app/config.py']
    code_hashes = {f: hashlib.sha256((ROOT/'api'/f).read_bytes()).hexdigest() for f in files}
    records, seen = [], set()
    OUT.mkdir(exist_ok=False)
    for p in selection:
        path = POOL / 'corrected-photos' / (p['id']+'.jpg')
        if not path.exists(): path = POOL / 'photos' / (p['id']+'.jpg')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest not in seen | prior_sha, ('duplicate photo', p['id'])
        assert digest != 'a567462f4edd496bdf5cd00da5bbde64131c283e3cf396bfd58c0fac26b13d9a', 'placeholder'
        assert p['image_url'] not in prior_urls, ('previous source', p['id'])
        seen.add(digest)
        shutil.copyfile(path, OUT / path.name)
        records.append({**p, 'sha256':digest, 'path':str((OUT/path.name).relative_to(ROOT)),
                        'review_status':'company_and_overall_grade_visually_transcribed_before_ocr'})
    report = {
        'frozen_at':datetime.now(timezone.utc).isoformat(),
        'test_scope':'Unmodified CardOcr.read_grading on original downloaded photos, not full matching/API HTTP benchmark.',
        'selection':'Six-company convenience sample; grade diversity then source discovery order; not population accuracy.',
        'truth_sha256':hashlib.sha256(truth_path.read_bytes()).hexdigest(),
        'code_hashes':code_hashes, 'exact_prior_photo_overlap':0, 'duplicate_image_hashes':0,
        'photos':records,
    }
    (ROOT/'docs/grading-label100-frozen-sources-20261002.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'frozen_photos':len(records),'exact_prior_photo_overlap':0}))

if __name__ == '__main__': main()
