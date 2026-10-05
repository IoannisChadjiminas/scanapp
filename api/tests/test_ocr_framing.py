from PIL import Image
import pytest

from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.ocr_framing import complete_frame_probe_allowed, complete_frame_identity_supported


@pytest.mark.parametrize('profile,angle,size,allowed', [
    ('window_0.70',0,(1000,1400),True), ('window_0.85',0,(1000,1400),True),
    ('loose_1',0,(1000,1400),True), ('loose_1',180,(1000,1400),False),
    ('loose_0',0,(1400,1000),False), ('loose_0',0,(600,1000),False),
    ('primary',0,(1000,1400),False), ('slab_interior',0,(1000,1400),False),
    ('window_0.70',180,(1000,1400),False), ('window_0.70',0,(1400,1000),False),
    ('window_0.70',0,(600,1000),False), ('window_0.70',0,(250,350),False),
])
def test_original_probe_is_bounded(profile, angle, size, allowed):
    assert complete_frame_probe_allowed(Image.new('RGB',size),profile=profile,orientation=angle) is allowed


def evidence(name='Pikachu', number='35/108', name_confidence=.99, number_confidence=.99, region='collector'):
    return OcrResult(name_text=name, hits=[OcrHit(name,name_confidence,'name'),
        OcrHit(number,number_confidence,region)])


def test_complete_frame_requires_literal_name_fraction_and_visual_identity():
    assert complete_frame_identity_supported(evidence(),['Pikachu'])
    assert not complete_frame_identity_supported(evidence(),['Raichu'])
    assert not complete_frame_identity_supported(evidence(name_confidence=.89),['Pikachu'])
    assert not complete_frame_identity_supported(evidence(number_confidence=.84),['Pikachu'])
    assert not complete_frame_identity_supported(evidence(number='35'),['Pikachu'])
    assert not complete_frame_identity_supported(evidence(region='holder_collector'),['Pikachu'])
    assert not complete_frame_identity_supported(OcrResult(failed=True),['Pikachu'])


def test_wrong_number_remains_observed_for_normal_printing_contradiction_checks():
    result = evidence(number='35/109')
    assert complete_frame_identity_supported(result,['Pikachu'])
    assert result.hits[1].text == '35/109'


def test_title_only_probe_requires_strong_literal_visual_agreement():
    from app.recognition.ocr_framing import complete_frame_title_supported
    observed = evidence(number='35', number_confidence=.6)
    assert complete_frame_title_supported(observed, ['Pikachu'])
    assert not complete_frame_identity_supported(observed, ['Pikachu'])
    assert not complete_frame_title_supported(observed, ['Raichu'])
    assert not complete_frame_title_supported(evidence(name_confidence=.94), ['Pikachu'])
    assert not complete_frame_title_supported(OcrResult(failed=True), ['Pikachu'])


def test_staged_footer_requires_agreeing_catalogue_backed_original_fields():
    from app.recognition.ocr_framing import original_footer_supports_skip
    selected = OcrResult(name_text='Pikachu', hits=[OcrHit('Pikachu', .99, 'name')])
    row = dict(name='Pikachu', collector_number='35', printed_collector_number='35/108', language='en')
    assert original_footer_supports_skip(selected, evidence(), [row])
    for original in (evidence(name='Raichu'), evidence(number='35/109'),
                     evidence(number='35'), evidence(number_confidence=.94),
                     evidence(name_confidence=.94), evidence(region='holder_collector'),
                     OcrResult(failed=True)):
        assert not original_footer_supports_skip(selected, original, [row])
    selected.hits.append(OcrHit('35', .6, 'collector'))
    assert not original_footer_supports_skip(selected, evidence(), [row])


@pytest.mark.parametrize('token,expected',[('35/108X','35/108'),('077/146C','077/146'),
    ('TG05/TG30★','TG05/TG30'),('35/109X','35/109'),('035/108X','035/108')])
def test_high_confidence_adjacent_footer_glyph_never_repairs_digits(token,expected):
    from app.recognition.ocr_framing import normalize_complete_frame_footer
    original=evidence(number=token)
    original.lines=[token]
    normalized,changes=normalize_complete_frame_footer(original)
    assert normalized.hits[1].text==expected and normalized.hits[1].confidence==.99
    assert original.hits[1].text==token and normalized.lines==[token]
    assert changes==[dict(observed=token,fraction=expected,confidence=.99)]


@pytest.mark.parametrize('token,confidence,region',[('35/108X',.84,'collector'),
    ('35/108X',None,'collector'),('35/108X',.99,'holder_collector'),
    ('35/108X2',.99,'collector'),('35/10BX',.99,'collector'),('35X',.99,'collector'),
    ('damage 35/108X',.99,'collector'),('SM35',.99,'collector')])
def test_glyph_normalization_rejects_uncertain_incomplete_or_unlocated_text(token,confidence,region):
    from app.recognition.ocr_framing import normalize_complete_frame_footer
    original=evidence(number=token,number_confidence=confidence,region=region)
    normalized,changes=normalize_complete_frame_footer(original)
    assert normalized==original and changes==[]


def test_read_pass_telemetry_records_failed_regions_without_text(monkeypatch):
    from app.recognition.ocr import CardOcr
    def fail(self, image):
        raise ValueError('private OCR error')
    monkeypatch.setattr(CardOcr,'_run',fail)
    result = CardOcr.read(CardOcr.__new__(CardOcr),Image.new('RGB',(600,825)))
    assert result.failed and len(result.passes) == 1
    assert result.passes[0]['region'] == 'name'
    assert result.passes[0]['reason'] == 'initial'
    assert 'text' not in result.passes[0] and 'error' not in result.passes[0]


@pytest.mark.parametrize('accepted',[True,False,'title_only'])
def test_pipeline_uses_complete_identity_or_reuses_failed_probe_without_duplicate_read(tmp_path,monkeypatch,accepted):
    import io
    import json
    from types import SimpleNamespace
    import numpy as np
    from app.config import Settings
    from app.db import connect,init_catalog,init_results
    from app.recognition.pipeline import recognize_bytes
    import app.recognition.pipeline as pipeline
    catalog=connect(tmp_path/'catalog.sqlite'); results=connect(tmp_path/'results.sqlite')
    init_catalog(catalog);init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    catalog.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES ('card','card','Pikachu','set','Set','35','35/108','en')")
    catalog.commit()
    calls=[]
    def read(image):
        calls.append(image.size)
        if image.width==600:
            return (evidence(number='35',number_confidence=.6) if accepted=='title_only' else
                    evidence() if accepted else OcrResult(failed=True))
        return evidence(number='35',number_confidence=.6)
    image=Image.fromarray(np.random.default_rng(9).integers(0,255,(840,600,3),dtype=np.uint8))
    monkeypatch.setattr(pipeline,'detect_and_rectify',lambda im:(im,False))
    monkeypatch.setattr(pipeline,'card_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'loose_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'portrait_window_candidates',lambda *a:[])
    monkeypatch.setattr(pipeline,'slab_interior_candidate',lambda *a:None)
    def oriented(im,*a,**kwargs):
        kwargs['selection_metadata'].update(profile='window_0.70')
        crop=im.resize((420,588));kwargs['query_vectors'][id(crop)]=np.array([1,0],dtype=np.float32)
        return crop,np.array([0]),np.array([.9]),{'orientation_degrees':0}
    monkeypatch.setattr(pipeline,'retrieve_oriented',oriented)
    snapshot=SimpleNamespace(card_ids=np.array(['card']),embeddings=np.array([[1,0]],dtype=np.float32))
    runtime=SimpleNamespace(require=lambda:(snapshot,SimpleNamespace(embed=lambda *a:np.array([1,0])),SimpleNamespace(read=read)),
        artwork_verifier=None,printing_index=None,versions=lambda:dict(ocr='test',ranking='test',model_revision='test',catalogue='test'),
        threshold_config=lambda:{})
    buffer=io.BytesIO();image.save(buffer,format='JPEG')
    try:
        response=recognize_bytes(buffer.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            store_captures=False,use_grading=False,ocr_complete_frame_first=True),runtime=runtime,
            catalog=catalog,results=results,session_id='test')
        assert calls==([(600,840)] if accepted else [(600,840),(420,588)])
        saved=json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?',(response.id,)).fetchone()[0])
        assert saved['frame_selection']['ocr_complete_frame_used'] is bool(accepted)
        if accepted == 'title_only':
            assert saved['frame_selection']['ocr_complete_frame_title_only']
            assert response.status.value == 'printing_ambiguous'
            assert response.confidence.printing == 'ambiguous'
            assert response.confidence.requires_confirmation
    finally:
        catalog.close();results.close()
