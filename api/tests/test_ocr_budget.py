from types import SimpleNamespace
from PIL import Image
import pytest

from app.recognition.ocr import CardOcr, OcrHit, OcrResult
from app.recognition.ocr_budget import footer_retry_required
from app.recognition.ocr_cache import RequestOcrCache


def evidence(name='Toxel', confidence=.99, number=None):
    return OcrResult(name_text=name, hits=[OcrHit(name, confidence, 'name')]
        + ([OcrHit(number, .6, 'collector')] if number else []))


def gate(ocr=None, *, visual=.88, runner=.70, art=.88, name='Toxel', size=(600,840)):
    return footer_retry_required(ocr or evidence(),
        [dict(card_id='first',name=name,visual_score=visual),
         dict(card_id='second',name='Other card',visual_score=runner)],
        [SimpleNamespace(card_id='first',score=art)],image_size=size)


def test_strong_two_stream_identity_can_skip_optional_retries_only():
    assert gate() is False
    assert gate(evidence('ピカチュウ'),name='ピカチュウ') is False


@pytest.mark.parametrize('kwargs', [dict(visual=.84),dict(runner=.81),dict(art=.79),
    dict(name='Pikachu'),dict(size=(800,600)),dict(size=(300,600)),
    dict(ocr=evidence(confidence=.94)),dict(ocr=evidence('ex')),
    dict(ocr=evidence(number='078')),dict(ocr=evidence(number='35/108')),
    dict(ocr=evidence(number='SM35')),dict(ocr=OcrResult(failed=True))])
def test_weak_ambiguous_partial_or_observed_identifiers_keep_retry(kwargs):
    assert gate(**kwargs) is True


def test_missing_artwork_or_runner_keeps_established_path():
    assert footer_retry_required(evidence(),[],[],image_size=(600,840))
    assert footer_retry_required(evidence(),[dict(card_id='first',name='Toxel',visual_score=.95)],
        [],image_size=(600,840))


@pytest.mark.parametrize('policy', [lambda ocr: False,lambda ocr: True])
def test_policy_preserves_first_observations_and_never_changes_confidence(monkeypatch, policy):
    calls=[]
    def read(self, image):
        calls.append(image.size)
        return (['Toxel'],[.99]) if len(calls)==1 else (['retreat'],[.97])
    monkeypatch.setattr(CardOcr,'_run',read)
    result=CardOcr.__new__(CardOcr).read(Image.new('RGB',(600,840)),collector_retry_policy=policy)
    skipped=not policy(None)
    assert len(calls)==(2 if skipped else 4)
    assert result.collector_retry_skipped is skipped
    assert result.collector_retry_used is not skipped
    assert not result.failed and not result.collector_retry_contributed
    assert [h.text for h in result.hits]==['Toxel','retreat']
    assert result.hits[0].confidence==.99 and len(result.passes)==len(calls)


def test_policy_failure_runs_the_existing_footer_retries(monkeypatch):
    calls=[]
    def read(self, image):
        calls.append(image.size)
        return (['Toxel'],[.99]) if len(calls)==1 else ([],[])
    def policy(ocr):
        raise RuntimeError('policy unavailable')
    monkeypatch.setattr(CardOcr,'_run',read)
    result=CardOcr.__new__(CardOcr).read(Image.new('RGB',(600,840)),collector_retry_policy=policy)
    assert len(calls)==4 and not result.collector_retry_skipped and result.collector_retry_used


def test_pruned_cache_entry_never_supplies_a_complete_evidence_request():
    calls=[]
    def read(image,**kwargs):
        calls.append(kwargs)
        return OcrResult(collector_retry_skipped=bool(kwargs))
    cache=RequestOcrCache(); reader=SimpleNamespace(read=read)
    image=Image.new('RGB',(20,30));policy=lambda observed:False
    assert cache.read(reader,image,collector_retry_policy=policy)[0].collector_retry_skipped
    assert cache.read(reader,image,collector_retry_policy=policy)[1]
    complete,hit=cache.read(reader,image)
    assert not hit and not complete.collector_retry_skipped and len(calls)==2
    assert not cache.read(reader,image,collector_retry_policy=policy)[0].collector_retry_skipped
    assert len(calls)==2


def test_pipeline_skipping_footer_never_automatically_certifies_printing(tmp_path,monkeypatch):
    import io
    import json
    import numpy as np
    import app.recognition.pipeline as pipeline
    from app.config import Settings
    from app.db import connect,init_catalog,init_results
    catalog=connect(tmp_path/'catalog.sqlite');results=connect(tmp_path/'results.sqlite')
    init_catalog(catalog);init_results(results)
    results.execute("INSERT INTO sessions VALUES('test','test','test')")
    for cid,name,number in [('first','Toxel','078'),('second','Other card','079')]:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES(?,?,?,?,?,?,?)',
                        (cid,cid,name,'promo','Promos',number,'en'))
    catalog.commit()
    calls=[];reader=CardOcr.__new__(CardOcr)
    def read(image):
        calls.append(image.size)
        return (['Toxel'],[.99]) if len(calls)==1 else (['retreat'],[.99])
    reader._run=read
    def oriented(image,*args,**kwargs):
        kwargs['query_vectors'][id(image)]=np.array([1.,0.],dtype=np.float32)
        kwargs['selection_metadata'].update(profile='primary')
        return image,np.array([0,1]),np.array([.88,.70]),{'orientation_degrees':0.}
    monkeypatch.setattr(pipeline,'retrieve_oriented',oriented)
    snapshot=SimpleNamespace(card_ids=np.array(['first','second']),
        embeddings=np.array([[1.,0.],[0.,1.]],dtype=np.float32))
    artwork=SimpleNamespace(search=lambda *a,**k:([
        SimpleNamespace(card_id='first',score=.88,reference_profile='conventional_window',query_profile='as_supplied')],{}))
    runtime=SimpleNamespace(require=lambda:(snapshot,None,reader),artwork_index=artwork,
        artwork_verifier=None,printing_index=None,
        versions=lambda:dict(ocr='test',ranking='test',model_revision='test',catalogue='test'),
        threshold_config=lambda:{})
    image=Image.fromarray(np.random.default_rng(9).integers(0,255,(840,600,3),dtype=np.uint8))
    buffer=io.BytesIO();image.save(buffer,format='JPEG')
    try:
        response=pipeline.recognize_bytes(buffer.getvalue(),settings=Settings(_env_file=None,
            data_dir=tmp_path,store_captures=False,use_grading=False,enable_matched=True,
            ocr_adaptive_footer=True),runtime=runtime,catalog=catalog,results=results,
            session_id='test',skip_detect=True)
        assert len(calls)==2 and response.ocr.collector_retry_skipped
        assert response.status.value=='uncertain' and response.best_match.card_id=='first'
        assert response.confidence.printing=='unconfirmed' and response.confidence.requires_confirmation
        assert response.confidence.probability is None and response.ocr.collector_text=='retreat'
        saved=json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?',(response.id,)).fetchone()[0])
        assert saved['collector_retry_skipped'] and len(saved['passes'])==2
    finally:
        catalog.close();results.close()


@pytest.mark.parametrize('number,skipped', [('35/108', True), ('35/109', False)])
def test_staged_original_uses_each_frame_once_and_keeps_printing_manual(tmp_path, monkeypatch, number, skipped):
    import io
    import json
    import numpy as np
    import app.recognition.pipeline as pipeline
    from app.config import Settings
    from app.db import connect, init_catalog, init_results
    catalog = connect(tmp_path/'catalog.sqlite'); results = connect(tmp_path/'results.sqlite')
    init_catalog(catalog); init_results(results)
    results.execute("INSERT INTO sessions VALUES('test','test','test')")
    catalog.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES('card','card','Pikachu','set','Set','35','35/108','en')")
    catalog.commit()
    reader = CardOcr.__new__(CardOcr); calls = []
    def read(patch):
        calls.append(patch.size)
        if patch.width in (600, 500):
            if patch.height in (184, 154): return ['Pikachu'], [.99]
            return ([number], [.99]) if patch.width == 600 else (['retreat'], [.99])
        return ['35/108'], [.99]
    reader._run = read
    monkeypatch.setattr(pipeline, 'detect_and_rectify', lambda image: (image, False))
    for name in ('card_frame_candidates', 'loose_frame_candidates', 'portrait_window_candidates'):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: [])
    monkeypatch.setattr(pipeline, 'slab_interior_candidate', lambda *a: None)
    monkeypatch.setattr(pipeline, 'line_frame_candidates', lambda *a, **k: [])
    def oriented(image, *args, **kwargs):
        frame = image.resize((500,700)); kwargs['query_vectors'][id(frame)] = np.array([1.,0.],dtype=np.float32)
        kwargs['selection_metadata'].update(profile='loose_0')
        return frame,np.array([0]),np.array([.9]),{'orientation_degrees':0.}
    monkeypatch.setattr(pipeline, 'retrieve_oriented', oriented)
    snapshot = SimpleNamespace(card_ids=np.array(['card']), embeddings=np.array([[1.,0.]],dtype=np.float32))
    runtime = SimpleNamespace(require=lambda: (snapshot, None, reader), artwork_verifier=None,
        printing_index=None, versions=lambda:dict(ocr='test',ranking='test',model_revision='test',catalogue='test'),
        threshold_config=lambda:{})
    image = Image.fromarray(np.random.default_rng(8).integers(0,255,(840,600,3),dtype=np.uint8))
    data = io.BytesIO(); image.save(data, format='JPEG')
    try:
        response = pipeline.recognize_bytes(data.getvalue(), settings=Settings(_env_file=None,
            data_dir=tmp_path, use_grading=False, store_captures=False, ocr_staged_original=True),
            runtime=runtime, catalog=catalog, results=results, session_id='test')
        assert response.ocr.collector_retry_skipped is skipped
        assert len(calls) == (4 if skipped else 6)
        assert calls.count((600,184)) == 1 and calls.count((600,152)) == 1
        saved = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0])
        assert saved['frame_selection']['ocr_staged_footer_supported'] is skipped
        assert response.status.value != 'matched'
        if skipped:
            assert response.best_match.card_id == 'card'
            # Literal original metadata is supported, not certified; manual
            # confirmation remains required after omitting optional retries.
            assert response.confidence.printing == 'metadata_supported'
            assert response.confidence.requires_confirmation
    finally:
        catalog.close(); results.close()
