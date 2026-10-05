from types import SimpleNamespace
import io
import json

import numpy as np
import pytest
from PIL import Image

from app.recognition import pipeline
from app.recognition.ocr import OcrHit, OcrResult
from app.schemas import ScanStatus
from app.config import Settings
from app.db import connect, init_catalog, init_results


def evaluation(status, saves, label, *, quality=False, name='Charizard ex', confidence=.99):
    return pipeline._ScanEvaluation(
        SimpleNamespace(status=ScanStatus(status),timings_ms={}),
        {'total_ms':100.,'ocr_ms':40.},Image.new('RGB',(500,700)),
        lambda:saves.append(label),{'card_id':label,'name':name,'language':'en'},
        OcrResult(name_text='Charizard ex'),[],('en',),confidence,quality,{})


def run(monkeypatch, rows, *, score=.90, **kwargs):
    calls=[]
    def once(*args, **options):
        calls.append(options)
        return rows[len(calls)-1]
    monkeypatch.setattr(pipeline,'_recognize_bytes_once',once)
    monkeypatch.setattr(pipeline,'line_frame_candidates',lambda *a,**k:[Image.new('RGB',(300,420))]*2)
    runtime=SimpleNamespace(require=lambda:(
        SimpleNamespace(embeddings=np.array([[1.,0.]],dtype=np.float32)),
        SimpleNamespace(embed=lambda *a:np.array([score,np.sqrt(1-score**2)],dtype=np.float32)),None),
        card_languages=np.array(['en']))
    settings=SimpleNamespace(preprocess_config='pad',threshold_min_visual=.78,threshold_min_visual_ocr=.70,threshold_min_gap=.04)
    response=pipeline.recognize_bytes(b'fake',settings=settings,runtime=runtime,
        catalog=None,results=None,session_id='test',**kwargs)
    return response,calls


@pytest.mark.parametrize('status',['matched','uncertain','printing_ambiguous','no_match'])
def test_useful_first_pass_is_never_replaced(monkeypatch,status):
    saves=[]
    first=evaluation(status,saves,'first')
    result,calls=run(monkeypatch,[first])
    assert result is first.response and len(calls)==1 and saves==['first']


@pytest.mark.parametrize('options',[{'skip_detect':True},{'crop_x':0.},{'crop_h':1.}])
def test_explicit_crop_does_not_trigger_recovery(monkeypatch,options):
    saves=[]
    result,calls=run(monkeypatch,[evaluation('retake',saves,'first')],**options)
    assert len(calls)==1 and saves==['first']


def test_quality_retake_does_not_trigger_recovery(monkeypatch):
    saves=[]
    _,calls=run(monkeypatch,[evaluation('retake',saves,'first',quality=True)])
    assert len(calls)==1 and saves==['first']


def test_successful_recovery_saves_one_scan_and_records_both_passes(monkeypatch):
    saves=[]
    first=evaluation('retake',saves,'first')
    retry=evaluation('uncertain',saves,'retry')
    result,calls=run(monkeypatch,[first,retry])
    assert result is retry.response and saves==['retry'] and len(calls)==2
    assert calls[1]['_frame_override'][0]=='line_0'
    assert result.timings_ms['boundary_retry_selected']==1
    assert result.timings_ms['first_pass_ms']==100
    assert retry.evidence['boundary_recovery']['first_top_id']=='first'


@pytest.mark.parametrize('status',['retake','no_match','matched'])
def test_failed_or_automatic_retry_is_discarded(monkeypatch,status):
    saves=[]
    first=evaluation('retake',saves,'first')
    retry=evaluation(status,saves,'retry')
    result,calls=run(monkeypatch,[first,retry])
    assert result is first.response and saves==['first'] and len(calls)==2
    assert result.timings_ms['boundary_retry_ms']==100
    assert first.evidence['boundary_recovery']['attempted'] is True


def test_second_pass_cannot_discard_confident_first_pass_name(monkeypatch):
    saves=[]
    first=evaluation('retake',saves,'first')
    retry=evaluation('uncertain',saves,'retry',name='Pikachu')
    result,_=run(monkeypatch,[first,retry])
    assert result is first.response and saves==['first']


def test_second_pass_cannot_discard_confident_fraction(monkeypatch):
    saves=[]
    first=evaluation('retake',saves,'first')
    first.numbers=[OcrHit('199/165',.99,'collector')]
    retry=evaluation('uncertain',saves,'retry')
    retry.lead.update(collector_number='200',printed_collector_number='200/165')
    result,_=run(monkeypatch,[first,retry])
    assert result is first.response and saves==['first']


def test_weak_line_query_does_not_trigger_second_ocr(monkeypatch):
    saves=[]
    _,calls=run(monkeypatch,[evaluation('retake',saves,'first')],score=.69)
    assert len(calls)==1 and saves==['first']


@pytest.mark.parametrize('card_name,ocr_name,display_name',[
    ('Charizard ex','Charizard ex','Charizard ex'),
    ("Professor's Research (Professor Magnolia)","Professor's Pesoarch","Professor's Research (Professor Magnolia)"),
    ("Professor's Research","Professor's Pesoarch","Professor's Research (Professor Magnolia)")])
def test_real_pipeline_persists_only_selected_pass_and_capture(tmp_path,monkeypatch,card_name,ocr_name,display_name):
    image=Image.fromarray(np.random.default_rng(44).integers(0,255,(800,600,3),dtype=np.uint8))
    frame=image.resize((300,420))
    monkeypatch.setattr(pipeline,'detect_and_rectify',lambda im:(im,False))
    monkeypatch.setattr(pipeline,'card_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'loose_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'portrait_window_candidates',lambda *a:[])
    monkeypatch.setattr(pipeline,'line_frame_candidates',lambda *a,**k:[frame])
    original_enrich=pipeline.apply_variants_to_candidate
    def enrich(*args,**kwargs):
        original_enrich(*args,**kwargs)
        args[1]['name']=display_name
    monkeypatch.setattr(pipeline,'apply_variants_to_candidate',enrich)
    captures=[]
    monkeypatch.setattr(pipeline,'save_scan_capture',lambda **record:captures.append(record))
    catalog=connect(tmp_path/'catalog.sqlite')
    results=connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES(?,?,?,?,?,?,?,?)',
        ('card','card',card_name,'set','Set','199','199/165','en'))
    catalog.commit()
    def embed(im,*args):
        score=.95 if im.size==(300,420) else .73
        return np.array([score,np.sqrt(1-score**2)],dtype=np.float32)
    def read(im):
        confidence=.99 if im.size==(300,420) else .84
        return OcrResult(name_text=ocr_name,collector_text='199/165',
            hits=[OcrHit(ocr_name,.99,'name'),OcrHit('199/165',confidence,'collector')])
    runtime=SimpleNamespace(require=lambda:(
        SimpleNamespace(card_ids=np.array(['card']),embeddings=np.array([[1,0]],dtype=np.float32)),
        SimpleNamespace(embed=embed),SimpleNamespace(read=read)),
        card_languages=np.array(['en']),printing_index=None,
        artwork_verifier=SimpleNamespace(verify=lambda *a:[]),
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
        threshold_config=lambda:{})
    payload=io.BytesIO()
    image.save(payload,format='JPEG')
    try:
        response=pipeline.recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,
            data_dir=tmp_path,store_captures=True,enable_matched=True),runtime=runtime,
            catalog=catalog,results=results,session_id='test',language='en')
        assert response.status==ScanStatus.uncertain
        rows=results.execute('SELECT id,ocr_json,timings_json FROM scans').fetchall()
        assert len(rows)==1 and rows[0]['id']==response.id and len(captures)==1
        assert captures[0]['scan_id']==response.id
        evidence=json.loads(rows[0]['ocr_json'])
        assert evidence['frame_selection']['profile']=='line_0'
        assert evidence['boundary_recovery']['first_status']=='retake'
        assert evidence['boundary_recovery']['selected'] is True
        assert json.loads(rows[0]['timings_json'])['total_ms']==pytest.approx(response.timings_ms['total_ms'],abs=.01)
    finally:
        catalog.close()
        results.close()


def test_reliable_name_guides_crop_selection_not_final_confirmation(monkeypatch):
    saves=[]
    first=evaluation('retake',saves,'first')
    retry=evaluation('uncertain',saves,'retry')
    frames=[Image.new('RGB',(300,420)),Image.new('RGB',(310,430))]
    calls=[]
    def once(*args,**kwargs):
        calls.append(kwargs)
        return first if len(calls)==1 else retry
    monkeypatch.setattr(pipeline,'_recognize_bytes_once',once)
    monkeypatch.setattr(pipeline,'line_frame_candidates',lambda *a,**k:frames)
    runtime=SimpleNamespace(card_positions={'first':0},card_languages=np.array(['en','en']),
        require=lambda:(SimpleNamespace(embeddings=np.array([[.8,.6],[1.,0.]],dtype=np.float32)),
            SimpleNamespace(embed=lambda frame,*a:np.array([1.,0.] if frame is frames[0] else [.8,.6],dtype=np.float32)),None))
    result=pipeline.recognize_bytes(b'fake',settings=SimpleNamespace(preprocess_config='pad',
        threshold_min_visual=.78,threshold_min_visual_ocr=.70,threshold_min_gap=.04),runtime=runtime,
        catalog=None,results=None,session_id='test')
    assert calls[1]['_frame_override'][1] is frames[1]
    assert retry.evidence['boundary_recovery']['selection_identity']=='first'
    assert result.status==ScanStatus.uncertain and saves==['retry']


def test_proposal_order_does_not_hide_small_crop_improvement(monkeypatch):
    saves=[]
    first=evaluation('retake',saves,'first')
    retry=evaluation('uncertain',saves,'retry')
    frames=[Image.new('RGB',(300,420)),Image.new('RGB',(310,430))]
    calls=[]
    def once(*args,**kwargs):
        calls.append(kwargs)
        return first if len(calls)==1 else retry
    monkeypatch.setattr(pipeline,'_recognize_bytes_once',once)
    monkeypatch.setattr(pipeline,'line_frame_candidates',lambda *a,**k:frames)
    runtime=SimpleNamespace(card_languages=np.array(['en']),
        require=lambda:(SimpleNamespace(embeddings=np.array([[1.,0.]],dtype=np.float32)),
            SimpleNamespace(embed=lambda frame,*a:np.array([.73,np.sqrt(1-.73**2)]
                if frame is frames[0] else [.75,np.sqrt(1-.75**2)],dtype=np.float32)),None))
    result=pipeline.recognize_bytes(b'fake',settings=SimpleNamespace(preprocess_config='pad',
        threshold_min_visual=.78,threshold_min_visual_ocr=.70,threshold_min_gap=.04),runtime=runtime,
        catalog=None,results=None,session_id='test')
    assert calls[1]['_frame_override'][1] is frames[1]
    assert retry.evidence['boundary_recovery']['proposal_profile']=='line_1'
    assert result.status==ScanStatus.uncertain and saves==['retry']
