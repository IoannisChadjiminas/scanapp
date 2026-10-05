"""Append verified reference vectors to isolated snapshots; never publish.

Mount the existing data volume read-only at /data and a new output directory
at /candidate. Selection records must carry image checksums and verification
provenance. All existing vector rows and Cardmarket mappings stay unchanged.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import re
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from app.config import Settings
from app.recognition.artifacts import resolve_bundle_dir, sha256_file, validate_embeddings
from app.recognition.artwork import PROFILES, SCHEMA_VERSION, crop_profile
from app.recognition.embed import DinoEmbedder
from app.recognition.rank import parse_collector


def insert_candidate_cards(target, cards):
    """Add independently reviewed missing rows to a disposable candidate only.

    Never overwrite a row, guess a set alias, or insert a marketplace mapping.
    FTS is additive; all existing card and mapping rows are audited below.
    """
    added = set()
    for row in cards:
        identifier = str(row['id'])
        if not re.fullmatch(r'[a-z]{2}(?:-[a-z]{2})?:[A-Za-z0-9_.-]+', identifier):
            raise ValueError('Unsafe candidate card ID')
        if identifier in added or target.execute('SELECT 1 FROM cards WHERE id=?', (identifier,)).fetchone():
            raise ValueError('Refusing to replace/duplicate an existing catalogue ID')
        if not identifier.startswith(str(row['language'])+':'):
            raise ValueError('Card ID language disagrees')
        if (row.get('verification') != 'manual_visual' or not row.get('source_page')
                or not row.get('source_kind') or not row.get('image_url')
                or not row.get('printed_collector_number') or not row.get('reference_edition')):
            raise ValueError('Incomplete independently reviewed source metadata')
        if row['source_kind'] not in {'official_pokemon', 'independent_catalogue_not_official'}:
            raise ValueError('Reference must be independently sourced, not a query photo')
        if row.get('cardmarket_url') is not None or row.get('cardmarket_id') is not None or row.get('cardmarket_verified'):
            raise ValueError('New row mapping must remain pending; verify marketplace identity separately')
        set_rows = target.execute('SELECT * FROM cards WHERE language=? AND (set_id=? OR set_name=?)',
            (row['language'], row['set_id'], row['set_name'])).fetchall()
        if not set_rows or any(r['set_id'] != row['set_id'] or r['set_name'] != row['set_name'] for r in set_rows):
            raise ValueError('Unknown or ambiguous existing set alias')
        number, printed = parse_collector(str(row['collector_number'])), parse_collector(row['printed_collector_number'])
        if (number is None or printed is None
                or (number.prefix, number.number) != (printed.prefix, printed.number)
                or (number.denominator is not None and number.denominator != printed.denominator)):
            raise ValueError('Unverified collector identity')
        for old in set_rows:
            parts = parse_collector(old['collector_number'])
            if parts and (parts.prefix,parts.number) == (number.prefix,number.number):
                raise ValueError('Collector identity already represented by another alias')
        path = Path(row['source_file'])
        if sha256_file(path) != row['sha256']:
            raise ValueError('Independent reference checksum changed')
        provenance = dict(source_kind=row['source_kind'], source_page=row['source_page'],
            reference_sha256=row['sha256'], reference_edition=row['reference_edition'],
            edition_of_query_unconfirmed=True, cardmarket_mapping='pending')
        target.execute('''INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,
            printed_collector_number,language,category,rarity,illustrator,variants_json,
            has_image,cardmarket_verified,cardmarket_provenance) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0,?)''',
            (identifier,identifier,row['name'],row['set_id'],row['set_name'],str(row['collector_number']),
             row['printed_collector_number'],row['language'],row.get('category'),row.get('rarity'),
             row.get('illustrator'),json.dumps({'catalogue_reference':provenance}), 'unmapped-independent-reference'))
        target.execute('INSERT INTO cards_fts(id,name,set_name,collector_number) VALUES(?,?,?,?)',
            (identifier,row['name'],row['set_name'],str(row['collector_number'])))
        added.add(identifier)
    return added


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--previous-artwork', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frozen-source', action='store_true', help='Input is a standalone completed backup with no WAL')
    p.add_argument('--new-cards', type=Path, help='Independently reviewed additions to this disposable candidate; no mappings')
    args = p.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(Path('/data')):
        raise ValueError('Candidate must be outside the existing data volume')
    output.mkdir(exist_ok=False)
    images = output / 'images'
    images.mkdir()
    # When extending an earlier recovery candidate, retain its recovered
    # images so catalogue paths do not become unavailable under the overlay.
    parent_images = Path('/data/reference-images/recovered')
    if parent_images.is_dir():
        for previous in parent_images.iterdir():
            if previous.is_file():
                shutil.copyfile(previous, images / previous.name)
    selection = json.loads(args.selection.read_text())['records']
    if not selection or len({r['id'] for r in selection}) != len(selection):
        raise ValueError('Empty or duplicate recovery selection')
    source = sqlite3.connect('file:/data/catalog.sqlite?mode=ro' + ('&immutable=1' if args.frozen_source else ''), uri=True)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(output / 'catalog.sqlite')
    target.row_factory = sqlite3.Row
    source.backup(target)
    source.close()
    # Compare against the frozen backup, not a live source connection: the
    # local service can legitimately update its helper cache during a build.
    old_rows = target.execute('SELECT * FROM cards ORDER BY id').fetchall()
    helper_rows = {}
    fts_before = Counter(tuple(r) for r in target.execute('SELECT id,name,set_name,collector_number FROM cards_fts'))
    for (table,) in target.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='cards'"):
        if table == 'cards_fts' or table.startswith('cards_fts_'):
            continue  # Validate logical FTS rows, not mutable index shadow pages.
        escaped = table.replace('"', '""')
        helper_rows[table] = [tuple(r) for r in target.execute(f'SELECT * FROM "{escaped}"')]
    new_cards = json.loads(args.new_cards.read_text())['cards'] if args.new_cards else []
    added_ids = insert_candidate_cards(target,new_cards)
    addition_by_id = {row['id']:row for row in new_cards}
    if not added_ids.issubset({r['id'] for r in selection}):
        raise ValueError('Every added catalogue row must have a verified vector/reference selection')
    accepted = []
    for row in selection:
        if row.get('verification') not in {'ocr_corroborated', 'official_metadata_matched', 'manual_visual'}:
            raise ValueError('Unverified reference in selection')
        if row['id'] in added_ids:
            for key in ('source_file','sha256','image_url','source_kind','source_page','reference_edition','verification'):
                if row.get(key) != addition_by_id[row['id']].get(key):
                    raise ValueError(f'New catalogue reference disagrees with selected image: {key}')
        original = target.execute('SELECT * FROM cards WHERE id=?', (row['id'],)).fetchone()
        if original is None:
            raise ValueError('Unknown card')
        for key in ('name', 'language', 'set_id', 'collector_number', 'cardmarket_url'):
            if original[key] != row[key]:
                raise ValueError(f'Catalogue identity changed: {row["id"]} {key}')
        if original['has_image'] and original['image_path'] and Path(original['image_path']).is_file():
            raise ValueError('Refusing to replace an existing usable image')
        path = Path(row['source_file'])
        if sha256_file(path) != row['sha256']:
            raise ValueError('Reference checksum changed')
        filename = row['id'].replace(':', '_') + path.suffix
        if (images / filename).exists():
            raise ValueError('Refusing to overwrite a recovered image')
        shutil.copyfile(path, images / filename)
        new_path = f'/data/reference-images/recovered/{filename}'
        target.execute('UPDATE cards SET image_path=?,has_image=1,remote_image_url=? WHERE id=?',
                       (new_path, row['image_url'], row['id']))
        accepted.append({**row, 'new_image_path': new_path})
    target.commit()
    new_rows = target.execute('SELECT * FROM cards ORDER BY id').fetchall()
    expected_ids = {r['id'] for r in accepted}
    existing_after = {r['id']:r for r in new_rows}
    if set(existing_after) != {r['id'] for r in old_rows} | added_ids:
        raise ValueError('Unexpected catalogue membership change')
    for old in old_rows:
        new = existing_after[old['id']]
        changed = {key for key in old.keys() if old[key] != new[key]}
        allowed = {'image_path', 'has_image', 'remote_image_url'} if old['id'] in expected_ids else set()
        if not changed.issubset(allowed):
            raise ValueError('Unexpected catalogue mutation')
    fts_after = Counter(tuple(r) for r in target.execute('SELECT id,name,set_name,collector_number FROM cards_fts'))
    fts_added = Counter((r['id'],r['name'],r['set_name'],str(r['collector_number'])) for r in new_cards)
    if fts_after != fts_before + fts_added:
        raise ValueError('Unexpected FTS/name-search mutation')
    for identifier in added_ids:
        row = existing_after[identifier]
        if row['cardmarket_url'] is not None or row['cardmarket_id'] is not None or row['cardmarket_verified']:
            raise ValueError('New candidate acquired an unverified mapping')
    # All helper/mapping tables must remain byte-for-byte equivalent as rows.
    for table, before in helper_rows.items():
        escaped = table.replace('"', '""')
        if before != [tuple(r) for r in target.execute(f'SELECT * FROM "{escaped}"')]:
            raise ValueError(f'Mapping/helper table changed: {table}')
    target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    target.execute('PRAGMA journal_mode=DELETE')
    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Candidate catalogue integrity check failed')
    target.close()
    settings = Settings(data_dir=Path('/data'), use_ocr=False)
    model = DinoEmbedder(str(settings.dinov2_path), 2, 1)
    model_hash = sha256_file(settings.dinov2_path)
    full_manifests = {}
    for mode in ('pad', 'square'):
        base = resolve_bundle_dir(Path('/data/vectors') / mode)
        manifest = json.loads((base / 'manifest.json').read_text())
        if manifest['dinov2_sha256'] != model_hash:
            raise ValueError('Base model mismatch')
        if sha256_file(base / 'embeddings.npy') != manifest['embeddings_sha256'] or sha256_file(base / 'embedding_card_ids.npy') != manifest['ids_sha256']:
            raise ValueError('Base snapshot checksum mismatch')
        old_vectors = np.load(base / 'embeddings.npy', allow_pickle=False)
        old_ids = np.load(base / 'embedding_card_ids.npy', allow_pickle=False)
        if set(old_ids.tolist()) & expected_ids:
            raise ValueError('Recovery ID is already indexed; audit separately')
        new_vectors = []
        for count, row in enumerate(accepted, 1):
            with Image.open(images / Path(row['new_image_path']).name) as image:
                new_vectors.append(model.embed(image.convert('RGB'), mode))
            if count % 50 == 0:
                print(json.dumps({'mode': mode, 'embedded': count, 'total': len(accepted)}), flush=True)
        matrix = np.concatenate([old_vectors, np.asarray(new_vectors, dtype=np.float32)])
        ids = np.asarray(old_ids.tolist() + [r['id'] for r in accepted])
        validate_embeddings(matrix, ids)
        if not np.array_equal(matrix[:len(old_ids)], old_vectors):
            raise ValueError('Existing vectors changed')
        directory = output / 'vectors' / mode
        directory.mkdir(parents=True)
        np.save(directory / 'embeddings.npy', matrix)
        np.save(directory / 'embedding_card_ids.npy', ids)
        manifest.update(catalogue_version=manifest['catalogue_version'] + '-candidate-additive-references-20261002',
                        card_count=manifest['card_count'] + len(added_ids),
                        indexed_count=len(ids), indexed_ids=ids.tolist(),
                        missing_images=manifest['missing_images'] - (len(accepted)-len(added_ids)),
                        embeddings_sha256=sha256_file(directory / 'embeddings.npy'),
                        ids_sha256=sha256_file(directory / 'embedding_card_ids.npy'),
                        recovery_selection_sha256=sha256_file(args.selection),
                        new_cards_selection_sha256=sha256_file(args.new_cards) if args.new_cards else None,
                        parent_embeddings_sha256=sha256_file(base / 'embeddings.npy'),
                        parent_ids_sha256=sha256_file(base / 'embedding_card_ids.npy'))
        # Preserve the parent fingerprint as provenance, not a claim about new images.
        manifest['parent_image_fingerprint'] = manifest.pop('image_fingerprint', None)
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        full_manifests[mode] = manifest
    artbase = args.previous_artwork
    artmanifest = json.loads((artbase / 'manifest.json').read_text())
    if artmanifest['model_sha256'] != model_hash or artmanifest['schema_version'] != SCHEMA_VERSION or artmanifest['preprocess_config'] != 'pad' or artmanifest['profiles'] != {k: list(v) for k, v in PROFILES.items()}:
        raise ValueError('Artwork parent model/profile mismatch')
    for filename, key in [('embeddings.npy', 'embeddings_sha256'), ('records.json', 'records_sha256')]:
        if sha256_file(artbase / filename) != artmanifest[key]:
            raise ValueError('Artwork parent checksum mismatch')
    if artmanifest['base_embeddings_sha256'] != full_manifests['pad']['parent_embeddings_sha256'] or artmanifest['base_ids_sha256'] != full_manifests['pad']['parent_ids_sha256']:
        raise ValueError('Artwork parent is bound to a different full snapshot')
    records = json.loads((artbase / 'records.json').read_text())
    old_art = np.load(artbase / 'embeddings.npy', allow_pickle=False)
    if {r['card_id'] for r in records} & expected_ids:
        raise ValueError('Recovery ID already has artwork vectors')
    appended = []
    for count, row in enumerate(accepted, 1):
        with Image.open(images / Path(row['new_image_path']).name) as source_image:
            image = source_image.convert('RGB')
        for profile in PROFILES:
            appended.append(model.embed(crop_profile(image, profile), 'pad'))
            records.append({'card_id': row['id'], 'profile': profile, 'language': row['language'],
                            'name': row['name'], 'set_name': row['set_name'],
                            'collector_number': row['collector_number'], 'reference_sha256': row['sha256']})
        if count % 50 == 0:
            print(json.dumps({'mode': 'artwork', 'embedded': count, 'total': len(accepted)}), flush=True)
    artwork = output / 'artwork'
    artwork.mkdir()
    np.save(artwork / 'embeddings.npy', np.concatenate([old_art, np.asarray(appended, dtype=np.float32)]))
    (artwork / 'records.json').write_text(json.dumps(records, ensure_ascii=False))
    artmanifest.update(base_embeddings_sha256=full_manifests['pad']['embeddings_sha256'],
                       base_ids_sha256=full_manifests['pad']['ids_sha256'],
                       embeddings_sha256=sha256_file(artwork / 'embeddings.npy'),
                       records_sha256=sha256_file(artwork / 'records.json'),
                       indexed_regions=len(records), indexed_cards=len({r['card_id'] for r in records}),
                       parent_manifest_sha256=sha256_file(artbase / 'manifest.json'),
                       scope='previous artwork subset plus verified recovered references; not whole catalogue')
    (artwork / 'manifest.json').write_text(json.dumps(artmanifest, indent=2))
    report = {'complete': True, 'published': False, 'created_at': datetime.now(timezone.utc).isoformat(),
              'recovered': accepted, 'new_catalogue_ids':sorted(added_ids),
              'existing_catalogue_rows_preserved':True, 'fts_existing_rows_preserved':True,
              'mappings_unchanged': True, 'existing_vectors_unchanged': True,
              'full_indexed_count': full_manifests['pad']['indexed_count'],
              'catalogue_sha256': sha256_file(output / 'catalog.sqlite'),
              'selection_sha256': sha256_file(args.selection)}
    report['new_cards_selection_sha256'] = sha256_file(args.new_cards) if args.new_cards else None
    report['builder_sha256'] = sha256_file(Path(__file__))
    (output / 'recovery.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({'complete': True, 'recovered': len(accepted), 'published': False}), flush=True)


if __name__ == '__main__':
    main()
