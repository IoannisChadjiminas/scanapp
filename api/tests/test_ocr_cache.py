from types import SimpleNamespace
from PIL import Image
from app.recognition.ocr import OcrResult, OcrHit
from app.recognition.ocr_cache import RequestOcrCache


def test_identical_pixels_are_reused_but_mutable_evidence_is_not_shared():
    calls=[]
    def read(image):
        calls.append(image)
        return OcrResult(name_text='Toxel',lines=['Toxel'],hits=[OcrHit('078',.99,'collector')],
                         passes=[dict(ms=4.)])
    engine=SimpleNamespace(read=read)
    cache=RequestOcrCache()
    frame=Image.new('RGB',(20,30),'red')
    first,hit=cache.read(engine,frame)
    assert not hit
    first.lines.append('supplement'); first.hits.clear(); first.passes[0]['ms']=999
    second,hit=cache.read(engine,frame.copy())
    assert hit and second.lines==['Toxel'] and second.hits[0].text=='078'
    assert second.passes[0]['ms']==4 and len(calls)==1
    second.lines.clear()
    assert cache.read(engine,frame)[0].lines==['Toxel']


def test_different_pixels_geometry_rotation_and_requests_do_not_share_reads():
    calls=[]
    engine=SimpleNamespace(read=lambda image:calls.append(image) or OcrResult())
    frame=Image.new('RGB',(20,30),'red')
    cache=RequestOcrCache()
    for image in (frame, frame.crop((0,0,20,29)), frame.rotate(90,expand=True),
                  Image.new('RGB',(20,30),'blue'), frame.convert('L')):
        assert not cache.read(engine,image)[1]
    assert not RequestOcrCache().read(engine,frame)[1]
    assert len(calls)==6 and cache.hits==0


def test_boundary_retry_shares_request_cache_and_saves_only_selected_pass(monkeypatch):
    import numpy as np
    from app.recognition import pipeline
    from app.schemas import ScanStatus
    frame=Image.new('RGB',(300,420),'red');calls=[];saved=[]
    engine=SimpleNamespace(read=lambda image:calls.append(image) or OcrResult(
        name_text='Toxel',hits=[OcrHit('Toxel',.99,'name')]))
    def evaluate(data,**kwargs):
        observed,hit=kwargs['_ocr_cache'].read(engine,frame.copy())
        retry='_frame_override' in kwargs
        response=SimpleNamespace(status=ScanStatus.uncertain if retry else ScanStatus.retake,
                                 id='retry' if retry else 'first',versions={})
        return pipeline._ScanEvaluation(response=response,timings={'total_ms':1.},input_image=frame,
            save=lambda:saved.append(response.id),lead={'card_id':'candidate','name':'Toxel','language':'en'},
            ocr=observed,numbers=[],languages=('en',),name_confidence=.99,quality_retake=False,evidence={})
    monkeypatch.setattr(pipeline,'_recognize_bytes_once',evaluate)
    monkeypatch.setattr(pipeline,'line_frame_candidates',lambda *a,**k:[frame])
    runtime=SimpleNamespace(card_languages=None,require=lambda:(
        SimpleNamespace(embeddings=np.array([[1.,0.]],dtype=np.float32)),
        SimpleNamespace(embed=lambda *a:np.array([.9,np.sqrt(1-.9**2)],dtype=np.float32)),None))
    settings=SimpleNamespace(preprocess_config='pad',threshold_min_visual=.78,
        threshold_min_visual_ocr=.7,threshold_min_gap=.04,use_grading=False,use_ocr=True)
    response=pipeline.recognize_bytes(b'fake',settings=settings,runtime=runtime,
                                      catalog=None,results=None,session_id='test')
    assert len(calls)==1 and saved==['retry']
    assert response.timings_ms['ocr_cache_hits']==1 and response.timings_ms['ocr_unique_reads']==1
