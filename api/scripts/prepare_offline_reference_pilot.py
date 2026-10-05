"""Prepare one manually verified existing-card reference in a disposable snapshot.
No cloud writes. Does not approve publication or substitute for heldout tests.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import cv2
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file, validate_embeddings
from app.recognition.artwork import PROFILES, crop_profile
from app.recognition.embed import DinoEmbedder
from app.recognition.reference_features import build_reference_bundle, catalogue_signature
from assemble_reference_feature_release import assemble


def validate_selection(card, selection):
    if (selection.get('verification') != 'manual_visual' or not selection.get('identity_approved')
            or selection.get('readable_contradictions') is not False):
        raise ValueError('An explicit manually verified source selection is required')
    if card['has_image'] or card['image_path']:
        raise ValueError('Pilot only adds a missing reference, never replaces an existing one')
    if selection.get('unexpected_stamp_observed') is not False:
        raise ValueError('Stamp evidence must be reviewed explicitly')
    for key in ('name', 'language', 'set_id', 'collector_number', 'cardmarket_url'):
        if card[key] != selection[key]:
            raise ValueError('Unverified identity or mapping field: ' + key)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent', type=Path, required=True)
    p.add_argument('--parent-features', type=Path, required=True)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); cv2.setNumThreads(1)
    selection = json.loads(a.selection.read_text())
    if selection.get('verification') != 'manual_visual' or not selection.get('identity_approved'):
        raise ValueError('An explicit manually verified source selection is required')
    source = Path(selection['source_file'])
    if sha256_file(source) != selection['sha256']:
        raise ValueError('Source selection checksum mismatch')
    parent_manifest = json.loads((a.parent / 'vectors/manifest.json').read_text())
    if sha256_file(a.model) != parent_manifest['dinov2_sha256']:
        raise ValueError('Pinned model mismatch')
    old = sqlite3.connect((a.parent / 'catalog.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    old.row_factory = sqlite3.Row
    rows = [dict(r) for r in old.execute('SELECT * FROM cards')]
    card = next(r for r in rows if r['id'] == selection['id'])
    validate_selection(card, selection)
    a.output.mkdir(parents=True, exist_ok=False)
    destination = '/data/reference-images/recovered/' + selection['id'].replace(':', '_') + source.suffix
    target = sqlite3.connect(a.output / 'catalog.sqlite')
    old.backup(target)
    target.execute('UPDATE cards SET image_path=?,has_image=1,remote_image_url=? WHERE id=?',
                   (destination, selection['image_url'], selection['id']))
    target.commit(); target.close(); old.close()
    updated = [dict(r, image_path=destination, has_image=1, remote_image_url=selection['image_url'])
               if r['id'] == card['id'] else r for r in rows]
    model = DinoEmbedder(str(a.model), 1, 1)
    with Image.open(source) as opened:
        image = opened.convert('RGB')
    full = a.output / 'vectors'; full.mkdir()
    matrix = np.load(a.parent / 'vectors/embeddings.npy', allow_pickle=False)
    ids = np.load(a.parent / 'vectors/embedding_card_ids.npy', allow_pickle=False)
    if (sha256_file(a.parent / 'vectors/embeddings.npy') != parent_manifest['embeddings_sha256'] or
            sha256_file(a.parent / 'vectors/embedding_card_ids.npy') != parent_manifest['ids_sha256'] or
            card['id'] in ids):
        raise ValueError('Parent snapshot drifted')
    vector = model.embed(image, 'pad')
    combined = np.concatenate([matrix, vector[None, :]])
    new_ids = np.asarray(ids.tolist() + [card['id']])
    validate_embeddings(combined, new_ids)
    assert np.array_equal(combined[:-1], matrix)
    np.save(full / 'embeddings.npy', combined); np.save(full / 'embedding_card_ids.npy', new_ids)
    # Square is prepared separately and is never silently used as the pad index.
    np.save(a.output / 'new-square-vector.npy', model.embed(image, 'square'))
    manifest = deepcopy(parent_manifest)
    manifest.update(indexed_count=len(new_ids), indexed_ids=new_ids.tolist(),
                    missing_images=manifest['missing_images']-1,
                    catalogue_version=manifest['catalogue_version']+'-offline-reference-pilot',
                    embeddings_sha256=sha256_file(full / 'embeddings.npy'),
                    ids_sha256=sha256_file(full / 'embedding_card_ids.npy'),
                    parent_embeddings_sha256=parent_manifest['embeddings_sha256'],
                    parent_ids_sha256=parent_manifest['ids_sha256'])
    (full / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    art = a.output / 'artwork'; art.mkdir()
    old_art_manifest = json.loads((a.parent / 'artwork/manifest.json').read_text())
    for filename, key in [('embeddings.npy', 'embeddings_sha256'), ('records.json', 'records_sha256')]:
        if sha256_file(a.parent / 'artwork' / filename) != old_art_manifest[key]:
            raise ValueError('Parent artwork drifted')
    old_art = np.load(a.parent / 'artwork/embeddings.npy', allow_pickle=False)
    records = json.loads((a.parent / 'artwork/records.json').read_text())
    if any(r['card_id'] == card['id'] for r in records):
        raise ValueError('Pilot card already has artwork')
    extra = [model.embed(crop_profile(image, profile), 'pad') for profile in PROFILES]
    combined_art = np.concatenate([old_art, np.asarray(extra, dtype=np.float32)])
    assert np.array_equal(combined_art[:-len(extra)], old_art)
    np.save(art / 'embeddings.npy', combined_art)
    records.extend(dict(card_id=card['id'], profile=profile, language=card['language'], name=card['name'],
                        set_name=card['set_name'], collector_number=card['collector_number'],
                        reference_sha256=selection['sha256']) for profile in PROFILES)
    (art / 'records.json').write_text(json.dumps(records, ensure_ascii=False))
    old_art_manifest.update(base_embeddings_sha256=manifest['embeddings_sha256'],
                           base_ids_sha256=manifest['ids_sha256'], indexed_regions=len(records),
                           indexed_cards=len({r['card_id'] for r in records}),
                           embeddings_sha256=sha256_file(art / 'embeddings.npy'),
                           records_sha256=sha256_file(art / 'records.json'))
    (art / 'manifest.json').write_text(json.dumps(old_art_manifest, indent=2))
    source_dir = a.output / 'reference-images/recovered'; source_dir.mkdir(parents=True)
    copied = source_dir / source.name; shutil.copyfile(source, copied)
    feature = build_reference_bundle([dict(card, image_path=str(copied))], a.output, a.output / 'feature-delta')
    record = feature['records'][card['id']]
    if not record['available'] or record['source_sha256'] != selection['sha256']:
        raise ValueError('Feature source mismatch')
    record['image_path'] = destination
    feature['catalogue_sha256'] = catalogue_signature([next(r for r in updated if r['id'] == card['id'])])
    (a.output / 'feature-delta/manifest.json').write_text(json.dumps(feature, sort_keys=True, indent=2))
    parent_features = json.loads((a.parent_features / 'manifest.json').read_text())
    expected = {k:r.get('source_sha256') if r['available'] else None for k,r in parent_features['records'].items()}
    expected[card['id']] = selection['sha256']
    report = assemble(a.parent_features, rows, updated, a.output / 'features', expected, a.output / 'feature-delta')
    report.update(card_id=card['id'], pad_parent_rows=len(ids), artwork_parent_rows=len(old_art),
                  existing_vector_bytes_preserved=True, mapping_unchanged=True,
                  identity_approved_for_disposable_pilot=True, heldout_passed=False,
                  publication_approved=False, published=False, activated=False)
    (a.output / 'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
