import pytest
from PIL import Image
import io
from types import SimpleNamespace
import numpy as np

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition import pipeline
from app.recognition.identity import structured_identity_agrees, review_title_agrees

from app.recognition.ocr import CardOcr, OcrHit, OcrResult, pick_name_line
from app.recognition.rank import rerank, decide_status


@pytest.mark.parametrize('observed,expected', [
    ('サーナイトビマ', True), ('サーナイトドマ', True), ('サーナイトGX', False),
    ('サーナイトVMAX', False), ('ピカチュウ', False), ('サーナイト別のカード', False),
])
def test_localized_suffix_damage_can_support_review_not_a_different_mechanic(observed, expected):
    assert review_title_agrees(observed, 'サーナイトex') is expected


@pytest.mark.parametrize('number,confidence,expected', [
    ('101/078', .99, True), ('102/078', .99, False),
    ('101/078', .6, False), ('101', .99, False),
])
def test_suffix_review_rescue_requires_explicit_matching_collector(number, confidence, expected):
    row = dict(name='サーナイトex',language='ja',collector_number='101',printed_collector_number='101/078')
    assert structured_identity_agrees(row,ocr_name='サーナイトビマ',name_confidence=.86,
        numbers=[OcrHit(number,confidence,'collector')],languages=('ja',)) is expected


@pytest.mark.parametrize('badge', ['1進化', '2進化', '２ 進化', 'キルリアから進化'])
def test_evolution_labels_do_not_supply_card_identity(badge):
    assert pick_name_line([badge, 'サーナイトex']) == 'サーナイトex'
    assert pick_name_line([badge]) is None


def candidate(identifier, language, score, number='44'):
    return dict(card_id=identifier, name='Example', language=language,
                visual_score=score, collector_number=number)


def test_bare_roi_numbers_do_not_prefer_a_foreign_language():
    ranked = rerank([candidate('foreign', 'ja', .85), candidate('local', 'en', .88)],
        None, [OcrHit('2', .99, 'collector')], False,
        detected_languages=('en',), require_confident_ocr=True)
    assert ranked[0]['card_id'] == 'local'
    assert decide_status(ranked, enable_matched=True, min_visual=.78,
                         min_gap=.04, retake=False) == 'uncertain'


def test_language_preference_does_not_override_structured_number_conflict():
    ranked = rerank([candidate('foreign', 'ja', .85, '43'), candidate('local', 'en', .82)],
        None, [OcrHit('43/70', .99, 'collector')], False,
        detected_languages=('en',), require_confident_ocr=True)
    assert ranked[0]['card_id'] == 'foreign'
    assert ranked[0]['language_conflict']
    assert decide_status(ranked, enable_matched=True, min_visual=.78,
                         min_gap=.04, retake=False) != 'matched'


def test_footer_tiles_contribute_only_confident_identifiers():
    ocr = object.__new__(CardOcr)
    responses = iter([(['Example'], [.99]), (['retreat', '30'], [.99, .99]),
                      (['25', '99/102'], [.99, .6]), (['58/102'], [.99])])
    ocr._run = lambda image: next(responses)
    result = ocr.read(Image.new('RGB', (1000, 1400)))
    assert not result.failed
    assert result.collector_retry_used and result.collector_retry_contributed
    assert result.collector_text == '58/102'
    assert '99/102' not in result.lines
    assert result.lines.count('30') == 1  # Original observations retained.


def test_footer_retry_does_not_replace_an_existing_fraction():
    ocr = object.__new__(CardOcr)
    responses = iter([(['Example'], [.99]), (['59/102'], [.99])])
    ocr._run = lambda image: next(responses)
    result = ocr.read(Image.new('RGB', (1000, 1400)))
    assert not result.failed and not result.collector_retry_used
    assert result.collector_text == '59/102'


@pytest.mark.parametrize('retry,expected', [('サーナイトex', 'サーナイトex'),
                                          ('ピカチュウ', 'サーナイトドマ')])
def test_title_retry_requires_text_compatibility(retry, expected):
    ocr = object.__new__(CardOcr)
    responses = iter([(['2進化', 'サーナイトドマ'], [.99, .86]),
                      (['101/078'], [.99]), ([retry], [.99])])
    ocr._run = lambda image: next(responses)
    result = ocr.read(Image.new('RGB', (1080, 1080)))
    assert not result.failed and result.name_text == expected
    assert 'サーナイトドマ' in result.lines  # Prior evidence retained.


@pytest.mark.parametrize('raw_name,expected', [('Example', 'correct'), ('Unrelated', 'wrong')])
def test_inferred_window_consults_raw_footer_only_for_agreeing_title(tmp_path, monkeypatch, raw_name, expected):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    for identifier, number in [('wrong', '87/130'), ('correct', '58/102')]:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES(?,?,?,?,?,?,?,?)',
            (identifier, identifier, 'Example', identifier, identifier, number, number, 'en'))
    catalog.commit()
    noise = Image.fromarray(np.random.default_rng(9).integers(0,255,(900,700,3),dtype=np.uint8))
    frame = noise.crop((100,100,600,800))
    def oriented(*args, selection_metadata, **kwargs):
        selection_metadata.update(profile='window_0.85', alternate_hypotheses=1)
        return frame, np.array([0,1]), np.array([.94,.91]), {}
    monkeypatch.setattr(pipeline, 'retrieve_oriented', oriented)
    monkeypatch.setattr(pipeline, 'detect_and_rectify', lambda image:(image,False))
    monkeypatch.setattr(pipeline, 'card_frame_candidates', lambda *a,**k:[])
    monkeypatch.setattr(pipeline, 'loose_frame_candidates', lambda *a,**k:[])
    def read(image):
        raw = image.size == noise.size
        title = raw_name if raw else 'Example'
        return OcrResult(name_text=title, hits=[OcrHit(title,.99,'name'),
            *([OcrHit('58/102',.99,'collector')] if raw else [])])
    runtime = SimpleNamespace(require=lambda:(
        SimpleNamespace(card_ids=np.array(['wrong','correct']),embeddings=np.eye(2,dtype=np.float32)),
        SimpleNamespace(embed=lambda *a:np.array([1.,0.],dtype=np.float32)),SimpleNamespace(read=read)),
        card_languages=np.array(['en','en']),printing_index=None,
        threshold_config=lambda:{},
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'))
    payload = io.BytesIO()
    noise.save(payload,format='JPEG')
    try:
        response = pipeline.recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,
            data_dir=tmp_path,enable_matched=True,store_captures=False),runtime=runtime,
            catalog=catalog,results=results,session_id='test',language='en')
        assert response.best_match.card_id == expected
        assert response.status.value != 'matched'
    finally:
        catalog.close()
        results.close()
