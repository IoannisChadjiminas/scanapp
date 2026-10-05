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
POOL = ROOT / 'datasets/review/holdout3-20261002'
FROZEN = ROOT / 'datasets/review/holdout3-frozen-20261002'
GROUPS = [
    ([2], 'en:swsh5-155', '155/163', 'pokemon_full_art'),
    ([4,5,6], 'en:sv03-205', '205/197', 'pokemon_full_art'),
    ([8,9,10], 'en:swsh12.5gg-GG05', 'GG05/GG70', 'pokemon_full_art'),
    ([12,14], 'en:swsh12.5gg-GG46', 'GG46/GG70', 'pokemon_full_art'),
    ([16,17,18], 'en:swsh12.5gg-GG41', 'GG41/GG70', 'pokemon_full_art'),
    ([21,22], 'en:swsh12.5gg-GG56', 'GG56/GG70', 'pokemon_full_art'),
    ([23,24,25], 'en:sv01-252', '252/198', 'trainer_full_art'),
    ([27,28,30], 'en:sv02-266', '266/193', 'trainer_full_art'),
    ([31,32], 'en:base1-66', '66/102', 'standard_frame'),
    ([35,37], 'en:base1-53', '53/102', 'standard_frame'),
    ([39,40], 'en:base1-60', '60/102', 'standard_frame'),
    ([45], 'en:base3-54', '54/62', 'standard_frame'),
    ([56,58], 'ja:SV1S-080', '080/078', 'pokemon_full_art'),
    ([65], 'ja:SV4a-339', '339/190', 'pokemon_full_art'),
    ([66], 'ja:SV3-031', '031/108', 'standard_frame'),
    ([67,68,70], 'ja:SV3-110', '110/108', 'pokemon_full_art'),
    ([73], 'ja:SV3-136', '136/108', 'pokemon_full_art'),
    ([75], 'ja:SV2D-092', '092/071', 'pokemon_full_art'),
    ([83], 'ja:SV6a-077', '077/064', 'pokemon_full_art'),
    ([85,86], 'en:svp-051', 'SVP 051', 'pokemon_full_art'),
    ([89,91], 'en:swsh12.5gg-GG36', 'GG36/GG70', 'pokemon_full_art'),
    ([92,95], 'en:swsh12.5gg-GG55', 'GG55/GG70', 'pokemon_full_art'),
    ([96,99], 'en:swsh12.5gg-GG48', 'GG48/GG70', 'pokemon_full_art'),
    ([100,102], 'ja:SV1V-102', '102/078', 'pokemon_full_art'),
    ([103], 'en:svp-028', 'SVP 028', 'pokemon_full_art'),
    ([107], 'ja:SV7-131', '131/102', 'trainer_full_art'),
    ([106], 'ja:SV7-124', '124/102', 'trainer_full_art'),
]
HOLDERS = {5,9,16,17,25,27,67,68,70,85,89,100,102,103,107}
SLABS = {25,67,68,70,100,102,103,107}
STANDS = {5,8,28,92,96,107}
TILT = {6,27,28,30,99,103}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    records = {}
    paths = {}
    for folder in ('photos', 'more-photos'):
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
        if manifest.name == 'internet-photo-holdout3-sources.json': continue
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
            pid = f'holdout3_{number:03}'
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
            if number == 103: conditions.append('other_cards_in_background')
            selected.append({**{k:p[k] for k in ('id','page_url','image_url')},
                'review_status':'visually_verified','expected_card_id':cid,
                'visible_label':f"{card['name']} {printed}",'language':card['language'],
                'layout':layout,'conditions':conditions,'sha256':digest,
                'truth_in_frozen_artwork_index':cid in indexed})
    assert len(selected) == 50
    assert not {p['expected_card_id'] for p in selected} & old_ids
    assert not names & old_names, names & old_names
    selected_ids = {p['id'] for p in selected}
    manifest = dict(purpose='Third untouched 50-photo physical-card Internet holdout, new printings and subjects, labelled before inference.',
        frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        selection='All 107 candidates manually reviewed on 18 contact sheets. Printed title, collector number and language determine labels, not search hints. Fifty physical-photo samples, 27 printing identities, not 50 different printings. References and current scanner frozen.',
        limitations='Convenience marketplace sample; repeated identities, not population-random sampling. Physical authenticity, finish, copy independence and model-pretraining overlap unverified. Local API pipeline, not Flutter camera end-to-end. Internet test photos never indexed or used to tune this run.',
        identity_counts=dict(Counter(p['expected_card_id'] for p in selected)),
        conditions=dict(Counter(v for p in selected for v in p['conditions'])),
        deduplication=dict(old_download_sha_count=len(old_sha), exact_byte_overlap=0,
            old_printing_identity_overlap=[], old_catalogue_name_overlap=[],
            near_duplicate_flags_for_manual_review=near,
            method='SHA256/URL overlap against prior photo manifests, 256-bit whole-image difference hash and visual review. Does not prove absence of every transformed crop or stock-photo reuse.'),
        exclusions=[dict(id=pid,reason='Pre-inference manual photo selection: render/cutout, composite, or eligible reserve not selected for fixed diverse sample.') for pid in records if pid not in selected_ids],
        photos=selected)
    target = ROOT / 'docs/internet-photo-holdout3-sources.json' if args.freeze else POOL / 'selection-draft.json'
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
