"""Validate candidate artifacts against the unchanged source volume, read-only."""
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from app.config import Settings
from app.recognition.artifacts import load_snapshot, resolve_bundle_dir, sha256_file
from app.recognition.artwork import ArtworkIndex

root = Path('/data')
class ReadOnlyArtifactSettings(Settings):
    @property
    def catalog_sqlite(self) -> Path:
        # Snapshot loading normally enables WAL on the catalogue. This audit
        # validates catalogue membership explicitly below without any writes.
        return Path('/nonexistent/read-only-artifact-audit.sqlite')

settings = ReadOnlyArtifactSettings(data_dir=root, catalogue_backend='sqlite')
snapshot = load_snapshot(settings)
catalogue = sqlite3.connect('file:/data/catalog.sqlite?mode=ro', uri=True)
catalogue.row_factory = sqlite3.Row
assert catalogue.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
cards = {r['id']: dict(r) for r in catalogue.execute('SELECT * FROM cards')}
selection_path = Path('/workspace/data/image-recovery/20261002-official/selection-combined.json')
selection = json.loads(selection_path.read_text())['records']
for row in selection:
    card = cards[row['id']]
    for key in ('name', 'language', 'set_id', 'collector_number', 'cardmarket_url'):
        assert card[key] == row[key], (row['id'], key)
    assert card['has_image'] == 1 and card['remote_image_url'] == row['image_url']
    assert sha256_file(Path(card['image_path'])) == row['sha256']
preserved = {}
for mode in ('pad', 'square'):
    current = load_snapshot(ReadOnlyArtifactSettings(data_dir=root, preprocess_config=mode, catalogue_backend='sqlite'))
    assert set(current.card_ids.tolist()) <= set(cards)
    base = resolve_bundle_dir(Path('/original/vectors') / mode)
    old_ids = np.load(base / 'embedding_card_ids.npy', allow_pickle=False)
    old_vectors = np.load(base / 'embeddings.npy', allow_pickle=False)
    assert np.array_equal(current.card_ids[:len(old_ids)], old_ids)
    assert np.array_equal(current.embeddings[:len(old_ids)], old_vectors)
    assert set(current.card_ids[len(old_ids):].tolist()) == {r['id'] for r in selection}
    preserved[mode] = {'old_count': len(old_ids), 'new_count': current.indexed_count,
                       'old_vectors_bitwise_identical': True,
                       'old_manifest_sha256': sha256_file(base / 'manifest.json')}
art = ArtworkIndex.load(root / 'artwork', snapshot=snapshot, model_path=settings.dinov2_path,
                       known_ids=set(cards), known_languages={i: c['language'] for i, c in cards.items()})
previous = Path('/workspace/data/artwork-candidates/20261002-recovery')
old_art = np.load(previous / 'embeddings.npy', allow_pickle=False)
old_records = json.loads((previous / 'records.json').read_text())
assert np.array_equal(art.embeddings[:len(old_art)], old_art)
assert art.records[:len(old_records)] == old_records
assert {r['card_id'] for r in art.records[len(old_records):]} == {r['id'] for r in selection}
missing = [r['id'] for r in cards.values() if not (r['has_image'] and r['image_path'] and Path(r['image_path']).is_file())]
indexed_ids = set(snapshot.card_ids.tolist())
flagged_not_indexed = [r['id'] for r in cards.values() if r['has_image'] and r['image_path'] and r['id'] not in indexed_ids]
assert not flagged_not_indexed
print(json.dumps({'valid': True, 'published': False, 'recovered': len(selection),
                  'full_snapshots': preserved, 'artwork_cards': art.manifest['indexed_cards'],
                  'artwork_regions': art.manifest['indexed_regions'],
                  'old_artwork_vectors_bitwise_identical': True,
                  'missing_usable_files_all_languages': len(missing),
                  'imageflag_but_unindexed': flagged_not_indexed,
                  'catalogue_sha256': sha256_file(root / 'catalog.sqlite'),
                  'selection_sha256': sha256_file(selection_path)}, indent=2))
