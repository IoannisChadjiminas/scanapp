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


def _served(tmp_path, monkeypatch):
    """A published base index from the fixture snapshot and a client serving the publish folder."""
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import card_index

    snapshot, catalogue, model = fixture(tmp_path, monkeypatch)
    root = tmp_path / 'output'
    base = exporter.export(snapshot, catalogue, catalogue, model, root)
    source = json.loads((snapshot / 'manifest.json').read_text())
    monkeypatch.setattr(card_index, '_MODEL_ID', source['dinov2_sha256'][:12])
    app = FastAPI()
    app.include_router(card_index.router, prefix='/api/v1')
    app.state.settings = SimpleNamespace(card_index_publish=True, card_index_publish_dir=root)
    app.state.runtime = SimpleNamespace(snapshot=SimpleNamespace(
        catalogue_version='test', ids_sha256=source['ids_sha256'],
        embeddings_sha256=source['embeddings_sha256'], indexed_count=2,
        embedding_dim=384, manifest=source))
    return root, base, app, TestClient(app)


def _extended(root, base, *, prints=True, vectors=None, list_prints=True):
    """An index that extends `base` by one row, as on_phone_index/extend_index.py writes it."""
    meta = json.loads((base / 'card_index.version.json').read_text())
    if vectors is None:
        added = np.zeros((1, 384), dtype='<f2')
        added[0, 2] = 1
        vectors = (base / 'card_index.f16.bin').read_bytes() + added.tobytes()
    body = {
        'card_index.f16.bin': vectors,
        'card_index.ids.txt': (base / 'card_index.ids.txt').read_bytes() + b'c\n',
        'card_index.meta.tsv': (base / 'card_index.meta.tsv').read_bytes() + b'c\tGamma\t3\t\t\ten\n'}
    if prints:
        body['card_index.prints.tsv'] = b'#id\treprint_of\tprinting\nd\ta\tpromo\n'
    files = {n: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for n, b in body.items()}
    if prints and not list_prints:
        del files['card_index.prints.tsv']
    version = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    meta.update(version=version, rows=3, files=files,
                extends={'version': base.name, 'rows': 2, 'added_rows': 1})
    folder = root / version
    folder.mkdir()
    for name, data in body.items():
        (folder / name).write_bytes(data)
    (folder / 'card_index.version.json').write_text(json.dumps(meta))
    (root / 'ACTIVE').write_text(version)
    return folder


def test_manifest_without_prints_file_is_unchanged(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    (root / 'ACTIVE').write_text(base.name)
    meta = json.loads((base / 'card_index.version.json').read_text())
    names = ['card_index.f16.bin', 'card_index.ids.txt', 'card_index.meta.tsv', 'card_index.version.json']
    assert client.get('/api/v1/card-index/manifest').json() == {
        'version': base.name, 'model_id': meta['model_id'], 'catalogue_version': 'test', 'rows': 2,
        'files': [{'name': n, 'bytes': (base / n).stat().st_size, 'sha256': exporter.digest(base / n),
                   'url': f'card-index/files/{base.name}/{n}'} for n in names]}
    assert client.get(f'/api/v1/card-index/files/{base.name}/card_index.prints.tsv').status_code == 404


def test_extended_index_lists_prints_file_and_its_own_rows(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    folder = _extended(root, base)
    manifest = client.get('/api/v1/card-index/manifest')
    assert manifest.status_code == 200
    manifest = manifest.json()
    assert manifest['version'] == folder.name and manifest['rows'] == 3
    assert [f['name'] for f in manifest['files']] == [
        'card_index.f16.bin', 'card_index.ids.txt', 'card_index.meta.tsv', 'card_index.version.json',
        'card_index.prints.tsv']
    prints = manifest['files'][4]
    assert prints['url'] == f'card-index/files/{folder.name}/card_index.prints.tsv'
    response = client.get('/api/v1/' + prints['url'])
    assert response.status_code == 200 and response.content == (folder / 'card_index.prints.tsv').read_bytes()
    assert manifest['files'][0]['bytes'] == 3 * 384 * 2
    assert client.get(f'/api/v1/card-index/files/{folder.name}/card_index.other.tsv').status_code == 404


def test_extended_index_without_prints_file_has_four_files(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    _extended(root, base, prints=False)
    manifest = client.get('/api/v1/card-index/manifest').json()
    assert manifest['rows'] == 3 and len(manifest['files']) == 4


def test_extended_index_refused_when_base_rows_differ(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    changed = bytearray((base / 'card_index.f16.bin').read_bytes() + np.zeros((1, 384), dtype='<f2').tobytes())
    changed[0] ^= 1  # first row's vector differs from the base by one bit
    _extended(root, base, vectors=bytes(changed))
    assert client.get('/api/v1/card-index/manifest').status_code == 503


def test_extended_index_refused_when_base_no_longer_matches_snapshot(tmp_path, monkeypatch):
    root, base, app, client = _served(tmp_path, monkeypatch)
    _extended(root, base)
    assert client.get('/api/v1/card-index/manifest').status_code == 200
    app.state.runtime.snapshot.indexed_count = 3  # snapshot now has a row the base lacks
    assert client.get('/api/v1/card-index/manifest').status_code == 503
    app.state.runtime.snapshot.indexed_count = 2
    import shutil
    shutil.rmtree(base)
    assert client.get('/api/v1/card-index/manifest').status_code == 503


def test_unlisted_prints_file_is_refused(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    _extended(root, base, list_prints=False)
    assert client.get('/api/v1/card-index/manifest').status_code == 503


def _other_model(root, active, *, model='38ce95cc1928', vectors=None, ids=None, catalogue=None):
    """Another picture model's vectors for the active index's rows, as published for run 4."""
    meta = json.loads((active / 'card_index.version.json').read_text())
    body = {name: (active / name).read_bytes() for name in meta['files']}
    if vectors is None:
        vectors = bytes(len(body['card_index.f16.bin']))
    body['card_index.f16.bin'] = vectors
    if ids is not None:
        body['card_index.ids.txt'] = ids
    files = {n: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for n, b in body.items()}
    identity = {k: v for k, v in meta.items() if k not in ('version', 'files', 'extends')}
    identity.update(model_id=model, variant_of=active.name, files=files)
    if catalogue is not None:
        identity['catalogue_version'] = catalogue
    version = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    identity['version'] = version
    folder = root / version
    folder.mkdir()
    for name, data in body.items():
        (folder / name).write_bytes(data)
    (folder / 'card_index.version.json').write_text(json.dumps(identity))
    (root / f'ACTIVE.{model}').write_text(version)
    return folder


def test_each_model_gets_its_own_index_of_the_same_rows(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    (root / 'ACTIVE').write_text(base.name)
    other = _other_model(root, base)
    plain = client.get('/api/v1/card-index/manifest').json()
    assert plain['version'] == base.name
    assert client.get(f'/api/v1/card-index/manifest?model={plain["model_id"]}').json() == plain
    tuned = client.get('/api/v1/card-index/manifest?model=38ce95cc1928').json()
    assert tuned['version'] == other.name and tuned['model_id'] == '38ce95cc1928'
    assert tuned['rows'] == plain['rows']
    vectors = next(f for f in tuned['files'] if f['name'] == 'card_index.f16.bin')
    assert client.get('/api/v1/' + vectors['url']).content == (other / 'card_index.f16.bin').read_bytes()


def test_other_model_index_of_an_extended_active_index(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    extended = _extended(root, base)
    other = _other_model(root, extended)
    tuned = client.get('/api/v1/card-index/manifest?model=38ce95cc1928').json()
    assert tuned['version'] == other.name and tuned['rows'] == 3
    assert 'card_index.prints.tsv' in {f['name'] for f in tuned['files']}


def test_unknown_or_malformed_model_has_no_index(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    (root / 'ACTIVE').write_text(base.name)
    assert client.get('/api/v1/card-index/manifest?model=aaaaaaaaaaaa').status_code == 404
    assert client.get('/api/v1/card-index/manifest?model=../ACTIVE').status_code == 404


def test_other_model_index_refused_when_its_rows_differ(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    (root / 'ACTIVE').write_text(base.name)
    _other_model(root, base, ids=b'a\nz\n')
    assert client.get('/api/v1/card-index/manifest?model=38ce95cc1928').status_code == 503
    assert client.get('/api/v1/card-index/manifest').status_code == 200


def test_other_model_index_refused_once_the_active_index_moves(tmp_path, monkeypatch):
    root, base, _, client = _served(tmp_path, monkeypatch)
    (root / 'ACTIVE').write_text(base.name)
    _other_model(root, base)
    assert client.get('/api/v1/card-index/manifest?model=38ce95cc1928').status_code == 200
    _extended(root, base)  # A new active index; run 4's still describes the old rows.
    assert client.get('/api/v1/card-index/manifest?model=38ce95cc1928').status_code == 503
