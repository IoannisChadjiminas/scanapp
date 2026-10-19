import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.local_match import LocalArtworkMatch
from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.pipeline import recognize_bytes
from app.recognition.title_retry import read_conflicting_title, title_observations_agree, title_retry_allowed
from app.schemas import ScanStatus


def unresolved():
    return SimpleNamespace(response=SimpleNamespace(status=ScanStatus.uncertain),
        quality_retake=False, lead=dict(name='Torchic', strong_name_conflict=True),
        name_confidence=.94, languages=('en',), numbers=[],
        ocr=OcrResult(name_text='BASIc Charmar'), ranked=[dict(name='Torchic')],
        query_image=Image.new('RGB', (1000, 1400)))


@pytest.mark.parametrize('change', [
    dict(response=SimpleNamespace(status=ScanStatus.matched)),
    dict(response=SimpleNamespace(status=ScanStatus.printing_ambiguous)),
    dict(response=SimpleNamespace(status=ScanStatus.retake)),
    dict(quality_retake=True), dict(name_confidence=.84), dict(languages=()),
    dict(lead=dict(name='Torchic', strong_name_conflict=False)),
    dict(ocr=OcrResult(name_text=None)), dict(ocr=OcrResult(name_text='BASIc Charmar', failed=True)),
    dict(ranked=[dict(name='Torchic'), dict(name='BASIc Charmar')]),
    dict(numbers=[OcrHit('3/185', .99, 'collector')]),
    dict(numbers=[OcrHit('SWSH232', .99, 'collector')]),
    dict(query_image=Image.new('RGB', (300, 420))),
])
def test_successful_or_contradictory_identity_never_enters_title_retry(change):
    first = unresolved()
    assert title_retry_allowed(first)
    first.__dict__.update(change)
    assert not title_retry_allowed(first)


def test_focused_read_is_literal_compatible_and_does_not_mutate_first_observations():
    original = OcrResult(name_text='BASIc Charmar', collector_text='185',
        hits=[OcrHit('BASIc Charmar', .94, 'name'), OcrHit('185', .99, 'collector')])
    calls = []
    engine = SimpleNamespace(_run=lambda patch: calls.append(patch.size) or (['Charmander'], [.99]))
    augmented, record = read_conflicting_title(engine, Image.new('RGB', (1388, 1754)), original)
    assert len(calls) == 1 and record['reason'] == 'conflicting_title'
    assert original.name_text == 'BASIc Charmar' and len(original.hits) == 2
    assert augmented.name_text == 'Charmander' and augmented.collector_text == '185'
    assert augmented.hits[:2] == original.hits
    assert not title_observations_agree('Bulbasaur', 'Charmander')
    assert not title_observations_agree('Charmeleon', 'Charmander')
    assert not title_observations_agree('Mew VMAX', 'Mew V')


@pytest.mark.parametrize('enabled,verified,retry_title,expected', [
    (False, True, 'Charmander', 'wrong-00'),
    (True, True, 'Charmander', 'correct'),
    (True, False, 'Charmander', 'wrong-00'),
    (True, True, 'Bulbasaur', 'wrong-00'),
])
def test_recovery_requires_literal_title_and_independent_artwork_and_saves_once(
        tmp_path, monkeypatch, enabled, verified, retry_title, expected):
    monkeypatch.setattr('app.recognition.pipeline.detect_and_rectify', lambda im: (im, True))
    monkeypatch.setattr('app.recognition.pipeline.card_frame_candidates', lambda *a, **k: [])
    monkeypatch.setattr('app.recognition.pipeline.loose_frame_candidates', lambda *a, **k: [])
    monkeypatch.setattr('app.recognition.pipeline.portrait_window_candidates', lambda *a, **k: [])
    monkeypatch.setattr('app.recognition.pipeline.slab_interior_candidate', lambda *a, **k: None)
    catalog, results = connect(tmp_path/'catalog.sqlite'), connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    ids = [f'wrong-{i:02}' for i in range(20)] + ['correct']
    for cid in ids:
        catalog.execute('INSERT INTO cards '
            '(id,provider_id,name,set_id,set_name,collector_number,language) VALUES (?,?,?,?,?,?,?)',
            (cid, cid, 'Charmander' if cid == 'correct' else 'Torchic', cid, cid,
             '23' if cid == 'correct' else '3', 'en'))
    catalog.commit()
    scores = [.76 - .001*i for i in range(20)] + [.72]
    snapshot = SimpleNamespace(card_ids=np.array(ids), embeddings=np.array(
        [[s, np.sqrt(1-s*s)] for s in scores], dtype=np.float32))
    observed = OcrResult(name_text='BASIc Charmar', collector_text='185',
        hits=[OcrHit('BASIc Charmar', .94192, 'name'), OcrHit('185', .99913, 'collector')])
    reads = []
    engine = SimpleNamespace(read=lambda image: observed,
        _run=lambda patch: reads.append(patch.size) or ([retry_title], [.999]))
    def verify(image, references):
        return ([LocalArtworkMatch('correct', 33, 33, .15)]
                if verified and any(cid == 'correct' for cid, _ in references) else [])
    runtime = SimpleNamespace(require=lambda: (snapshot,
        SimpleNamespace(embed=lambda *args: np.array([1, 0], dtype=np.float32)), engine),
        card_languages=np.array(['en']*len(ids)), printing_index=None,
        artwork_verifier=SimpleNamespace(verify=verify),
        metadata_index=MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'), indexed_ids=set(ids)),
        versions=lambda: dict(model_revision='test', catalogue='test', ocr='test', ranking='test'),
        threshold_config=lambda: {})
    payload = io.BytesIO()
    Image.fromarray(np.random.default_rng(41).integers(0, 255, (825, 600, 3), dtype=np.uint8)).save(payload, format='JPEG')
    try:
        response = recognize_bytes(payload.getvalue(), settings=Settings(_env_file=None,
            data_dir=tmp_path, store_captures=False, ocr_conflict_title_retry=enabled),
            runtime=runtime, catalog=catalog, results=results, session_id='test', language='en', graded=False)
        assert response.best_match.card_id == expected
        assert response.status == 'uncertain' and response.confidence.requires_confirmation
        assert len(reads) == int(enabled)
        saved = results.execute('SELECT ocr_json FROM scans').fetchall()
        assert len(saved) == 1
        evidence = json.loads(saved[0][0])
        assert evidence.get('title_recovery', {}).get('selected', False) == (expected == 'correct')
        if expected == 'correct':
            assert evidence['title_recovery']['original_name'] == 'BASIc Charmar'
            assert evidence['name_text'] == 'Charmander'
            assert {'text': '185', 'confidence': .99913, 'region': 'collector'} in evidence['hits']
    finally:
        catalog.close()
        results.close()
