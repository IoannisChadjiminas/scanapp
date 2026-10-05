"""Freeze the second independent, manually reviewed 50-photo sample."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'datasets/review/holdout2-20261002'
GROUPS = [
    ([1,3,4,5], 'en:swsh7-205', '205/203', 'pokemon_full_art'),
    ([8,9,10,11], 'en:swsh7-209', '209/203', 'pokemon_full_art'),
    ([13,15,16], 'en:swsh6-177', '177/198', 'pokemon_full_art'),
    ([20,21,23], 'en:swsh10-172', '172/189', 'pokemon_full_art'),
    ([22], 'en:swsh10-072', '072/189', 'standard_frame'),
    ([24,26,29,30], 'en:swsh12.5gg-GG68', 'GG68/GG70', 'pokemon_full_art'),
    ([32,34,35,36], 'ja:SV3-134', '134/108', 'pokemon_full_art'),
    ([43], 'ja:SV8a-126', '126/187', 'standard_frame'),
    ([45], 'ja:SV8a-223', '223/187', 'pokemon_full_art'),
    ([46], 'ja:SV8a-224', '224/187', 'pokemon_full_art'),
    ([48,49,51], 'ja:SV2D-096', '096/071', 'trainer_full_art'),
    ([52], 'ja:SV2D-091', '091/071', 'trainer_full_art'),
    ([54,56,57], 'ja:S8a-001', '001/028', 'standard_frame'),
    ([58,60,62], 'en:swsh12.5gg-GG60', 'GG60/GG70', 'trainer_full_art'),
    ([63,69,71], 'en:base5-4', '4/82', 'standard_frame'),
    ([75,79,82], 'en:base4-87', '87/130', 'standard_frame'),
    ([85,86,89,90], 'en:sv01-036', '036/198', 'standard_frame'),
    ([93,95,96,98], 'en:swsh7-218', '218/203', 'pokemon_full_art'),
]
HOLDERS = {1,4,5,9,11,15,16,21,23,29,30,43,45,48,52,56,57,60,62,63,75,82,85,86,90,95,96}
STANDS = {1,11,15,16,35,46,56,60,62,82,85,86,95}
GLARE = {1,3,4,8,10,11,13,15,16,21,26,29,30,35,36,43,45,48,49,51,52,58,60,62,71,90,93,95,96,98}
TILT = {1,10,13,24,43,56,69,79,85,93,98}

def dhash(path):
    with Image.open(path) as image:
        pixels = np.asarray(ImageOps.exif_transpose(image).convert('L').resize((17,16)))
    return np.packbits(pixels[:,1:] > pixels[:,:-1]).tobytes()

def distance(a,b):
    return sum((x^y).bit_count() for x,y in zip(a,b))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    downloads = json.loads((PRIVATE / 'photos/downloads.json').read_text())['photos']
    records = {p['id']:p for p in downloads}
    old_sha, old_paths = set(), []
    for manifest in (ROOT / 'datasets/review').rglob('downloads*.json'):
        if PRIVATE in manifest.parents:
            continue
        for p in json.loads(manifest.read_text()).get('photos',[]):
            if p.get('sha256'):
                old_sha.add(p['sha256'])
            path = manifest.parent / (p['id']+'.jpg')
            if path.is_file():
                old_paths.append((str(path.relative_to(ROOT)),dhash(path)))
    old_ids, old_urls = set(), set()
    for filename in ('internet-photo-50-sources.json','physical-photo-holdout-sources.json',
                     'physical-photo-extra-sources.json','internet-photo-fresh50-sources.json'):
        for p in json.loads((ROOT / 'docs' / filename).read_text())['photos']:
            old_ids.add(p['expected_card_id'])
            old_urls.add(p['image_url'].split('#')[0])
    art_records = json.loads((ROOT / 'data/image-recovery/20261002-official/verified-final-v5/artwork/records.json').read_text())
    reference_sha = {p['reference_sha256'] for p in art_records}
    indexed = {p['card_id'] for p in art_records}
    catalogue = sqlite3.connect('file:'+str(ROOT / 'data/image-recovery/20261002-official/verified-final-v5/catalog.sqlite')+'?mode=ro',uri=True)
    catalogue.row_factory = sqlite3.Row
    selected, seen_sha, seen_hash, near = [], set(), [], []
    for numbers,card_id,printed,layout in GROUPS:
        card = catalogue.execute('SELECT * FROM cards WHERE id=?',(card_id,)).fetchone()
        assert card is not None, card_id
        for number in numbers:
            pid = f'holdout2_{number:03}'
            p = records[pid]
            assert p['download_status'] == 'downloaded'
            path = PRIVATE / 'photos' / (pid+'.jpg')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == p['sha256'] and digest not in old_sha | reference_sha | seen_sha
            assert p['image_url'].split('#')[0] not in old_urls
            h = dhash(path)
            for other,oh in old_paths + seen_hash:
                delta = distance(h,oh)
                if delta <= 12:
                    near.append(dict(id=pid,other=other,dhash_hamming_256=delta))
            seen_sha.add(digest)
            seen_hash.append((pid,h))
            conditions = ['background']
            if layout != 'standard_frame': conditions.append('foil_texture')
            if number in HOLDERS: conditions.append('holder_or_sleeve')
            if number in STANDS: conditions.append('stand')
            if number in GLARE: conditions.append('glare_or_strong_reflection')
            if number in TILT: conditions.append('perspective_tilt')
            if number in (4,62,96): conditions.append('slab')
            selected.append({**{k:p[k] for k in ('id','page_url','image_url')},
                'review_status':'visually_verified','expected_card_id':card_id,
                'visible_label':f"{card['name']} {printed}",'language':card['language'],
                'layout':layout,'conditions':conditions,'sha256':digest,
                'truth_in_frozen_artwork_index':card_id in indexed})
    assert len(selected) == 50
    excluded = []
    selected_ids = {p['id'] for p in selected}
    for p in downloads:
        if p['id'] not in selected_ids:
            n = int(p['id'].rsplit('_',1)[1])
            reason = ('digital_reference_or_product_render' if n in (33,50,53,87,88) else
                      'eligible_photo_not_selected_before_inference_for_fixed_diverse_50')
            excluded.append({'id':p['id'],'reason':reason})
    manifest = dict(purpose='Second fresh 50-photo Internet camera-image holdout, labels frozen before inference.',
        frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        selection='Manual visible title/collector/language review of all 98 candidate photos on 17 contact sheets. Eighteen printing identities; selection made without scanner predictions. Search hints corrected for Machamp and Eevee/Iono printings.',
        limitations='Convenience sample, not random population sampling. Repeated identities and marketplace sources. Camera photos of physical cards, not Flutter/live API tests. Authenticity, finish, physical-copy independence and model-pretraining overlap unverified. Images never indexed or used to tune this run.',
        identity_counts=dict(Counter(p['expected_card_id'] for p in selected)),
        conditions=dict(Counter(v for p in selected for v in p['conditions'])),
        deduplication=dict(old_download_sha_count=len(old_sha),exact_byte_overlap=0,
            old_printing_identity_overlap=sorted({p['expected_card_id'] for p in selected} & old_ids),
            near_duplicate_flags_for_manual_review=near,
            method='SHA256/URL overlap, 256-bit whole-image difference hash plus manual review; not exhaustive crop reuse detection.'),
        exclusions=excluded,photos=selected)
    target = ROOT / 'docs/internet-photo-holdout2-sources.json' if args.freeze else PRIVATE / 'selection-draft.json'
    if args.freeze:
        assert not near, 'Review and resolve near-duplicate flags before freezing'
        with target.open('x') as handle: json.dump(manifest,handle,indent=2,ensure_ascii=False)
    else:
        target.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'photos':len(selected),'identities':len(manifest['identity_counts']),
        'languages':dict(Counter(p['language'] for p in selected)),
        'artwork_coverage':sum(p['truth_in_frozen_artwork_index'] for p in selected),
        'old_identity_overlap':manifest['deduplication']['old_printing_identity_overlap'],
        'near':near,'manifest_sha256':hashlib.sha256(target.read_bytes()).hexdigest()},indent=2))

if __name__ == '__main__': main()
