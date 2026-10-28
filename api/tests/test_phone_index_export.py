import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest


path = Path(__file__).resolve().parents[1] / 'scripts/on_phone_index/export_index.py'
spec = importlib.util.spec_from_file_location('phone_index_export', path)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def fixture(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    model = tmp_path / 'model'
    model.write_bytes(b'model')
    model_hash = hashlib.sha256(b'model').hexdigest()
    monkeypatch.setattr(exporter, 'MODEL_ID', model_hash[:12])
    vectors = np.zeros((2, 384), dtype=np.float32)
    vectors[0, 0] = vectors[1, 1] = 1
    np.save(snapshot / 'embeddings.npy', vectors)
    np.save(snapshot / 'embedding_card_ids.npy', np.array(['b', 'a']))
    manifest = {'preprocess_config': 'pad', 'embedding_dim': 384, 'dinov2_sha256': model_hash,
                'embeddings_sha256': exporter.digest(snapshot / 'embeddings.npy'),
                'ids_sha256': exporter.digest(snapshot / 'embedding_card_ids.npy'),
                'indexed_count': 2, 'indexed_ids': ['b', 'a'], 'catalogue_version': 'test'}
    (snapshot / 'manifest.json').write_text(json.dumps(manifest))
    catalogue = tmp_path / 'catalogue.db'
    with sqlite3.connect(catalogue) as db:
        db.execute('CREATE TABLE cards (id TEXT, name TEXT, collector_number TEXT, printed_collector_number TEXT, language TEXT, set_id TEXT)')
        db.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?)', [
            ('a', 'Alpha', '1', None, 'en', 'en:set'), ('b', 'Beta', '2', '02', 'en', 'set')])
        db.execute('CREATE TABLE set_totals (language TEXT, set_id TEXT, official_total INTEGER)')
        db.execute("INSERT INTO set_totals VALUES ('en','set',100)")
    return snapshot, catalogue, model


def test_export_preserves_rows_and_hashes(tmp_path, monkeypatch):
    snapshot, catalogue, model = fixture(tmp_path, monkeypatch)
    target = exporter.export(snapshot, catalogue, catalogue, model, tmp_path / 'output')
    assert (target / 'card_index.ids.txt').read_text() == 'b\na\n'
    assert (target / 'card_index.meta.tsv').read_text().splitlines()[1:] == [
        'b\tBeta\t2\t02\t100\ten', 'a\tAlpha\t1\t\t100\ten']
    assert np.fromfile(target / 'card_index.f16.bin', dtype='<f2').reshape(2, 384)[1, 1] == 1
    version = json.loads((target / 'card_index.version.json').read_text())
    for name, info in version['files'].items():
        assert info == {'bytes': (target / name).stat().st_size, 'sha256': exporter.digest(target / name)}
    assert exporter.export(snapshot, catalogue, catalogue, model, tmp_path / 'output') == target


def test_rejects_changed_snapshot_without_publishing(tmp_path, monkeypatch):
    snapshot, catalogue, model = fixture(tmp_path, monkeypatch)
    (snapshot / 'embedding_card_ids.npy').write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        exporter.export(snapshot, catalogue, catalogue, model, tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_publication_requires_switch_and_matching_snapshot(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import card_index
    from app.routes.card_index import router

    snapshot, catalogue, model = fixture(tmp_path, monkeypatch)
    root = tmp_path / 'output'
    candidate = exporter.export(snapshot, catalogue, catalogue, model, root)
    (root / 'ACTIVE').write_text(candidate.name)
    source = json.loads((snapshot / 'manifest.json').read_text())
    monkeypatch.setattr(card_index, '_MODEL_ID', source['dinov2_sha256'][:12])
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    settings = SimpleNamespace(card_index_publish=False, card_index_publish_dir=root)
    app.state.settings = settings
    app.state.runtime = SimpleNamespace(snapshot=SimpleNamespace(
        catalogue_version='test', ids_sha256=source['ids_sha256'],
        embeddings_sha256=source['embeddings_sha256'], indexed_count=2,
        embedding_dim=384, manifest=source))
    client = TestClient(app)
    assert client.get('/api/v1/card-index/manifest').status_code == 404
    settings.card_index_publish = True
    hashed = []
    original_hash = card_index.sha256_file
    def counted_hash(path):
        hashed.append(path)
        return original_hash(path)
    monkeypatch.setattr(card_index, 'sha256_file', counted_hash)
    result = client.get('/api/v1/card-index/manifest')
    assert len(hashed) == 4
    assert client.get('/api/v1/card-index/manifest').status_code == 200
    assert len(hashed) == 4
    assert result.status_code == 200
    manifest = result.json()
    assert manifest['version'] == candidate.name
    index = next(f for f in manifest['files'] if f['name'] == 'card_index.f16.bin')
    response = client.get('/api/v1/' + index['url'])
    assert response.status_code == 200
    assert len(hashed) == 4
    assert response.headers['etag'] == '"' + index['sha256'] + '"'
    assert client.get('/api/v1/' + index['url'], headers={'Range': 'bytes=0-7'}).status_code == 206
    assert client.get('/api/v1/' + index['url'], headers={'If-None-Match': response.headers['etag']}).status_code == 304
    app.state.runtime.snapshot.catalogue_version = 'different'
    assert client.get('/api/v1/card-index/manifest').status_code == 503
    import os
    target = candidate / 'card_index.ids.txt'
    original_stat = target.stat()
    target.write_text('a\nb\n')  # Same size; changed mtime must invalidate the cache.
    os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000))
    assert client.get('/api/v1/' + index['url']).status_code == 404
