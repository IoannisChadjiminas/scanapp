import copy
import importlib.util
import json
from pathlib import Path
import platform
import sqlite3
import sys

import numpy as np
from PIL import Image
import pytest

spec = importlib.util.spec_from_file_location(
    'build_reference_features', Path(__file__).resolve().parents[1] / 'scripts' / 'build_reference_features.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def data_dir(tmp_path):
    root = tmp_path / 'reference-images'
    root.mkdir()
    rng = np.random.default_rng(7)
    for name in ('a', 'b'):
        image = Image.new('RGB', (500, 700), 'lightgray')
        image.paste(Image.fromarray(rng.integers(0, 256, (310, 420, 3), dtype=np.uint8)), (40, 120))
        image.save(root / f'{name}.png')
    with sqlite3.connect(tmp_path / 'catalog.sqlite') as db:
        db.execute('CREATE TABLE cards (id TEXT PRIMARY KEY, image_path TEXT, rarity TEXT)')
        db.executemany('INSERT INTO cards VALUES (?,?,?)', [
            ('a', str(root / 'a.png'), 'Common'), ('b', str(root / 'b.png'), 'Ultra Rare'),
            ('c', str(root / 'absent.png'), 'Common')])
    vectors = tmp_path / 'vectors' / 'pad'
    vectors.mkdir(parents=True)
    (vectors / 'manifest.json').write_text(json.dumps({'exported_from': {'import_id': 'PS-TEST'}}))
    return tmp_path


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', ['build_reference_features.py', *map(str, argv)])
    builder.main()


def other_architecture(manifest):
    other = copy.deepcopy(manifest)
    other['processing'].update(architecture='other-arch', opencv_build_sha256='0' * 64)
    return other


def test_native_build_passes_strict_checks(data_dir, monkeypatch, capsys):
    run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'out',
        '--expect-architecture', platform.machine(), '--expect-import-id', 'PS-TEST',
        '--expect-cards', 3, '--native-check', 5)
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary['architecture'] == platform.machine()
    assert (summary['cards'], summary['available'], summary['native_check']) == (3, 2, {'cards': 2, 'deltas': []})


@pytest.mark.parametrize('flag, value', [('--expect-architecture', 'not-this-host'),
                                         ('--expect-import-id', 'PS-OTHER'), ('--expect-cards', 4)])
def test_wrong_host_or_release_is_refused_before_building(data_dir, monkeypatch, flag, value):
    with pytest.raises(SystemExit, match='Refusing'):
        run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'out', flag, value)
    assert not (data_dir / 'out').exists()


def test_other_architecture_may_differ_only_in_architecture_fields(data_dir, monkeypatch, capsys):
    run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'first')
    manifest = json.loads((data_dir / 'first' / 'manifest.json').read_text())
    result = builder.compare_manifests(manifest, other_architecture(manifest), partial=False)
    assert result['problems'] == []
    assert result['changed_processing_fields'] == ['architecture', 'opencv_build_sha256']

    other = other_architecture(manifest)
    other['processing']['pixel_size'] = 640
    other['records']['a']['source_sha256'] = 'f' * 64
    other['records']['c']['available'] = True
    other['catalogue_sha256'] = '0' * 64
    problems = builder.compare_manifests(manifest, other, partial=False)['problems']
    assert any('pixel_size' in p for p in problems)
    assert any('catalogue_sha256' in p for p in problems)
    assert any(p.startswith('source image checksum differs on 1') for p in problems)
    assert any(p.startswith('availability differs on 1') for p in problems)


def test_rejected_comparison_unpublishes_the_bundle(data_dir, monkeypatch):
    run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'first')
    other = other_architecture(json.loads((data_dir / 'first' / 'manifest.json').read_text()))
    other['processing']['opencv'] = '0.0.0'
    (data_dir / 'other.json').write_text(json.dumps(other))
    with pytest.raises(SystemExit, match='beyond the architecture fields'):
        run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'second',
            '--compare-manifest', data_dir / 'other.json')
    assert not (data_dir / 'second' / 'manifest.json').exists()
    assert (data_dir / 'second' / 'manifest.rejected.json').exists()


def test_smoke_subset_compares_against_full_bundle(data_dir, monkeypatch, capsys):
    run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'full')
    (data_dir / 'other.json').write_text(json.dumps(other_architecture(
        json.loads((data_dir / 'full' / 'manifest.json').read_text()))))
    capsys.readouterr()
    run(monkeypatch, '--data-dir', data_dir, '--output', data_dir / 'smoke', '--limit', 2,
        '--compare-manifest', data_dir / 'other.json')
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary['subset'] and summary['cards'] == 2
    assert summary['compared']['compared_cards'] == 2 and summary['compared']['problems'] == []
