import json
import sqlite3
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.recognition.artifacts import ArtifactError
from app.recognition.artifacts import sha256_file
from app.recognition.local_match import LocalArtworkVerifier, FULL_ART_BOX, _pixels
from app.recognition.printing import ART_BOX, ReferencePrintingIndex, artwork_thumbnail
from app.recognition.reference_features import (
    ReferenceFeatureStore, SIFT_PROFILES, build_reference_bundle, extract_reference,
)
from app.recognition.runtime import Runtime


@pytest.fixture
def features(tmp_path):
    root = tmp_path / 'reference-images'
    root.mkdir()
    rng = np.random.default_rng(39)
    image = Image.new('RGB', (500, 700), 'lightgray')
    texture = rng.integers(0, 256, (310, 420, 3), dtype=np.uint8)
    patch = (texture * .35 + np.linspace(0, 160, 420)[None, :, None]).astype(np.uint8)
    image.paste(Image.fromarray(patch), (40, 120))
    image.save(root / 'card.png')
    rows = [dict(id='base', image_path=str(root / 'card.png'), rarity='Common'),
            dict(id='full', image_path=str(root / 'card.png'), rarity='Ultra Rare'),
            dict(id='missing', image_path=str(root / 'absent.png'), rarity='Common')]
    bundle = tmp_path / 'features'
    build_reference_bundle(rows, tmp_path, bundle)
    return tmp_path, image, rows, bundle


@pytest.mark.parametrize('box', [ART_BOX, FULL_ART_BOX])
@pytest.mark.parametrize('profile', SIFT_PROFILES)
def test_extraction_is_bitwise_equal_to_legacy_reference_extraction(features, box, profile):
    _, image, _, _ = features
    count, contrast = profile
    pixels = _pixels(image)
    h, w = pixels.shape
    mask = np.zeros_like(pixels)
    x0, y0, x1, y1 = box
    mask[round(y0*h)+8:round(y1*h)-8, round(x0*w)+8:round(x1*w)-8] = 255
    keys, desc = cv2.SIFT_create(nfeatures=count, contrastThreshold=contrast).detectAndCompute(pixels, mask)
    extracted = extract_reference(image, box, count, contrast)
    np.testing.assert_array_equal(extracted.points, np.float32([key.pt for key in keys]))
    np.testing.assert_array_equal(extracted.descriptors, desc)
    assert extracted.size == (w, h)


@pytest.mark.parametrize('profile', SIFT_PROFILES)
def test_roundtrip_is_lossless_and_does_not_need_original_images(features, profile):
    data_dir, image, rows, bundle = features
    store = ReferenceFeatureStore.load(bundle, rows)
    count, contrast = profile
    expected = extract_reference(image, ART_BOX, count, contrast)
    for path in (data_dir / 'reference-images').iterdir():
        path.unlink()
    actual = store.features('base', rows[0]['image_path'], ART_BOX, count, contrast)
    np.testing.assert_array_equal(actual.points, expected.points)
    np.testing.assert_array_equal(actual.descriptors, expected.descriptors)
    np.testing.assert_array_equal(store.thumbnail('base', rows[0]['image_path']), artwork_thumbnail(image))
    assert not actual.points.flags.writeable and not actual.descriptors.flags.writeable
    assert store.features('missing', rows[2]['image_path'], ART_BOX, count, contrast) is None


@pytest.mark.parametrize('kind', ['raw', 'slab'])
def test_matching_and_frame_recovery_identical_without_reference_files(features, kind):
    data_dir, image, rows, bundle = features
    photo = image.copy()
    if kind == 'slab':
        photo = Image.new('RGB', (850, 1300), 'darkgray')
        photo.paste(image, (175, 340))
    refs = [('base', rows[0]['image_path'])]
    legacy = LocalArtworkVerifier(data_dir)
    cv2.setRNGSeed(19)
    matches = legacy.verify(photo, refs)
    assert matches and matches[0].card_id == 'base'
    cv2.setRNGSeed(19)
    diagnostics = []
    frame = legacy.propose_frame(photo, refs[0], diagnostics)
    if kind == 'slab':
        assert frame is not None
    store = ReferenceFeatureStore.load(bundle, rows)
    (data_dir / 'reference-images' / 'card.png').unlink()
    reader = LocalArtworkVerifier(data_dir, feature_store=store)
    cv2.setRNGSeed(19)
    assert reader.verify(photo, refs) == matches
    cv2.setRNGSeed(19)
    stored_diagnostics = []
    stored_frame = reader.propose_frame(photo, refs[0], stored_diagnostics)
    assert stored_diagnostics == diagnostics
    assert (stored_frame is None) == (frame is None)
    if frame is not None:
        np.testing.assert_array_equal(np.asarray(stored_frame), np.asarray(frame))


def test_printing_family_and_missing_evidence_are_identical(features):
    data_dir, _, rows, bundle = features
    catalog = sqlite3.connect(':memory:')
    catalog.row_factory = sqlite3.Row
    catalog.execute('CREATE TABLE cards(id TEXT,image_path TEXT,name TEXT,language TEXT)')
    for row in rows:
        catalog.execute('INSERT INTO cards VALUES (?,?,?,?)', (row['id'], row['image_path'], 'Pikachu', 'en'))
    top = dict(card_id='base', name='Pikachu', language='en')
    expected = ReferencePrintingIndex(data_dir).family(catalog, top)
    store = ReferenceFeatureStore.load(bundle, rows)
    (data_dir / 'reference-images' / 'card.png').unlink()
    assert ReferencePrintingIndex(data_dir, feature_store=store).family(catalog, top) == expected
    assert expected[1] is True  # Missing sibling must still require review.


@pytest.mark.parametrize('field,value', [('schema_version', 'wrong'), ('processing', {}),
    ('catalogue_sha256', 'wrong'), ('cards', 0), ('available', 0), ('records', {})])
def test_bad_manifest_fails_closed(features, field, value):
    _, _, rows, bundle = features
    manifest = json.loads((bundle / 'manifest.json').read_text())
    manifest[field] = value
    (bundle / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ArtifactError):
        ReferenceFeatureStore.load(bundle, rows)


@pytest.mark.parametrize('change', ['id', 'image_path', 'rarity'])
def test_changed_catalogue_rejects_stale_features(features, change):
    _, _, rows, bundle = features
    rows[0][change] = 'changed'
    with pytest.raises(ArtifactError):
        ReferenceFeatureStore.load(bundle, rows)


def test_corrupt_file_and_unsupported_profile_never_fallback(features):
    _, _, rows, bundle = features
    store = ReferenceFeatureStore.load(bundle, rows)
    with pytest.raises(ArtifactError):
        store.features('base', rows[0]['image_path'], ART_BOX, 500, .04)
    with pytest.raises(ArtifactError):
        store.features('base', '/wrong/file.png', ART_BOX, 1000, .04)
    file = bundle / store.manifest['records']['base']['filename']
    file.write_bytes(b'corrupt')
    with pytest.raises(ArtifactError):
        store.features('base', rows[0]['image_path'], ART_BOX, 1000, .04)


def test_bundle_cannot_overwrite_existing_directory(features):
    data_dir, _, rows, bundle = features
    with pytest.raises(FileExistsError):
        build_reference_bundle(rows, data_dir, bundle)


def test_foreign_architecture_bundle_is_rejected(features):
    _, _, rows, bundle = features
    path = bundle / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['processing']['architecture'] = 'foreign-architecture'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ArtifactError, match='processing contract mismatch'):
        ReferenceFeatureStore.load(bundle, rows)


def test_startup_rejects_corrupt_feature_files(features):
    _, _, rows, bundle = features
    manifest = json.loads((bundle / 'manifest.json').read_text())
    (bundle / manifest['records']['base']['filename']).write_bytes(b'corrupt')
    with pytest.raises(ArtifactError):
        ReferenceFeatureStore.load(bundle, rows)


def test_invalid_opt_in_bundle_fails_readiness(tmp_path):
    assert Settings(_env_file=None).reference_features_dir is None
    runtime = Runtime(Settings(_env_file=None, reference_features_dir=tmp_path / 'missing'))
    runtime.snapshot = SimpleNamespace(card_ids=np.array(['base']))
    runtime.embedder = SimpleNamespace()
    catalog = sqlite3.connect(':memory:')
    catalog.row_factory = sqlite3.Row
    catalog.execute('CREATE TABLE cards(id TEXT,language TEXT,name TEXT,collector_number TEXT,printed_collector_number TEXT,image_path TEXT,rarity TEXT)')
    catalog.execute("INSERT INTO cards VALUES ('base','en','Pikachu','58','58/102','/data/reference-images/base.jpg','Common')")
    runtime.bind_card_languages(catalog)
    assert not runtime.ready and runtime.error


@pytest.mark.parametrize('field', ['filename', 'art_box', 'image_path', 'available', 'source_sha256'])
def test_record_metadata_cannot_redirect_or_change_reference(features, field):
    _, _, rows, bundle = features
    path = bundle / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['records']['base'][field] = '../outside.npz'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ArtifactError):
        ReferenceFeatureStore.load(bundle, rows)


@pytest.mark.parametrize('field', ['points_1000', 'descriptors_2000', 'size_1000', 'thumbnail'])
def test_invalid_array_values_fail_even_with_updated_checksum(features, field):
    _, _, rows, bundle = features
    path = bundle / 'manifest.json'
    manifest = json.loads(path.read_text())
    record = manifest['records']['base']
    file = bundle / record['filename']
    with np.load(file, allow_pickle=False) as source:
        arrays = {key: source[key] for key in source.files}
    if field == 'size_1000':
        arrays[field] = np.array([0, 700], np.int32)
    else:
        arrays[field].flat[0] = np.nan
    np.savez_compressed(file, **arrays)
    record['sha256'] = sha256_file(file)
    path.write_text(json.dumps(manifest))
    store = ReferenceFeatureStore.load(bundle, rows)
    with pytest.raises(ArtifactError):
        store.features('base', rows[0]['image_path'], ART_BOX, 1000, .04)


def test_blank_reference_preserves_absence_of_geometry_and_thumbnail(tmp_path):
    root = tmp_path / 'reference-images'
    root.mkdir()
    Image.new('RGB', (500, 700), 'white').save(root / 'blank.png')
    rows = [dict(id='blank', image_path=str(root / 'blank.png'), rarity='Common')]
    bundle = tmp_path / 'features'
    build_reference_bundle(rows, tmp_path, bundle)
    store = ReferenceFeatureStore.load(bundle, rows)
    assert store.manifest['available'] == 1
    assert store.features('blank', rows[0]['image_path'], ART_BOX, 1000, .04).descriptors is None
    assert store.thumbnail('blank', rows[0]['image_path']) is None


def test_parallel_builder_is_bitwise_equal_to_serial(features):
    data_dir, _, rows, bundle = features
    other = data_dir / 'parallel'
    build_reference_bundle(rows, data_dir, other, workers=3)
    # ZIP timestamps differ, so compare arrays, not archive byte hashes.
    serial = ReferenceFeatureStore.load(bundle, rows)
    parallel = ReferenceFeatureStore.load(other, rows)
    for row in rows:
        a = serial.read(row['id'], row['image_path'])
        b = parallel.read(row['id'], row['image_path'])
        assert (a is None) == (b is None)
        if a is not None:
            assert a.keys() == b.keys()
            for key in a:
                np.testing.assert_array_equal(a[key], b[key])
