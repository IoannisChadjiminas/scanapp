"""Pre-inference stratified selection; checksums and provenance, never predictions."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from prepare_holdout2 import dhash, distance

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT/'datasets/review/grading-fresh100-20261002'
QUOTAS = {'raw':50,'psa':10,'beckett':8,'cgc':8,'tag':8,'ace':7,'ags':9}

def asset(url):
    return urlsplit(url).path.split('/s-l')[0].replace('/thumbs/images/','/images/')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    args = parser.parse_args()
    truth = json.loads((ROOT/'docs/grading-fresh100-pre-inference-annotations-20261002.json').read_text())['cases']
    downloads = {}
    for manifest in sorted(POOL.glob('photos-*/downloads.json')):
        for p in json.loads(manifest.read_text())['photos']:
            if p['download_status']=='downloaded': downloads[p['id']] = p
    prior_sha, prior_assets, prior_paths = set(),set(),{}
    for manifest in (ROOT/'datasets/review').rglob('downloads*.json'):
        if POOL in manifest.parents: continue
        for p in json.loads(manifest.read_text()).get('photos',[]):
            if p.get('sha256'): prior_sha.add(p['sha256'])
            if p.get('image_url'): prior_assets.add(asset(p['image_url']))
            path = manifest.parent/(p['id']+'.jpg')
            if path.is_file() and p.get('sha256') not in prior_paths:
                prior_paths[p.get('sha256')] = path
    references = json.loads((ROOT/'data/image-recovery/20261002-official/verified-final-v5/artwork/records.json').read_text())
    prior_sha.update(p['reference_sha256'] for p in references)
    grouped, seen, exclusions = defaultdict(list),set(),[]
    for pid,known in truth.items():
        p = downloads[pid]
        path = ROOT/p['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == p['sha256']
        if digest in prior_sha or asset(p['image_url']) in prior_assets or digest in seen:
            exclusions.append({'id':pid,'reason':'prior_or_duplicate_photo_asset'})
            continue
        seen.add(digest)
        grouped[known['company'] or 'raw'].append((p,known))
    selected = []
    # Round-robin among observed identities/grades reduces repeated-printing
    # dominance. All choices are made before inference, using manual truth only.
    for company,quota in QUOTAS.items():
        buckets = defaultdict(list)
        for p,known in grouped[company]:
            buckets[(known['name'],known['number'],known['language'],known['grade'])].append((p,known))
        chosen = []
        while len(chosen)<quota:
            progressed = False
            for bucket in buckets.values():
                if bucket and len(chosen)<quota:
                    chosen.append(bucket.pop(0)); progressed=True
            assert progressed, ('insufficient pre-reviewed photos',company)
        selected.extend(chosen)
    ids = {p['id'] for p,_ in selected}
    exclusions.extend({'id':pid,'reason':'unreviewed_or_reserve_not_selected_before_inference'}
                      for pid in downloads if pid not in ids and pid not in {p['id'] for p in exclusions})
    old_hashes = [(str(p.relative_to(ROOT)),dhash(p)) for p in prior_paths.values()]
    near,seen_hash = [],[]
    for p,_ in selected:
        h = dhash(ROOT/p['path'])
        for other,oh in old_hashes+seen_hash:
            delta = distance(h,oh)
            if delta<=12: near.append({'id':p['id'],'other':other,'dhash_hamming_256':delta})
        seen_hash.append((p['id'],h))
    sources = {'frozen_at':datetime.now(timezone.utc).isoformat(),
        'selection':'Manual visual truth before inference; fixed 50 raw / 50 slabs, six grader quotas, identity/grade round-robin.',
        'limitations':'Convenience seller-photo sample; not random population or live Flutter/camera tests. Distinct photos may share cards, sellers or physical copies. Authenticity, editing and model-pretraining overlap unverified. Finish/raw condition not scored.',
        'exact_prior_asset_overlap':0,'near_duplicate_flags':near,
        'deduplication_method':'SHA256, normalized marketplace asset URL and 256-bit whole-image dHash; not exhaustive crop reuse detection.',
        'strata':QUOTAS,'exclusions':exclusions,
        'photos':[{**p,'conditions':['slab'] if known['kind']=='slab' else ['raw_card'],
            'review_status':'visually_verified','manual_truth':known} for p,known in selected]}
    if not args.freeze:
        (POOL/'selection-draft.json').write_text(json.dumps(sources,indent=2)+'\n')
    else:
        assert not near, 'Resolve near-photo reuse before freezing'
        out = POOL/'frozen-photos';out.mkdir(exist_ok=False)
        truth_path = ROOT/'docs/grading-fresh100-manual-truth-20261002.json'
        with truth_path.open('x') as handle:
            json.dump({'annotation_method':'Visually transcribed before inference','cases':{p['id']:known for p,known in selected}},handle,indent=2)
        sources['truth_sha256'] = hashlib.sha256(truth_path.read_bytes()).hexdigest()
        for p in sources['photos']:
            destination = out/(p['id']+'.jpg')
            shutil.copyfile(ROOT/p['path'],destination)
            p['path'] = str(destination.relative_to(ROOT))
        with (ROOT/'docs/grading-fresh100-frozen-sources-20261002.json').open('x') as handle:
            json.dump(sources,handle,indent=2)
    print(json.dumps({'selected':len(selected),'strata':dict(Counter(k['company'] or 'raw' for _,k in selected)),
                     'near':near,'exact_reuse_exclusions':[p for p in exclusions if p['reason']=='prior_or_duplicate_photo_asset']},indent=2))

if __name__=='__main__': main()
