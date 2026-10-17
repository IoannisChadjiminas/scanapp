import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.identity import layout_identity_agrees
from app.recognition.layout_match import CardLayoutVerifier, LayoutMatch
from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import CardOcr, OcrHit, OcrResult
from app.recognition.pipeline import recognize_bytes
from app.recognition.rank import extract_collector_candidates


def identity(**kwargs):
    return dict(name='Jumpluff', collector_number='7', printed_collector_number='7/111',
                language='en', **kwargs)


@pytest.mark.parametrize('changes', [dict(name_confidence=.94), dict(ocr_name='Jumpluff ex'),
    dict(languages=()), dict(languages=('ja',)),
    dict(numbers=[OcrHit('7', .99, 'collector')]),
    dict(numbers=[OcrHit('7/111', .89, 'collector')]),
    dict(numbers=[OcrHit('7/111', .99, 'holder_collector')]),
    dict(numbers=[OcrHit('7/111', .99, 'collector'), OcrHit('7/112', .99, 'collector')])])
def test_layout_gate_abstains_on_incomplete_weak_or_conflicting_identity(changes):
    args=dict(ocr_name='Jumpluff', name_confidence=.99,
              numbers=[OcrHit('7/111', .99, 'collector')], languages=('en',))
    assert layout_identity_agrees(identity(), **args)
    args.update(changes)
    assert not layout_identity_agrees(identity(), **args)


def test_layout_requires_known_denominator_and_preserves_prior_conflicts():
    args=dict(ocr_name='Jumpluff', name_confidence=.99,
              numbers=[OcrHit('7/111', .99, 'collector')], languages=('en',))
    card=identity(); card['printed_collector_number']=''
    assert not layout_identity_agrees(card, **args)
    card['set_total']=112
    assert not layout_identity_agrees(card, **args)
    card['set_total']=111
    assert layout_identity_agrees(card, **args)
    card['collector_conflict']=True
    assert not layout_identity_agrees(card, **args)


@pytest.mark.parametrize('text', ['-30', '−30', '–30', '- 30'])
def test_resistance_reductions_are_not_collector_numbers(text):
    hits=extract_collector_candidates([], hits=[OcrHit(text,.99,'collector'),
        OcrHit('7/111',.99,'collector'), OcrHit('SM-215',.99,'collector')])
    assert {h.text for h in hits} == {'7/111', '215'}


@pytest.mark.parametrize('extra', [('7/111', .93), ('7/111', .89), ('71111', .99), ('7/111★', .99)])
def test_compact_footer_is_one_literal_read(monkeypatch, extra):
    calls=[]
    def read(self, patch):
        calls.append(patch.size)
        return [extra[0], '-30'], [extra[1], .99]
    monkeypatch.setattr(CardOcr,'_run',read)
    reader=CardOcr.__new__(CardOcr)
    hits,record=reader.read_compact_footer(Image.new('RGB',(1121,1600)))
    assert calls==[(900,116)] and record['reason']=='compact_footer'
    assert [(h.text,h.region) for h in hits]==([('7/111','collector')] if extra==('7/111',.93) else [])


def test_ordinary_read_never_runs_compact_footer(monkeypatch):
    # The compact strip is recovery-only; ordinary evidence and status rules
    # (including footer_retry_contributed) must see exactly the prior passes.
    observations=iter([(['Jumpluff'],[.99]),(['-30'],[.99]),([],[]),([],[])])
    monkeypatch.setattr(CardOcr,'_run',lambda self,patch:next(observations))
    reader=CardOcr.__new__(CardOcr)
    result=reader.read(Image.new('RGB',(1121,1600)))
    assert not result.failed and not result.collector_retry_contributed
    assert [p['reason'] for p in result.passes]==['initial','initial','footer_half','footer_half']


def test_weaker_retry_fraction_can_receive_a_literal_stronger_read():
    hits=[OcrHit('Jumpluff',.99,'name'),OcrHit('-30',.99,'collector'),
          OcrHit('7/111',.87689,'collector'),OcrHit('7/111',.92775,'collector')]
    numbers=extract_collector_candidates([],hits=hits)
    assert [(h.text,h.confidence) for h in numbers]==[('7/111',.92775)]


def test_duplicate_observations_do_not_pool_confidence_or_erase_conflicts():
    hits=[OcrHit('7/111',.86,'collector'),OcrHit('7/111',.87,'collector'),
          OcrHit('7/112',.99,'collector'),OcrHit('7/111',1.,'unknown')]
    numbers=extract_collector_candidates([],hits=hits)
    assert {(h.text,h.confidence,h.region) for h in numbers}=={
        ('7/111',.87,'collector'),('7/112',.99,'collector')}


def textured_card(seed=51):
    # Repeated title/rules layout plus spatially distributed landmarks.
    image=Image.fromarray(np.random.default_rng(seed).integers(0,256,(825,600,3),dtype=np.uint8))
    draw=ImageDraw.Draw(image)
    for y in (30,70,120,650,700,760):
        draw.rectangle((20,y,580,y+25),fill='white')
        draw.text((40,y+5),f'Observed field {y}: JUMPLUFF 7/111',fill='black')
    return image


def test_layout_geometry_needs_both_ends_and_rejects_unrelated_pixels(tmp_path):
    root=tmp_path/'reference-images'; root.mkdir()
    source=root/'card.png'; ref=textured_card(); ref.save(source)
    verifier=CardLayoutVerifier(tmp_path)
    photo=ref.copy(); photo.paste(Image.new('RGB',(540,350),'white'),(30,170))
    matches=verifier.verify(photo,[('card',str(source))])
    assert len(matches)==1 and matches[0].header_inliers>=8 and matches[0].footer_inliers>=8
    unrelated=Image.fromarray(np.random.default_rng(92).integers(0,256,(825,600,3),dtype=np.uint8))
    assert verifier.verify(unrelated,[('card',str(source))])==[]
    clipped=Image.new('RGB',ref.size);clipped.paste(ref.crop((0,0,600,180)),(0,0))
    assert verifier.verify(clipped,[('card',str(source))])==[]
    assert verifier.verify(photo,[('card',str(source))]*5)==[]


def test_layout_reference_must_stay_inside_root_and_match_validated_source(tmp_path):
    root=tmp_path/'reference-images'; root.mkdir()
    outside=tmp_path/'outside.png'; image=textured_card(); image.save(outside)
    verifier=CardLayoutVerifier(tmp_path)
    assert verifier.verify(image,[('card',str(outside))])==[]
    inside=root/'card.png'; image.save(inside)
    verifier.feature_store=SimpleNamespace(manifest={'records':{'card':{
        'available':True,'image_path':str(inside),'source_sha256':'0'*64}}})
    assert verifier.verify(image,[('card',str(inside))])==[]


@pytest.mark.parametrize('enabled,verified,number,ambiguous,compact', [
    (True,True,'7/111',False,None),(False,True,'7/111',False,None),
    (True,False,'7/111',False,None),(True,True,'7/112',False,None),(True,True,'7/111',True,None),
    # A weak first-pass fraction needs the abstained-only compact read.
    (True,True,'7/111@.87689',False,'7/111'),(True,True,'7/111@.87689',False,None),
    (True,True,'7/111@.87689',False,'7/112')])
def test_pipeline_layout_recovery_is_review_only_and_preserves_abstention(
        tmp_path, monkeypatch, enabled, verified, number, ambiguous, compact):
    import app.recognition.pipeline as pipeline
    catalog=connect(tmp_path/'catalog.sqlite');results=connect(tmp_path/'results.sqlite')
    init_catalog(catalog);init_results(results)
    results.execute("INSERT INTO sessions VALUES('test','test','test')")
    rows=[('wrong','Other','4','4/111','wrong'),('correct','Jumpluff','7','7/111','neo1')]
    if ambiguous:
        rows.append(('twin','Jumpluff','7','7/111','other-set'))
    for cid,name,num,printed,set_id in rows:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language,image_path) VALUES(?,?,?,?,?,?,?,?,?)',
            (cid,cid,name,set_id,set_id,num,printed,'en',str(tmp_path/cid)))
    catalog.commit()
    ids=[r[0] for r in rows]
    snapshot=SimpleNamespace(card_ids=np.array(ids),embeddings=np.array(
        [[.65,np.sqrt(1-.65**2)]]+[[.55,np.sqrt(1-.55**2)]]*(len(ids)-1),dtype=np.float32))
    number,_,first_confidence=number.partition('@')
    ocr=OcrResult(name_text='Jumpluff',collector_text=number,
        hits=[OcrHit('Jumpluff',.99,'name'),OcrHit(number,float(first_confidence or .99),'collector')])
    calls=[];compact_calls=[]
    def read_compact_footer(image):
        compact_calls.append(image.size)
        return ([OcrHit(compact,.92775,'collector')] if compact else []),dict(
            region='collector',reason='compact_footer',width=900,height=116,ms=1.)
    def verify(image,refs):
        calls.append(refs)
        return [LayoutMatch('correct',100,20,20,.6)] if verified else []
    runtime=SimpleNamespace(require=lambda:(snapshot,SimpleNamespace(embed=lambda *a:np.array([1,0],dtype=np.float32)),
        SimpleNamespace(read=lambda image:ocr,read_compact_footer=read_compact_footer)),card_languages=np.array(['en']*len(ids)),
        artwork_verifier=SimpleNamespace(verify=lambda *a:[]),printing_index=None,layout_verifier=SimpleNamespace(verify=verify),
        metadata_index=MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'),indexed_ids=set(ids)),
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),threshold_config=lambda:{})
    def oriented(image,*a,**kwargs):
        kwargs['query_vectors'][id(image)]=np.array([1,0],dtype=np.float32)
        return image,np.arange(len(ids)),snapshot.embeddings[:,0],{'orientation_degrees':0.}
    monkeypatch.setattr(pipeline,'retrieve_oriented',oriented)
    monkeypatch.setattr(pipeline,'detect_and_rectify',lambda image:(image,False))
    monkeypatch.setattr(pipeline,'card_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'loose_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'line_frame_candidates',lambda *a,**k:[])
    payload=io.BytesIO();textured_card().save(payload,format='JPEG')
    try:
        response=recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            store_captures=False,use_grading=False,structured_layout_recovery=enabled),
            runtime=runtime,catalog=catalog,results=results,session_id='test')
        weak=bool(first_confidence)
        recovered=(enabled and verified and number=='7/111' and not ambiguous
                   and (not weak or compact=='7/111'))
        assert response.status.value==('uncertain' if recovered else 'retake')
        if recovered:
            assert response.best_match.card_id=='correct'
            assert response.confidence.requires_confirmation and response.confidence.probability is None
            assert response.confidence.visual_similarity==pytest.approx(.55)
        else:
            assert response.best_match is None
        if not enabled or number!='7/111' or ambiguous or (weak and compact!='7/111'):
            assert calls==[]
        # The compact read runs only for a weak/missing fraction in recovery.
        assert compact_calls==([(600,825)] if enabled and weak else [])
        saved=json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?',(response.id,)).fetchone()[0])
        assert saved['layout_review_supported'] is recovered
        assert saved['local_artwork_matches']==[]
        assert [h['text'] for h in saved['layout_footer_hits']]==([compact] if weak and compact else [])
        assert 'footer_retry_contributed' not in response.confidence.reasons
    finally:
        catalog.close();results.close()
