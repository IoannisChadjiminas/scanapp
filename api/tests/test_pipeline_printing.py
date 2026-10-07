import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.pipeline import recognize_bytes
from app.recognition.printing import ReferencePrintingIndex
from app.recognition.artwork import ArtworkHit
from app.recognition.local_match import LocalArtworkMatch
from app.recognition.metadata import MetadataCandidateIndex
import pytest


@pytest.mark.parametrize('wrong_fraction', [False, True])
def test_metadata_retrieval_outside_visual_top_k_is_review_only(tmp_path, wrong_fraction):
    catalog, results = connect(tmp_path/'catalog.sqlite'), connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    try:
        ids = [f'wrong-{i:02}' for i in range(21)] + ['correct']
        for cid in ids:
            catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES(?,?,?,?,?,?,?,?)',
                (cid,cid,'Lugia V' if cid == 'correct' else 'Distractor',cid,cid,
                 '186' if cid == 'correct' else '1','186/195' if cid == 'correct' else '1/195','en'))
        catalog.commit()
        snapshot = SimpleNamespace(card_ids=np.array(ids), embeddings=np.array(
            [[.94,np.sqrt(1-.94**2)]]*21+[[.91,np.sqrt(1-.91**2)]],dtype=np.float32))
        fraction = '186/198' if wrong_fraction else '186/195'
        ocr = OcrResult(name_text='Lugia V',collector_text=fraction,
            hits=[OcrHit('Lugia V',.99,'name'),OcrHit(fraction,.99,'collector')])
        runtime = SimpleNamespace(require=lambda:(snapshot,
            SimpleNamespace(embed=lambda *args:np.array([1,0],dtype=np.float32)),
            SimpleNamespace(read=lambda image:ocr)),card_languages=np.array(['en']*len(ids)),
            artwork_verifier=None,printing_index=None,
            metadata_index=MetadataCandidateIndex(catalog.execute('SELECT * FROM cards'),indexed_ids=set(ids)),
            versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
            threshold_config=lambda:{})
        image=Image.fromarray(np.random.default_rng(8).integers(0,255,(825,600,3),dtype=np.uint8))
        payload=io.BytesIO()
        image.save(payload,format='JPEG')
        response=recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            store_captures=False),runtime=runtime,catalog=catalog,results=results,
            session_id='test',skip_detect=True,language='en')
        row=results.execute('SELECT visual_ranking_json,ocr_json FROM scans WHERE id=?',(response.id,)).fetchone()
        visual,evidence=json.loads(row[0]),json.loads(row[1])
        if wrong_fraction:
            assert evidence['metadata_candidate_ids'] == []
            assert 'correct' not in {r['card_id'] for r in visual}
        else:
            assert evidence['metadata_candidate_ids'] == ['correct']
            assert response.status == 'uncertain'
            assert response.suggestions[0].card_id == 'correct'
            correct=next(r for r in visual if r['card_id']=='correct')
            assert correct['retrieved_via'] == ['ocr_metadata']
            assert correct['visual_score'] == pytest.approx(.91)
    finally:
        catalog.close()
        results.close()


@pytest.mark.parametrize('name,number,dual,expected,score,retry',[
    ('Charizard ex','199/165',False,'uncertain',.73,False),
    ('Pikachu','199/165',False,'retake',.73,False),('Charizard ex','200/165',False,'retake',.73,False),
    ('Charizard ex','199',False,'retake',.73,False), ('Charizard ex','',True,'printing_ambiguous',.73,False),
    ('Pikachu','',True,'retake',.73,False), ('Charizard ex','200/165',True,'retake',.73,False),
    ('Charizard ex','199/165',False,'uncertain',.90,True)])
def test_two_field_ocr_review_rescue_never_automatically_confirms(tmp_path,monkeypatch,name,number,dual,expected,score,retry):
    monkeypatch.setattr('app.recognition.pipeline.detect_and_rectify',lambda im:(im,False))
    monkeypatch.setattr('app.recognition.pipeline.card_frame_candidates',lambda *a,**k:[])
    monkeypatch.setattr('app.recognition.pipeline.loose_frame_candidates',lambda *a,**k:[])
    image=Image.fromarray(np.random.default_rng(11).integers(0,255,(800,600,3),dtype=np.uint8))
    catalog=connect(tmp_path/'catalog.sqlite')
    results=connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES(?,?,?,?,?,?,?)',
        ('card','card','Charizard ex','set','Set','199','en'))
    catalog.commit()
    snapshot=SimpleNamespace(card_ids=np.array(['card']),embeddings=np.array([[score,np.sqrt(1-score**2)]],dtype=np.float32))
    ocr=OcrResult(name_text=name,collector_text=number,lines=[name,number],
                  hits=[OcrHit(name,.99,'name'),OcrHit(number,.99,'collector')],
                  collector_retry_used=retry, collector_retry_contributed=retry)
    runtime=SimpleNamespace(require=lambda:(snapshot,
        SimpleNamespace(embed=lambda *a:np.array([1,0],dtype=np.float32)),
        SimpleNamespace(read=lambda im:ocr)),card_languages=np.array(['en']),
        printing_index=None,artwork_verifier=SimpleNamespace(verify=lambda *a:[]),
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
        threshold_config=lambda:{})
    payload=io.BytesIO()
    if dual:
        runtime.artwork_index = SimpleNamespace(search=lambda *a,**k:
            ([ArtworkHit('card',.72,'conventional_window','as_supplied')],{}))
    image.save(payload,format='JPEG')
    try:
        response=recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            enable_matched=True,store_captures=False),runtime=runtime,catalog=catalog,
            results=results,session_id='test',language='en')
        assert response.status.value == expected
        if expected == 'retake':
            assert response.best_match is None
            assert response.alternatives == []
        else:
            assert response.best_match.card_id == response.suggestions[0].card_id
            assert response.match_state == 'likely'
        assert response.status.value != 'matched'
        if expected=='uncertain':
            assert response.suggestions[0].card_id=='card'
            if score < .78:
                assert 'framing was not verified' in response.message
        elif expected == 'printing_ambiguous':
            assert response.suggestions[0].card_id == 'card'
            assert response.printing_review.reason == 'likely_identity_printing_unverified'
            assert response.confidence.identity == 'likely'
            assert response.confidence.probability is None
            saved = json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?',
                (response.id,)).fetchone()[0])
            assert saved['confidence'] == response.confidence.model_dump(mode='json')
            assert saved['match_presentation']['best_match'] == response.best_match.model_dump(mode='json')
            assert 'Likely card' in response.message
        else:
            assert not response.suggestions
    finally:
        catalog.close()
        results.close()


def test_pipeline_surfaces_and_persists_expanded_printing_choices(tmp_path):
    root = tmp_path / "reference-images"
    root.mkdir()
    image = Image.fromarray(np.random.default_rng(7).integers(0,255,(35,25,3),dtype=np.uint8)).resize((500,700), Image.Resampling.NEAREST)
    catalog = connect(tmp_path / "catalog.sqlite")
    results = connect(tmp_path / "results.sqlite")
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    try:
        for i, set_name, num in (("base", "Base Set", "58"), ("classic", "Classic", "014")):
            path = root / f"{i}.png"
            image.save(path)
            catalog.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,image_path,has_image) VALUES (?,?,?,?,?,?,?,?,1)",
                (i,i,"Pikachu",i,set_name,num,"en",str(path)))
        catalog.commit()
        snapshot = SimpleNamespace(card_ids=np.array(["base"]), embeddings=np.array([[1,0]],dtype=np.float32))
        runtime = SimpleNamespace(
            require=lambda: (snapshot, SimpleNamespace(embed=lambda *args, **kwargs: np.array([1,0], dtype=np.float32)),
                             SimpleNamespace(read=lambda image: OcrResult())),
            card_languages=np.array(["en"]), printing_index=ReferencePrintingIndex(tmp_path),
            artwork_verifier=None,
            versions=lambda: dict(model_revision="test", catalogue="test", ocr="test", ranking="test"),
            threshold_config=lambda: {},
        )
        data = io.BytesIO()
        image.save(data, format="JPEG")
        response = recognize_bytes(data.getvalue(), settings=Settings(data_dir=tmp_path,store_captures=False),
            runtime=runtime,catalog=catalog,results=results,session_id="test",skip_detect=True,language="en")
        assert response.status == "printing_ambiguous"
        assert response.best_match.card_id == response.suggestions[0].card_id
        assert {response.best_match.card_id, *(c.card_id for c in response.alternatives)} == {'base','classic'}
        assert {p.card_id for p in response.printing_review.plausible_printings} == {"base","classic"}
        row = results.execute("SELECT status,ocr_json FROM scans WHERE id=?",(response.id,)).fetchone()
        assert row["status"] == "printing_ambiguous"
        assert json.loads(row["ocr_json"])["printing_review"]["candidate_group_id"] == response.printing_review.candidate_group_id
    finally:
        catalog.close()
        results.close()


@pytest.mark.parametrize('geometry_verified,ocr_result,skip_detect', [
    (False,None,True), (True,None,True), (False,None,False),
    (True,OcrResult(name_text='Copyright Nintendo Creatures GAME FREAK',
                   lines=['Copyright Nintendo Creatures GAME FREAK'],
                   hits=[OcrHit('Copyright Nintendo Creatures GAME FREAK',.99,'collector')]),True)])
def test_artwork_retrieval_rescues_outside_full_top_k_without_automatic_printing(tmp_path, monkeypatch, geometry_verified, ocr_result, skip_detect):
    size = (300,600,3) if skip_detect else (825,600,3)
    image = Image.fromarray(np.random.default_rng(8).integers(0,255,size,dtype=np.uint8))
    monkeypatch.setattr('app.recognition.pipeline.detect_and_rectify',lambda im:(im,False))
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    try:
        ids = [f'wrong-{i:02}' for i in range(21)] + ['correct']
        for card_id in ids:
            catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language,image_path,has_image) VALUES(?,?,?,?,?,?,?,?,1)',
                            (card_id,card_id,'Fuecoco' if card_id == 'correct' else 'Distractor',
                             card_id,card_id,'036' if card_id == 'correct' else '1','en','/unused'))
        catalog.commit()
        snapshot = SimpleNamespace(card_ids=np.array(ids), embeddings=np.array(
            [[.5,np.sqrt(.75)]]*21+[[.4,np.sqrt(.84)]],dtype=np.float32))
        references = []
        def verify(image, candidates):
            references.extend(candidates[:8])
            assert 'correct' in {card_id for card_id,path in candidates[:8]}
            return [LocalArtworkMatch('correct',100,100,.7)] if geometry_verified else []
        runtime = SimpleNamespace(require=lambda: (snapshot,
            SimpleNamespace(embed=lambda *args: np.array([1,0],dtype=np.float32)),
            SimpleNamespace(read=lambda image:ocr_result) if ocr_result else None),
            card_languages=np.array(['en']*len(ids)), printing_index=None,
            artwork_verifier=SimpleNamespace(verify=verify),
            artwork_index=SimpleNamespace(search=lambda *args,**kwargs: (
                [ArtworkHit('correct',.999,'conventional_window','as_supplied')],{})),
            versions=lambda: dict(model_revision='test',catalogue='test',ocr='off',ranking='test'),
            threshold_config=lambda: {})
        data = io.BytesIO()
        image.save(data,format='JPEG')
        response = recognize_bytes(data.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            use_ocr=bool(ocr_result),store_captures=False),runtime=runtime,catalog=catalog,results=results,
            session_id='test',skip_detect=skip_detect,language='en')
        assert response.status != 'matched'
        row = results.execute('SELECT combined_ranking_json,ocr_json FROM scans WHERE id=?',(response.id,)).fetchone()
        ranking,ocr = json.loads(row[0]),json.loads(row[1])
        correct = next(r for r in ranking if r['card_id'] == 'correct')
        assert correct['retrieved_via'] == ['artwork']
        assert correct['visual_score'] == pytest.approx(.4)
        assert correct['artwork_score'] == pytest.approx(.999)
        assert ocr['artwork_retrieval'][0]['card_id'] == 'correct'
        if geometry_verified:
            assert response.suggestions[0].card_id == 'correct'
            assert response.status in {'uncertain','printing_ambiguous'}
        else:
            assert response.status == 'retake' and not response.suggestions
    finally:
        catalog.close()
        results.close()
