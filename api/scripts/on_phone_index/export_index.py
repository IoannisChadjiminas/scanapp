"""Export a verified server snapshot to an immutable phone index directory.

Use a snapshot exported by export_cloud_snapshot.py when the server uses the
cloud catalogue. Supply the matching operational SQLite database for set totals.
The output is an offline candidate; do not publish it until the parity gate and
device tests in the shipping plan pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

import numpy as np

MODEL_ID = '2ddf6ec79e37'
DIMENSIONS = 384


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def clean(value: object) -> str:
    text = '' if value is None else str(value)
    if any(c in text for c in '\t\r\n'):
        raise ValueError('Catalogue field contains a tab or newline')
    return text


def export(snapshot_dir: Path, catalogue: Path, totals_db: Path, model: Path, out: Path) -> Path:
    manifest = json.loads((snapshot_dir / 'manifest.json').read_text())
    if manifest.get('preprocess_config') != 'pad' or manifest.get('embedding_dim') != DIMENSIONS:
        raise ValueError('Expected a 384-dimensional pad snapshot')
    model_hash = digest(model)
    if manifest.get('dinov2_sha256') != model_hash or not model_hash.startswith(MODEL_ID):
        raise ValueError('Snapshot model does not match the phone model')
    emb_path = snapshot_dir / 'embeddings.npy'
    ids_path = snapshot_dir / 'embedding_card_ids.npy'
    for path, key in ((emb_path, 'embeddings_sha256'), (ids_path, 'ids_sha256')):
        if not manifest.get(key) or digest(path) != manifest[key]:
            raise ValueError(f'Snapshot checksum mismatch: {path.name}')
    vectors = np.load(emb_path, mmap_mode='r', allow_pickle=False)
    ids = np.load(ids_path, allow_pickle=False).astype(str).tolist()
    if (vectors.dtype != np.float32 or vectors.shape != (len(ids), DIMENSIONS)
            or not ids or len(set(ids)) != len(ids) or manifest.get('indexed_count') != len(ids)):
        raise ValueError('Invalid snapshot shape, rows, or ids')
    if manifest.get('indexed_ids') is not None and manifest['indexed_ids'] != ids:
        raise ValueError('Snapshot ids do not match the manifest order')
    for start in range(0, len(ids), 8192):
        chunk = np.asarray(vectors[start:start + 8192])
        if not np.isfinite(chunk).all() or np.max(np.abs(np.linalg.norm(chunk, axis=1) - 1)) > .01:
            raise ValueError('Snapshot vectors are not finite and normalized')
    with sqlite3.connect(f'{catalogue.resolve().as_uri()}?mode=ro', uri=True) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(cards)')}
        printed = 'printed_collector_number' if 'printed_collector_number' in columns else "''"
        cards = {row[0]: row for row in db.execute(
            f'SELECT id, name, collector_number, {printed}, language, set_id FROM cards')}
    with sqlite3.connect(f'{totals_db.resolve().as_uri()}?mode=ro', uri=True) as db:
        totals = {(str(lang).casefold(), str(set_id).split(':')[-1].casefold()): total
                  for lang, set_id, total in db.execute(
                      'SELECT language, set_id, official_total FROM set_totals')}
    if not totals:
        raise ValueError('Set totals are empty; provide the server operational database')
    if any(card_id not in cards for card_id in ids):
        raise ValueError('Snapshot contains ids absent from the catalogue')
    if not manifest.get('catalogue_version'):
        raise ValueError('Snapshot has no catalogue version')
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.phone-index-', dir=out))
    try:
        (tmp / 'card_index.ids.txt').write_text(''.join(clean(i) + '\n' for i in ids), encoding='utf-8')
        with (tmp / 'card_index.meta.tsv').open('w', encoding='utf-8', newline='\n') as f:
            f.write('#id\tname\tnumber\tprinted_number\tset_total\tlanguage\n')
            for card_id in ids:
                _, name, number, printed_number, lang, set_id = cards[card_id]
                total = totals.get((str(lang or 'en').casefold(), str(set_id or '').split(':')[-1].casefold()))
                f.write('\t'.join(map(clean, (card_id, name, number, printed_number, total, lang))) + '\n')
        with (tmp / 'card_index.f16.bin').open('wb') as f:
            for start in range(0, len(ids), 8192):
                f.write(np.asarray(vectors[start:start + 8192], dtype='<f2').tobytes(order='C'))
        names = ('card_index.f16.bin', 'card_index.ids.txt', 'card_index.meta.tsv')
        files = {name: {'bytes': (tmp / name).stat().st_size, 'sha256': digest(tmp / name)} for name in names}
        identity = {'model_id': MODEL_ID, 'catalogue_version': str(manifest['catalogue_version']),
                    'rows': len(ids), 'dims': DIMENSIONS, 'files': files,
                    'source_ids_sha256': manifest['ids_sha256'],
                    'source_embeddings_sha256': manifest['embeddings_sha256']}
        version = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        identity['version'] = version
        (tmp / 'card_index.version.json').write_text(json.dumps(identity, sort_keys=True) + '\n', encoding='utf-8')
        destination = out / version
        if destination.exists():
            if any(not (destination / name).is_file() or digest(destination / name) != digest(tmp / name)
                   for name in (*names, 'card_index.version.json')):
                raise ValueError('Existing version directory differs from the candidate')
            shutil.rmtree(tmp)
        else:
            os.rename(tmp, destination)
        return destination
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot-dir', type=Path, required=True)
    p.add_argument('--catalogue', type=Path, required=True)
    p.add_argument('--totals-db', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    print(export(a.snapshot_dir, a.catalogue, a.totals_db, a.model, a.out))


if __name__ == '__main__':
    main()
