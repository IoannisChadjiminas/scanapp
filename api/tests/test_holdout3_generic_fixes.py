"""No card IDs, titles or photo-specific acceptance exceptions."""
import pytest

from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import OcrHit, pick_name_line, pick_confident_name
from app.recognition.rank import extract_collector_candidates


def test_japanese_rarity_footer_disambiguates_set_code_from_collector():
    hits = [OcrHit('sv9',.99,'collector'), OcrHit('125/100 SAR',.99,'collector')]
    assert [h.text for h in extract_collector_candidates([],hits)] == ['125/100']
    # A shiny-vault ID remains evidence without Japanese footer context.
    assert [h.text for h in extract_collector_candidates([], [OcrHit('SV7',.99,'collector')])] == ['SV7']
    assert [h.text for h in extract_collector_candidates([], [OcrHit('SV7/SV94',.99,'collector')])] == ['SV7','SV94']


@pytest.mark.parametrize('rule', ['サポートは、自分の番に１枚しか使えない。',
                                 'サボートは、自分の番に1枚しか使えない。',
                                 'サポートは自分の番に1枚しか使えない'])
def test_supporter_instructions_are_not_titles(rule):
    assert pick_name_line([rule]) is None
    assert pick_name_line([rule, 'Example']) == 'Example'
    assert pick_confident_name(['Example', rule], [.8, .99]) == 'Example'


def title_index():
    rows = [dict(id='a',name='Example VSTAR',language='en',collector_number='001'),
            dict(id='b',name='Example VSTAR',language='en',collector_number='002'),
            dict(id='foreign',name='Example VSTAR',language='ja',collector_number='003'),
            dict(id='different',name='Example V',language='en',collector_number='004'),
            dict(id='missing',name='Example VSTAR',language='en',collector_number='005')]
    return MetadataCandidateIndex(rows,indexed_ids={'a','b','foreign','different'})


def query(**overrides):
    args = dict(ocr_name='ExampleVSTAR',name_confidence=.99,numbers=[],languages=('en',))
    args.update(overrides)
    return title_index().title_candidates(**args)


def test_title_proposal_preserves_all_same_language_printings():
    assert query() == ['a','b']
    assert query(ocr_name='Example V') == ['different']


@pytest.mark.parametrize('overrides', [dict(name_confidence=.84),dict(ocr_name=None),
    dict(languages=()),dict(limit=1),dict(ocr_name='Unrelated'),
    dict(numbers=[OcrHit('099/100',.99,'collector')]),
    dict(numbers=[OcrHit('GG01',.99,'collector')])])
def test_missing_weak_ambiguous_or_numbered_titles_are_not_fallbacks(overrides):
    assert query(**overrides) == []


def test_bare_footer_stat_does_not_become_printing_evidence():
    assert query(numbers=[OcrHit('30',.99,'collector')]) == ['a','b']


@pytest.mark.parametrize('verified', [False, True])
def test_title_only_outside_shortlist_requires_geometry_and_never_confirms(tmp_path, verified):
    import io
    from types import SimpleNamespace
    import numpy as np
    from PIL import Image
    from app.config import Settings
    from app.db import connect, init_catalog, init_results
    from app.recognition.ocr import OcrResult
    from app.recognition.pipeline import recognize_bytes
    from app.recognition.local_match import LocalArtworkMatch

    catalog, results = connect(tmp_path/'catalog.sqlite'), connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    ids = [f'distractor-{i}' for i in range(21)] + ['target']
    for cid in ids:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES(?,?,?,?,?,?,?)',
            (cid,cid,'Example VSTAR' if cid == 'target' else 'Distractor',cid,cid,'001','en'))
    catalog.commit()
    snapshot = SimpleNamespace(card_ids=np.array(ids),embeddings=np.array(
        [[.94,np.sqrt(1-.94**2)]]*21 + [[.91,np.sqrt(1-.91**2)]],dtype=np.float32))
    ocr = OcrResult(name_text='Example VSTAR',hits=[OcrHit('Example VSTAR',.99,'name')])
    def verify(image, references):
        return [LocalArtworkMatch('target',100,100,.3,'as_supplied','conventional_window')] if verified else []
    runtime = SimpleNamespace(require=lambda:(snapshot,
        SimpleNamespace(embed=lambda *a:np.array([1.,0.],dtype=np.float32)),
        SimpleNamespace(read=lambda image:ocr)),card_languages=np.array(['en']*len(ids)),
        printing_index=None,artwork_verifier=SimpleNamespace(verify=verify),
        metadata_index=MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'),indexed_ids=set(ids)),
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
        threshold_config=lambda:{})
    payload = io.BytesIO()
    Image.fromarray(np.random.default_rng(13).integers(0,255,(825,600,3),dtype=np.uint8)).save(payload,format='JPEG')
    try:
        response = recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            enable_matched=True,store_captures=False),runtime=runtime,catalog=catalog,
            results=results,session_id='test',skip_detect=True,language='en')
        assert response.status.value != 'matched'
        if verified:
            assert response.best_match.card_id == 'target'
        else:
            assert response.best_match is None
    finally:
        catalog.close()
        results.close()
