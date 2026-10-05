import hashlib
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from assemble_reference_feature_release import assemble
from app.recognition.artifacts import ArtifactError, sha256_file
from app.recognition.reference_features import build_reference_bundle, ReferenceFeatureStore


@pytest.fixture
def release(tmp_path):
    images = tmp_path / 'reference-images'
    images.mkdir()
    Image.new('RGB', (240, 340), 'orange').save(images / 'one.png')
    rows = [dict(id='one', image_path=str(images / 'one.png'), rarity='Common'),
            dict(id='missing', image_path=str(images / 'absent.png'), rarity='Common')]
    parent = tmp_path / 'parent'
    manifest = build_reference_bundle(rows, tmp_path, parent)
    sources = {k: r.get('source_sha256') for k, r in manifest['records'].items()}
    return tmp_path, parent, rows, sources, manifest


def test_reuse_preserves_parent_and_uses_independent_manifest(release):
    root, parent, rows, sources, manifest = release
    before = sha256_file(parent / 'manifest.json')
    output = root / 'release'
    result = assemble(parent, rows, rows, output, sources)
    filename = manifest['records']['one']['filename']
    assert (output / filename).stat().st_ino == (parent / filename).stat().st_ino
    assert (output / 'manifest.json').stat().st_ino != (parent / 'manifest.json').stat().st_ino
    assert sha256_file(parent / 'manifest.json') == before
    assert result['available'] == result['parent_files'] == 1
    assert result['delta_files'] == 0
    assert ReferenceFeatureStore.load(output, rows).read('missing', rows[1]['image_path']) is None
    with pytest.raises(FileExistsError):
        assemble(parent, rows, rows, output, sources)


def test_changed_source_at_same_path_requires_delta(release):
    root, parent, rows, sources, _ = release
    sources['one'] = 'a' * 64
    with pytest.raises(ArtifactError, match='Source selection mismatch'):
        assemble(parent, rows, rows, root / 'release', sources)
    assert not (root / 'release').exists()


def test_changed_layout_requires_delta(release):
    root, parent, rows, sources, _ = release
    changed = [dict(rows[0], rarity='Ultra Rare'), rows[1]]
    with pytest.raises(ArtifactError, match='requires a validated delta'):
        assemble(parent, rows, changed, root / 'release', sources)


def test_delta_replaces_feature_without_writing_parent(release):
    root, parent, rows, sources, old = release
    before = sha256_file(parent / old['records']['one']['filename'])
    Image.new('RGB', (240, 340), 'blue').save(rows[0]['image_path'])
    delta = root / 'delta'
    new = build_reference_bundle(rows[:1], root, delta)
    sources['one'] = new['records']['one']['source_sha256']
    output = root / 'release'
    result = assemble(parent, rows, rows, output, sources, delta)
    filename = new['records']['one']['filename']
    assert result['delta_files'] == 1
    assert (output / filename).stat().st_ino != (parent / filename).stat().st_ino
    assert (output / filename).stat().st_ino == (delta / filename).stat().st_ino
    assert sha256_file(parent / filename) == before


def test_corrupt_parent_cannot_be_reused(release):
    root, parent, rows, sources, manifest = release
    (parent / manifest['records']['one']['filename']).write_bytes(b'corrupt')
    with pytest.raises(ArtifactError, match='checksum mismatch'):
        assemble(parent, rows, rows, root / 'release', sources)
    assert not (root / 'release').exists()


def test_incomplete_source_selection_is_rejected(release):
    root, parent, rows, sources, _ = release
    sources.pop('missing')
    with pytest.raises(ArtifactError, match='every candidate ID'):
        assemble(parent, rows, rows, root / 'release', sources)


def test_cross_filesystem_failure_leaves_no_activatable_manifest(release, monkeypatch):
    import errno
    import assemble_reference_feature_release as module
    root, parent, rows, sources, _ = release
    before = sha256_file(parent / 'manifest.json')
    def fail(*args, **kwargs):
        raise OSError(errno.EXDEV, 'Cross-device link')
    monkeypatch.setattr(module.os, 'link', fail)
    with pytest.raises(OSError):
        assemble(parent, rows, rows, root / 'release', sources)
    assert not (root / 'release/manifest.json').exists()
    assert sha256_file(parent / 'manifest.json') == before
