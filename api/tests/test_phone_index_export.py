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
    np.save(snapshot / 'embedding_card_ids.npy', np.array(['en:b', 'en:a']))
    manifest = {'preprocess_config': 'pad', 'embedding_dim': 384, 'dinov2_sha256': model_hash,
                'embeddings_sha256': exporter.digest(snapshot / 'embeddings.npy'),
                'ids_sha256': exporter.digest(snapshot / 'embedding_card_ids.npy'),
                'indexed_count': 2, 'indexed_ids': ['en:b', 'en:a'], 'catalogue_version': 'test'}
    (snapshot / 'manifest.json').write_text(json.dumps(manifest))
    catalogue = tmp_path / 'catalogue.db'
    with sqlite3.connect(catalogue) as db:
        db.execute('CREATE TABLE cards (id TEXT, name TEXT, collector_number TEXT, printed_collector_number TEXT, language TEXT, set_id TEXT)')
        db.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?)', [
            ('en:a', 'Alpha', '1', None, 'en', 'en:set'), ('en:b', 'Beta', '2', '02', 'en', 'set')])
        db.execute('CREATE TABLE set_totals (language TEXT, set_id TEXT, official_total INTEGER)')
        db.execute("INSERT INTO set_totals VALUES ('en','set',100)")
    return snapshot, catalogue, model


def test_export_preserves_rows_and_hashes(tmp_path, monkeypatch):
    snapshot, catalogue, model = fixture(tmp_path, monkeypatch)
    target = exporter.export(snapshot, catalogue, catalogue, model, tmp_path / 'output')
    assert (target / 'card_index.ids.txt').read_text() == 'en:b\nen:a\n'
    assert (target / 'card_index.meta.tsv').read_text().splitlines() == [
        exporter.HEADER.rstrip('\n'), 'en:b\tBeta\t2\t02\t100\ten\t\t', 'en:a\tAlpha\t1\t\t100\ten\t\t']
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
    target.write_text('en:a\nen:b\n')  # Same size; changed mtime must invalidate the cache.
    os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000))
    assert client.get('/api/v1/' + index['url']).status_code == 404


def test_printed_fraction_and_promo_code():
    identity = exporter.row_identity
    assert identity('006', '006/163', 'en', 'PPS1-BST', None) == ('163', '')
    assert identity('006', '006/080', 'ja', 'L2', 70) == ('80', '')  # printed total wins
    assert identity('TG01', 'TG01/TG30', 'en', 'swsh12tg', 195) == ('30', '')
    assert identity('u64', '002/S-P', 'ja', 'SP', None) == ('', 'S-P')
    assert identity('001', '', 'ja', 'SV-P', 288) == ('', 'SV-P')  # promo: code, no total
    assert identity('001', '', 'en', 'SP', 300) == ('300', '')  # only Japanese promos
    assert identity('001/032', '', 'ja', 'cll', None) == ('32', '')  # fraction in the number
    assert identity('A', 'A/28', 'en', 'ex10', 115) == ('28', '')
    assert identity('12', '', 'ja', 'S1W', 60) == ('60', '')


def test_checks_fail_unless_recorded():
    rows = [('ja:X-1', 'Pikachu', '1', '', '10', 'ja', '', ''),
            ('base1-1', 'Alakazam', '1', '', '102', 'en', '', 'duplicate'),
            ('en:A1-001', 'Bulbasaur', '001', '', '', 'en', '', 'digital'),
            ('en:Y-1', 'Eevee', '1', '1/9', '', 'en', '', ''),
            ('ja:X-2', 'ピカチュウ', '2', '', '10', 'ja', '', '')]
    found = exporter.check_rows(rows)
    assert found == {'unprefixed_id': ['base1-1'], 'latin_name_ja': ['ja:X-1'],
                     'missing_total': ['en:Y-1'], 'digital_set': ['en:A1-001']}
    assert exporter.check_failures(found, found) == {}
    assert exporter.check_failures(found, {**found, 'latin_name_ja': []}) == {'latin_name_ja': ['ja:X-1']}


def test_row_kinds():
    from app import phone_index_subset as rule
    ids = ['en:base1-1', 'base1-1', 'extra-mew', 'zh-tw:SV1-1', 'en:A1-001', 'en:P-A-001',
           'en:A1a-001', 'ja:SV1-1', 'en:sv1-1', 'en:bw1-1']
    assert rule.row_kinds(ids) == ['', 'duplicate', 'reference', 'language', 'digital', 'digital',
                                   'digital', '', '', '']
    assert rule.subset_ids(ids, ['language', 'duplicate']) == [
        'en:base1-1', 'extra-mew', 'en:A1-001', 'en:P-A-001', 'en:A1a-001', 'ja:SV1-1', 'en:sv1-1', 'en:bw1-1']
    with pytest.raises(ValueError):
        rule.subset_ids(ids, ['reference'])


def test_subset_index_is_served_only_for_its_snapshot(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import card_index
    from app.routes.card_index import router

    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    model = tmp_path / 'model'
    model.write_bytes(b'model')
    model_hash = hashlib.sha256(b'model').hexdigest()
    monkeypatch.setattr(exporter, 'MODEL_ID', model_hash[:12])
    monkeypatch.setattr(card_index, '_MODEL_ID', model_hash[:12])
    ids = ['en:base1-1', 'base1-1', 'zh-tw:S1-1', 'ja:S1-1']
    vectors = np.zeros((4, 384), dtype=np.float32)
    for i in range(4):
        vectors[i, i] = 1
    np.save(snapshot / 'embeddings.npy', vectors)
    np.save(snapshot / 'embedding_card_ids.npy', np.array(ids))
    manifest = {'preprocess_config': 'pad', 'embedding_dim': 384, 'dinov2_sha256': model_hash,
                'embeddings_sha256': exporter.digest(snapshot / 'embeddings.npy'),
                'ids_sha256': exporter.digest(snapshot / 'embedding_card_ids.npy'),
                'indexed_count': 4, 'indexed_ids': ids, 'catalogue_version': 'test'}
    (snapshot / 'manifest.json').write_text(json.dumps(manifest))
    catalogue = tmp_path / 'catalogue.db'
    with sqlite3.connect(catalogue) as db:
        db.execute('CREATE TABLE cards (id TEXT, name TEXT, collector_number TEXT, printed_collector_number TEXT, language TEXT, set_id TEXT)')
        db.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?)', [
            ('en:base1-1', 'Alakazam', '1', None, 'en', 'base1'), ('base1-1', 'Alakazam', '1', None, 'en', 'base1'),
            ('zh-tw:S1-1', '皮卡丘', '1', '001/100', 'zh-tw', 'S1'), ('ja:S1-1', 'ピカチュウ', '1', '001/100', 'ja', 'S1')])
        db.execute('CREATE TABLE set_totals (language TEXT, set_id TEXT, official_total INTEGER)')
        db.execute("INSERT INTO set_totals VALUES ('en','base1',102)")
    root = tmp_path / 'output'
    with pytest.raises(ValueError, match='unprefixed_id 1'):
        exporter.export(snapshot, catalogue, catalogue, model, root)
    report = tmp_path / 'report.json'
    candidate = exporter.export(snapshot, catalogue, catalogue, model, root,
                                exclude=('language', 'duplicate'), report=report)
    assert json.loads(report.read_text())['counts']['unprefixed_id'] == 0
    assert (candidate / 'card_index.ids.txt').read_text() == 'en:base1-1\nja:S1-1\n'
    stored = np.fromfile(candidate / 'card_index.f16.bin', dtype='<f2').reshape(2, 384)
    assert stored[0, 0] == 1 and stored[1, 3] == 1
    version = json.loads((candidate / 'card_index.version.json').read_text())
    assert version['rows'] == 2 and version['subset'] == {
        'rule': 'phone-subset-v1', 'excluded': ['duplicate', 'language'], 'source_rows': 4}
    (root / 'ACTIVE').write_text(candidate.name)
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.state.settings = SimpleNamespace(card_index_publish=True, card_index_publish_dir=root)
    loaded = SimpleNamespace(catalogue_version='test', ids_sha256=manifest['ids_sha256'],
                             embeddings_sha256=manifest['embeddings_sha256'], indexed_count=4,
                             embedding_dim=384, manifest=manifest, card_ids=np.array(ids),
                             embeddings=vectors)
    app.state.runtime = SimpleNamespace(snapshot=loaded)
    client = TestClient(app)
    result = client.get('/api/v1/card-index/manifest')
    assert result.status_code == 200 and result.json()['rows'] == 2
    # Same hashes claimed, other vectors loaded: the recomputed subset no longer matches.
    changed = vectors.copy()
    changed[3, 3], changed[3, 4] = 0, 1
    card_index._subsets.clear()
    app.state.runtime.snapshot = SimpleNamespace(**{**vars(loaded), 'embeddings': changed})
    assert client.get('/api/v1/card-index/manifest').status_code == 503
    # Another rule than the one the index was cut with is refused.
    card_index._subsets.clear()
    app.state.runtime.snapshot = loaded
    version['subset']['excluded'] = ['language']
    assert not card_index._rows_match(version, loaded)
