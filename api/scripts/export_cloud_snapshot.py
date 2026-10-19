"""Export the cloud catalogue snapshot the API serves as a local-backend data directory.

Run on the host that already holds the catalogue credential, from the API image, with the
credential coming only from that environment. It loads the catalogue with the API's own
verified loader (row digests, vector hashes, model checksums), then writes public card data
only: catalog.sqlite, vectors/<preprocess>/{embeddings,embedding_card_ids}.npy and
manifest.json. Prints counts and checksums, never settings or connection details.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, '/app')
from app.config import Settings  # noqa: E402
from app.db import Databases, init_catalog  # noqa: E402


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    settings = Settings()
    if settings.catalogue_backend != 'planetscale':
        raise SystemExit('Run with the cloud catalogue backend configured.')
    dbs = Databases(settings)
    snapshot = dbs.cloud_snapshot
    cloud = dbs.catalog
    out = a.out
    vectors = out / 'vectors' / settings.preprocess_config
    vectors.mkdir(parents=True, exist_ok=True)
    np.save(vectors / 'embeddings.npy', np.asarray(snapshot.embeddings, dtype=np.float32))
    np.save(vectors / 'embedding_card_ids.npy', np.asarray(snapshot.card_ids))
    manifest = dict(snapshot.manifest)
    manifest['exported_from'] = dict(
        cloud_embeddings_sha256=manifest.get('embeddings_sha256'),
        cloud_ids_sha256=manifest.get('ids_sha256'),
        import_id=settings.planetscale_import_id, schema=settings.planetscale_schema)
    manifest['embeddings_sha256'] = sha(vectors / 'embeddings.npy')
    manifest['ids_sha256'] = sha(vectors / 'embedding_card_ids.npy')
    (vectors / 'manifest.json').write_text(json.dumps(manifest))
    target = out / 'catalog.sqlite'
    target.unlink(missing_ok=True)
    local = sqlite3.connect(target)
    init_catalog(local)
    have = [r[1] for r in local.execute('PRAGMA table_info(cards)')]
    cursor = cloud.execute('SELECT * FROM cards')
    source = [d[0] for d in cursor.description]
    kept = [c for c in source if c in have]
    index = [source.index(c) for c in kept]
    marks = ','.join('?' for _ in kept)
    while rows := cursor.fetchmany(2000):
        local.executemany(f"INSERT OR REPLACE INTO cards({','.join(kept)}) VALUES ({marks})",
                          [tuple(row[i] for i in index) for row in rows])
    local.execute('INSERT INTO cards_fts(name,set_name,collector_number,id) '
                  'SELECT name,set_name,collector_number,id FROM cards')
    product = cloud.execute('SELECT * FROM cardmarket_expansion_products')
    pcolumns = [d[0] for d in product.description]
    local.execute('CREATE TABLE IF NOT EXISTS cardmarket_expansion_products(' + ','.join(pcolumns) + ')')
    while rows := product.fetchmany(2000):
        local.executemany(f"INSERT INTO cardmarket_expansion_products VALUES ({','.join('?' for _ in pcolumns)})", rows)
    local.commit()
    cards = local.execute('SELECT count(*) FROM cards').fetchone()[0]
    products = local.execute('SELECT count(*) FROM cardmarket_expansion_products').fetchone()[0]
    local.close()
    aliases = getattr(cloud, 'visual_image_aliases', None)
    if aliases:
        (out / 'visual_image_aliases.json').write_text(json.dumps(
            {k: (list(v) if isinstance(v, (set, tuple)) else v) for k, v in dict(aliases).items()},
            default=str))
    print(json.dumps(dict(cards=cards, cardmarket_products=products,
        indexed=int(snapshot.indexed_count), catalogue_version=snapshot.catalogue_version,
        import_id=settings.planetscale_import_id, embeddings_sha256=manifest['embeddings_sha256'],
        ids_sha256=manifest['ids_sha256'], cloud_embeddings_sha256=manifest['exported_from']['cloud_embeddings_sha256'],
        visual_aliases=len(aliases) if aliases else 0)))
    dbs.close()


if __name__ == '__main__':
    main()
