"""Freeze new-subject physical marketplace photos before scanner inference."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from prepare_holdout2 import dhash, distance

ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT / 'datasets/review/holdout4-20261002'
FROZEN = ROOT / 'datasets/review/holdout4-frozen-20261002'
GROUPS = [
    ([2,3,4,5,6], 'en:swsh12.5gg-GG38', 'GG38/GG70', 'pokemon_full_art'),
    ([9,10,11], 'en:swsh12.5gg-GG42', 'GG42/GG70', 'pokemon_full_art'),
    ([13], 'en:swsh12.5gg-GG54', 'GG54/GG70', 'pokemon_full_art'),
    ([16,17,18], 'en:swsh12.5gg-GG47', 'GG47/GG70', 'pokemon_full_art'),
    ([22,23,24], 'en:swsh12.5gg-GG64', 'GG64/GG70', 'trainer_full_art'),
    ([26,27,28,29,31], 'en:swsh12.5gg-GG66', 'GG66/GG70', 'trainer_full_art'),
    ([36], 'en:swsh12.5gg-GG61', 'GG61/GG70', 'trainer_full_art'),
    ([39,41], 'en:swsh12.5gg-GG23', 'GG23/GG70', 'pokemon_full_art'),
    ([43,45], 'en:swsh12.5gg-GG22', 'GG22/GG70', 'pokemon_full_art'),
    ([46,47], 'en:swsh12.5gg-GG31', 'GG31/GG70', 'pokemon_full_art'),
    ([49,50,51], 'en:base1-20', '20/102', 'standard_frame'),
    ([58,60], 'en:base1-65', '65/102', 'standard_frame'),
    ([63,64,67], 'en:base1-43', '43/102', 'standard_frame'),
    ([68,70,72], 'en:base2-58', '58/64', 'standard_frame'),
    ([78,80], 'en:base1-68', '68/102', 'standard_frame'),
    ([84,85], 'en:base1-62', '62/102', 'standard_frame'),
    ([86,90], 'ja:SV5a-090', '090/066', 'pokemon_full_art'),
    ([97], 'ja:SV4M-088', '088/066', 'pokemon_full_art'),
    ([99,105], 'ja:SV5M-094', '094/071', 'pokemon_full_art'),
    ([111,112,113], 'ja:SV5K-093', '093/071', 'pokemon_full_art'),
]
HOLDERS = {2,3,10,13,17,18,22,23,26,31,36,43,45,58,67,68,72,84,85,111,113}
SLABS = {2,3,10,18,22,23,26,36,43,45,67,113}
STANDS = {4,16,27,41,60,64,90,99,113}
TILT = {5,9,11,13,46,50,63,68,72,80,85,86,105,112}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    records = {}
    paths = {}
    for folder in ('photos',):
        for p in json.loads((POOL / folder / 'downloads.json').read_text())['photos']:
            records[p['id']] = p
            paths[p['id']] = POOL / folder / (p['id']+'.jpg')
    old_sha, old_paths, old_ids, old_urls = set(), [], set(), set()
    for manifest in (ROOT / 'datasets/review').rglob('downloads*.json'):
        if POOL in manifest.parents or FROZEN in manifest.parents:
            continue
        for p in json.loads(manifest.read_text()).get('photos', []):
            if p.get('sha256'): old_sha.add(p['sha256'])
            path = manifest.parent / (p['id']+'.jpg')
            if path.is_file(): old_paths.append((str(path.relative_to(ROOT)), dhash(path)))
    for manifest in (ROOT / 'docs').glob('*photo*sources.json'):
        if manifest.name == 'internet-photo-holdout4-sources.json': continue
        for p in json.loads(manifest.read_text()).get('photos', []):
            if p.get('expected_card_id'): old_ids.add(p['expected_card_id'])
            if p.get('image_url'): old_urls.add(p['image_url'].split('#')[0])
    reference = ROOT / 'data/image-recovery/20261002-official/verified-final-v5'
    art = json.loads((reference / 'artwork/records.json').read_text())
    indexed = {p['card_id'] for p in art}
    reference_sha = {p['reference_sha256'] for p in art}
    db = sqlite3.connect('file:'+str(reference / 'catalog.sqlite')+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    old_names = {row['name'] for cid in old_ids for row in db.execute('SELECT name FROM cards WHERE id=?', (cid,))}
    selected, seen_sha, seen_hash, near, names = [], set(), [], [], set()
    for numbers, cid, printed, layout in GROUPS:
        card = db.execute('SELECT * FROM cards WHERE id=?', (cid,)).fetchone()
        assert card is not None, cid
        names.add(card['name'])
        for number in numbers:
            pid = f'holdout4_{number:03}'
            p, path = records[pid], paths[pid]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert p['download_status'] == 'downloaded'
            assert digest == p['sha256'] and digest not in old_sha | reference_sha | seen_sha, pid
            assert p['image_url'].split('#')[0] not in old_urls, pid
            h = dhash(path)
            for other, oh in old_paths + seen_hash:
                delta = distance(h, oh)
                if delta <= 12: near.append(dict(id=pid, other=other, dhash_hamming_256=delta))
            seen_sha.add(digest)
            seen_hash.append((pid,h))
            conditions = ['physical_background']
            if layout != 'standard_frame': conditions.append('foil_texture_or_reflection')
            if number in HOLDERS: conditions.append('holder_or_sleeve')
            if number in SLABS: conditions.append('slab')
            if number in STANDS: conditions.append('stand')
            if number in TILT: conditions.append('perspective_or_handheld')
            if number == 72: conditions.append('busy_packaging_background')
            selected.append({**{k:p[k] for k in ('id','page_url','image_url')},
                'review_status':'visually_verified','expected_card_id':cid,
                'visible_label':f"{card['name']} {printed}",'language':card['language'],
                'layout':layout,'conditions':conditions,'sha256':digest,
                'truth_in_frozen_artwork_index':cid in indexed})
    assert len(selected) == 50
    assert not {p['expected_card_id'] for p in selected} & old_ids
    assert not names & old_names, names & old_names
    selected_ids = {p['id'] for p in selected}
    manifest = dict(purpose='Fourth untouched 50-photo physical-card Internet holdout, new printings and subjects, labelled before inference.',
        frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        selection='All 114 candidates manually reviewed on 19 contact sheets. Printed title, collector number and language determine labels, not search hints. Fifty physical-photo samples, 20 printing identities, not 50 different printings. References and current scanner frozen.',
        limitations='Convenience marketplace sample; repeated identities, not population-random sampling. Physical authenticity, finish, copy independence and model-pretraining overlap unverified. Local API pipeline, not Flutter camera end-to-end. Internet test photos never indexed or used to tune this run.',
        identity_counts=dict(Counter(p['expected_card_id'] for p in selected)),
        conditions=dict(Counter(v for p in selected for v in p['conditions'])),
        deduplication=dict(old_download_sha_count=len(old_sha), exact_byte_overlap=0,
            old_printing_identity_overlap=[], old_catalogue_name_overlap=[],
            near_duplicate_flags_for_manual_review=near,
            method='SHA256/URL overlap against prior photo manifests, 256-bit whole-image difference hash and visual review. Does not prove absence of every transformed crop or stock-photo reuse.'),
        exclusions=[dict(id=pid,reason='Pre-inference manual photo selection: render/cutout, composite, or eligible reserve not selected for fixed diverse sample.') for pid in records if pid not in selected_ids],
        photos=selected)
    target = ROOT / 'docs/internet-photo-holdout4-sources.json' if args.freeze else POOL / 'selection-draft.json'
    if args.freeze:
        assert not near, 'Resolve near-duplicate flags before freezing'
        assert not FROZEN.exists() and not target.exists()
        (FROZEN / 'photos').mkdir(parents=True)
        for p in selected: shutil.copyfile(paths[p['id']], FROZEN / 'photos' / (p['id']+'.jpg'))
        with (FROZEN / 'photos/downloads.json').open('x') as handle:
            json.dump({'photos':[records[p['id']] for p in selected]}, handle, indent=2)
        with target.open('x') as handle: json.dump(manifest,handle,indent=2,ensure_ascii=False)
    else:
        target.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(photos=len(selected), identities=len(manifest['identity_counts']),
        languages=dict(Counter(p['language'] for p in selected)),
        layouts=dict(Counter(p['layout'] for p in selected)),
        artwork_coverage=sum(p['truth_in_frozen_artwork_index'] for p in selected),
        near=near, manifest_sha256=hashlib.sha256(target.read_bytes()).hexdigest()),indent=2))

if __name__ == '__main__': main()
