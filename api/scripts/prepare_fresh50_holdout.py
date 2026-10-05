"""Freeze independently reviewed fresh listing photos before scanner evaluation."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
GROUPS = [
    ([1, 2, 3, 4, 5, 6], 'en:swsh11-180', 'Aerodactyl V 180/196', 'pokemon_full_art'),
    ([9], 'en:swsh11-186', 'Giratina V 186/196', 'pokemon_full_art'),
    ([10, 11, 12, 13, 18], 'en:base1-58', 'Pikachu 58/102, shadowed, no first-edition stamp', 'standard_frame'),
    ([14, 15, 17, 19, 66, 67, 68, 69], 'en:sv03.5-203', "Erika's Invitation MEW 203/165", 'trainer_full_art'),
    ([20, 21, 22, 24, 25, 26, 27, 28], 'en:swsh12.5gg-GG44', 'Mewtwo VSTAR GG44/GG70', 'pokemon_full_art'),
    ([31, 32, 33, 34, 35, 36], 'ja:SV2a-205', 'ミュウex sv2a 205/165', 'pokemon_full_art'),
    ([40], 'ja:SV1a-080', 'コイキング sv1a 080/073', 'pokemon_full_art'),
    ([41, 42, 45, 46, 48, 49], 'en:sv03.5-201', 'Alakazam ex MEW 201/165', 'pokemon_full_art'),
    ([51], 'en:sv03.5-202', 'Zapdos ex MEW 202/165', 'pokemon_full_art'),
    ([52, 53, 58, 60], 'en:sv01-245', 'Gardevoir ex SVI 245/198', 'pokemon_full_art'),
    ([70, 71, 73, 74], 'ja:SV1S-101', 'サーナイトex sv1S 101/078', 'pokemon_full_art'),
]


def dhash(path):
    with Image.open(path) as image:
        pixels = np.asarray(ImageOps.exif_transpose(image).convert('L').resize((17, 16)))
    return np.packbits(pixels[:, 1:] > pixels[:, :-1]).tobytes()


def main():
    private = ROOT / 'datasets/review/fresh50-20261002'
    downloaded = json.loads((private / 'photos/downloads.json').read_text())['photos']
    records = {p['id']: p for p in downloaded}
    old_sha, old_paths, old_ids, old_urls = set(), [], set(), set()
    for manifest in (ROOT / 'datasets/review').rglob('downloads*.json'):
        if private in manifest.parents:
            continue
        for p in json.loads(manifest.read_text()).get('photos', []):
            if p.get('sha256'):
                old_sha.add(p['sha256'])
            path = manifest.parent / (p['id'] + '.jpg')
            if path.exists():
                old_paths.append((str(path.relative_to(ROOT)), dhash(path)))
    for name in ('internet-photo-50-sources.json', 'physical-photo-holdout-sources.json', 'physical-photo-extra-sources.json'):
        for p in json.loads((ROOT / 'docs' / name).read_text())['photos']:
            old_ids.add(p['expected_card_id'])
            old_urls.add(p['image_url'].split('#')[0])
    references = json.loads((ROOT / 'data/artwork-candidates/20261002-recovery/records.json').read_text())
    reference_sha = {p['reference_sha256'] for p in references}
    indexed_ids = {p['card_id'] for p in references}
    selected, seen_sha, seen_hash, near = [], set(), [], []
    for numbers, card_id, label, layout in GROUPS:
        assert card_id not in old_ids, card_id
        for number in numbers:
            pid = f'fresh_{number:03}'
            p = records[pid]
            assert p['download_status'] == 'downloaded'
            path = private / 'photos' / (pid + '.jpg')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == p['sha256']
            assert digest not in old_sha | reference_sha | seen_sha
            assert p['image_url'].split('#')[0] not in old_urls
            h = dhash(path)
            for other, oh in old_paths + seen_hash:
                distance = sum((a ^ b).bit_count() for a, b in zip(h, oh))
                if distance <= 12:
                    near.append({'id': pid, 'other': other, 'dhash_hamming_256': distance})
            seen_sha.add(digest)
            seen_hash.append((pid, h))
            conditions = ['background']
            if layout != 'standard_frame':
                conditions.append('foil_texture')
            if number in (1, 2, 6, 9, 14, 15, 19, 25, 27, 31, 33, 35, 36, 46, 51, 53, 60, 67, 68, 69):
                conditions.append('holder_or_sleeve')
            if number in (6, 15, 19, 35, 51, 60, 73):
                conditions.append('stand')
            if number in (10, 21, 40, 53, 58):
                conditions.append('perspective_tilt')
            if number in (4, 5, 21, 34, 40, 45, 46, 51, 52, 58, 66, 67, 69, 74):
                conditions.append('glare_or_strong_reflection')
            if number in (46, 48, 58):
                conditions.append('hand')
            if number == 58:
                conditions.append('slab')
            selected.append({**{k: p[k] for k in ('id', 'page_url', 'image_url')},
                'review_status': 'visually_verified', 'expected_card_id': card_id,
                'visible_label': label, 'language': 'ja' if card_id.startswith('ja:') else 'en',
                'layout': layout, 'conditions': conditions, 'sha256': digest,
                'truth_in_frozen_artwork_index': card_id in indexed_ids})
    assert len(selected) == 50
    manifest = {'purpose': 'Fresh 50-photo convenience holdout, labels frozen before inference.',
        'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'selection': 'Manual visible name/number/language review of 79 search candidates. Eleven printing identities, none in the previous 69. Balance across selected available identities; not random sampling. No scanner predictions consulted.',
        'exclusions': 'Exact duplicates 62-65; previously tested Espeon identity 23/30; near duplicate 72/75; apparently digital product image 78. Remaining eligible extras omitted for a fixed 50-photo identity mix before inference.',
        'limitations': 'Internet listing photos, not independently captured app-camera input. Seller authenticity, finish, editing and model-pretraining overlap unverified. Repeated identities/listing-category sources reduce statistical independence. Finish is not a truth label. No rescan, tuning or indexing of holdout images.',
        'deduplication': {'old_download_sha_count': len(old_sha), 'exact_byte_overlap': 0,
            'old_printing_identity_overlap': 0, 'near_duplicate_flags_for_manual_review': near,
            'method': 'SHA256 and whole-image 256-bit difference hash; manual contact-sheet review. Not an exhaustive crop/asset reuse proof.'},
        'identity_counts': dict(Counter(p['expected_card_id'] for p in selected)),
        'photos': selected}
    destination = ROOT / 'docs/internet-photo-fresh50-sources.json'
    with destination.open('x') as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
    print(json.dumps({'photos': len(selected), 'identities': len(manifest['identity_counts']),
        'languages': dict(Counter(p['language'] for p in selected)), 'near_flags': near,
        'artwork_coverage': sum(p['truth_in_frozen_artwork_index'] for p in selected),
        'source_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
