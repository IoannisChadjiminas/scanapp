import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.recognition.artifacts import ArtifactError, sha256_file
from app.recognition.artwork import ArtworkIndex, PROFILES, SCHEMA_VERSION, crop_profile
from app.recognition.runtime import Runtime


@pytest.fixture
def bundle(tmp_path):
    model = tmp_path / 'model.onnx'
    model.write_bytes(b'test-model')
    snapshot = SimpleNamespace(embeddings_sha256='full-sha', ids_sha256='ids-sha',
                               preprocess_config='pad', embedding_dim=2)
    directory = tmp_path / 'index'
    directory.mkdir()
    records = [{'card_id':'base', 'profile':p, 'language':'en'} for p in PROFILES]
    records.append({'card_id':'reprint', 'profile':'conventional_window', 'language':'ja'})
    np.save(directory / 'embeddings.npy', np.array([[1,0],[.8,.6],[1,0]], dtype=np.float32))
    (directory / 'records.json').write_text(json.dumps(records))
    manifest = dict(schema_version=SCHEMA_VERSION, base_embeddings_sha256='full-sha',
        base_ids_sha256='ids-sha', model_sha256=sha256_file(model), preprocess_config='pad',
        profiles={p:list(box) for p,box in PROFILES.items()}, indexed_regions=3, indexed_cards=2)
    for name,key in (('embeddings.npy','embeddings_sha256'),('records.json','records_sha256')):
        manifest[key] = sha256_file(directory / name)
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    return directory, dict(snapshot=snapshot, model_path=model, known_ids={'base','reprint'},
                           known_languages={'base':'en','reprint':'ja'})


def rewrite_manifest(directory, **changes):
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest.update(changes)
    (directory / 'manifest.json').write_text(json.dumps(manifest))


def test_load_is_readonly_and_retains_printings(bundle):
    directory, kwargs = bundle
    index = ArtworkIndex.load(directory, **kwargs)
    assert len(index.records) == 3
    assert not index.embeddings.flags.writeable
    with pytest.raises(ValueError):
        index.embeddings[0,0] = .2


@pytest.mark.parametrize('field,value', [
    ('schema_version','unknown'), ('base_embeddings_sha256','wrong'),
    ('base_ids_sha256','wrong'), ('model_sha256','wrong'), ('preprocess_config','stretch'),
    ('profiles',{}), ('indexed_cards',99), ('indexed_regions',99),
    ('embeddings_sha256','wrong'), ('records_sha256','wrong')])
def test_rejects_incompatible_bundle(bundle, field, value):
    directory, kwargs = bundle
    rewrite_manifest(directory, **{field:value})
    with pytest.raises(ArtifactError):
        ArtworkIndex.load(directory, **kwargs)


@pytest.mark.parametrize('mutation', ['unknown_id','unknown_profile','duplicate','language','missing_language','malformed'])
def test_rejects_bad_records_even_with_updated_hash(bundle, mutation):
    directory, kwargs = bundle
    path = directory / 'records.json'
    records = json.loads(path.read_text())
    if mutation == 'unknown_id': records[0]['card_id'] = 'absent'
    elif mutation == 'unknown_profile': records[0]['profile'] = 'unvalidated'
    elif mutation == 'duplicate': records[1] = records[0]
    elif mutation == 'language': records[0]['language'] = 'ja'
    elif mutation == 'missing_language': del records[0]['language']
    else: records[0] = None
    path.write_text(json.dumps(records))
    rewrite_manifest(directory, records_sha256=sha256_file(path))
    with pytest.raises(ArtifactError): ArtworkIndex.load(directory, **kwargs)


@pytest.mark.parametrize('vectors', [np.zeros((3,2),dtype=np.float32),
    np.array([[np.nan,0],[1,0],[1,0]],dtype=np.float32), np.ones((2,2),dtype=np.float32),
    np.ones((3,2),dtype=np.float64)])
def test_rejects_bad_vectors_even_with_updated_hash(bundle, vectors):
    directory, kwargs = bundle
    np.save(directory / 'embeddings.npy', vectors)
    rewrite_manifest(directory, embeddings_sha256=sha256_file(directory / 'embeddings.npy'))
    with pytest.raises(ArtifactError): ArtworkIndex.load(directory, **kwargs)


def test_missing_or_malformed_bundle_reports_artifact_error(bundle):
    directory, kwargs = bundle
    (directory / 'manifest.json').write_text('not JSON')
    with pytest.raises(ArtifactError): ArtworkIndex.load(directory, **kwargs)
    with pytest.raises(ArtifactError): ArtworkIndex.load(directory / 'missing', **kwargs)


def test_search_deduplicates_regions_not_shared_art_printings(bundle):
    directory, kwargs = bundle
    index = ArtworkIndex.load(directory, **kwargs)
    embedder = SimpleNamespace(embed=lambda *args: pytest.fail('as-is vector should be reused'))
    hits, timings = index.search(Image.new('RGB',(600,300)), embedder, mode='pad',
                                as_supplied_vector=np.array([1,0],dtype=np.float32), k=2)
    assert {h.card_id for h in hits} == {'base','reprint'}
    assert len(hits) == 2 and all(h.score == 1 and h.query_profile == 'as_supplied' for h in hits)
    assert timings['artwork_retrieve_ms'] >= 0
    english, _ = index.search(Image.new('RGB',(600,300)), embedder, mode='pad',
        as_supplied_vector=np.array([1,0],dtype=np.float32), languages=('en',))
    assert [h.card_id for h in english] == ['base']


def test_portrait_hypotheses_do_not_stretch_or_replace_full_stream(bundle):
    directory, kwargs = bundle
    index = ArtworkIndex.load(directory, **kwargs)
    sizes = []
    def embed(image, mode):
        sizes.append(image.size)
        return np.array([1,0],dtype=np.float32)
    index.search(Image.new('RGB',(600,825)), SimpleNamespace(embed=embed), mode='pad',
                 as_supplied_vector=np.array([1,0],dtype=np.float32))
    assert sizes == [crop_profile(Image.new('RGB',(600,825)),p).size for p in PROFILES]
    assert len(sizes) == 2


def test_empty_language_or_limit_never_embeds(bundle):
    directory, kwargs = bundle
    index = ArtworkIndex.load(directory, **kwargs)
    embedder = SimpleNamespace(embed=lambda *args: pytest.fail('empty search must not embed'))
    for args in ({'languages':('fr',)}, {'k':0}):
        hits,timing = index.search(Image.new('RGB',(600,825)),embedder,mode='pad',**args)
        assert hits == [] and all(ms == 0 for ms in timing.values())


def test_config_is_opt_in_and_invalid_bundle_fails_readiness(tmp_path):
    assert Settings(_env_file=None).artwork_bundle_dir is None
    runtime = Runtime(Settings(_env_file=None, artwork_bundle_dir=tmp_path / 'missing'))
    runtime.snapshot = SimpleNamespace(card_ids=np.array(['base']))
    runtime.embedder = SimpleNamespace()
    import sqlite3
    with sqlite3.connect(':memory:') as catalog:
        catalog.row_factory = sqlite3.Row
        catalog.execute('CREATE TABLE cards(id TEXT, language TEXT, name TEXT, collector_number TEXT, printed_collector_number TEXT)')
        catalog.execute("INSERT INTO cards VALUES ('base','en','Pikachu','58','58/102')")
        runtime.bind_card_languages(catalog)
    assert not runtime.ready and runtime.error
    with pytest.raises(ArtifactError): runtime.require()
