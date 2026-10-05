"""Generic layout/script/statistics handling, never benchmark-card exceptions."""
import pytest
from PIL import Image
from app.recognition.ocr import CardOcr, OcrHit, pick_name_line
from app.recognition.language import confident_language_texts, resolve_search_languages
from app.recognition.rank import extract_collector_candidates


def test_isolated_footer_script_symbols_do_not_override_english_layout():
    hits = [OcrHit('Example VMAX',.99,'name'),
            OcrHit('Evolves from Example V',.99,'name'),
            OcrHit('weakness',.99,'collector'),OcrHit('resistance',.99,'collector'),
            OcrHit('本本',.99,'collector')]
    assert resolve_search_languages('auto',confident_language_texts(hits)).detected == 'en'


@pytest.mark.parametrize('text,expected', [('ポケモン','ja'),('寶可夢','zh-tw'),
    ('宝可梦','zh-cn'),('포켓몬','ko'),('皮卡丘','zh'),('イーブイ','ja')])
def test_real_localized_language_not_overridden_by_copyright(text, expected):
    assert resolve_search_languages('auto',[text,'Nintendo GAME FREAK']).detected == expected


@pytest.mark.parametrize('badge', ['Basic Pokémon','Basic','Stage 1','Stage 2','TRAINER','たね','トレーナーズ','2進化'])
def test_layout_badge_anchors_title_after_background(badge):
    assert pick_name_line(['BACKGROUND SHOP',badge,'Example', '90 HP']) == 'Example'


def test_unanchored_title_and_slab_name_can_propose_identity():
    assert pick_name_line(['Example', '90 HP']) == 'Example'
    assert pick_name_line(['FA/EXAMPLE','GEM MT','SET LABEL']) == 'FA/EXAMPLE'
    assert pick_name_line(['asic Pokémon','Example','50 HP']) == 'Example'


@pytest.mark.parametrize('line', ['LV. 23 N250','LV. 23 #250',
                                  'Pokemon text LV 23 N250','LY. 23 s250',
                                  'At night it detects danger and hides s250'])
def test_level_pokedex_line_not_collector(line):
    assert extract_collector_candidates([], [OcrHit(line,.99,'collector')]) == []
    assert [h.text for h in extract_collector_candidates([], [OcrHit(line+' 42/100',.99,'collector')])] == ['42/100']


def test_small_regions_upscaled_without_fabricating_observations():
    ocr = object.__new__(CardOcr)
    sizes = []
    responses = iter([(['Example'],[.99]),(['42/100'],[.99])])
    def run(image):
        sizes.append(image.size)
        return next(responses)
    ocr._run = run
    result = ocr.read(Image.new('RGB',(200,280)))
    assert result.name_text == 'Example' and result.collector_text == '42/100'
    assert all(width == 600 for width,_ in sizes)
    assert result.hits == [OcrHit('Example',.99,'name'),OcrHit('42/100',.99,'collector')]


@pytest.mark.parametrize('prefix', ['MF','WE','F','G'])
def test_decorated_gallery_fraction_retains_gallery_namespace(prefix):
    hits=extract_collector_candidates([], [OcrHit(prefix+'GG24/GG70',.99,'collector')])
    assert [h.text for h in hits] == ['GG24/70']


def test_unknown_gallery_prefix_without_fraction_not_rewritten():
    assert [h.text for h in extract_collector_candidates([], [OcrHit('WEGG24',.99,'collector')])] == ['WEGG24']


def test_full_ocr_only_promotes_observed_title_and_footer_boxes():
    from types import SimpleNamespace
    import numpy as np
    ocr=object.__new__(CardOcr)
    ocr._run=lambda image:([],[])
    ocr.engine=lambda image:SimpleNamespace(txts=['Example','Rules','42/100',''],
        scores=[.99,.99,.99,.99],boxes=np.array([
            [[10,20],[100,20],[100,40],[10,40]],
            [[10,300],[100,300],[100,350],[10,350]],
            [[10,600],[100,600],[100,630],[10,630]],
            [[10,20],[100,20],[100,40],[10,40]]]))
    result=ocr.read(Image.new('RGB',(500,700)))
    assert result.name_text=='Example' and result.collector_text=='42/100'
    assert [h.region for h in result.hits]==['name','full','collector']


def test_full_ocr_without_boxes_keeps_identity_unknown():
    from types import SimpleNamespace
    ocr=object.__new__(CardOcr)
    ocr._run=lambda image:([],[])
    ocr.engine=lambda image:SimpleNamespace(txts=['Example','42/100'],scores=[.99,.99])
    result=ocr.read(Image.new('RGB',(500,700)))
    assert result.name_text is None and result.collector_text is None
    assert all(h.region=='full' for h in result.hits)


@pytest.mark.parametrize('number,expected,verified', [(None,'a',True),('002/100','b',True),
    ('holder','a',True),('holder',None,False)])
def test_verified_artwork_counts_do_not_choose_printing(tmp_path,number,expected,verified):
    import io
    from types import SimpleNamespace
    import numpy as np
    from app.config import Settings
    from app.db import connect,init_catalog,init_results
    from app.recognition.local_match import LocalArtworkMatch
    from app.recognition.ocr import OcrResult
    from app.recognition.pipeline import recognize_bytes
    catalog,results=connect(tmp_path/'catalog.sqlite'),connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    for cid,n in [('a','001'),('b','002')]:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES(?,?,?,?,?,?,?,?)',
            (cid,cid,'Example',cid,cid,n,n+'/100','en'))
    catalog.commit()
    ocr=OcrResult(hits=[OcrHit(number,.99,'collector')] if number else [])
    if number=='holder':
        ocr=OcrResult(name_text='Example',hits=[OcrHit('Example',.99,'name'),OcrHit('001',.99,'holder_collector')])
    snapshot=SimpleNamespace(card_ids=np.array(['a','b']),embeddings=np.array([
        [.77,np.sqrt(1-.77**2)],[.76,np.sqrt(1-.76**2)]],dtype=np.float32))
    runtime=SimpleNamespace(require=lambda:(snapshot,
        SimpleNamespace(embed=lambda *a:np.array([1.,0.],dtype=np.float32)),
        SimpleNamespace(read=lambda image:ocr)),card_languages=np.array(['en','en']),
        printing_index=None,artwork_verifier=SimpleNamespace(verify=lambda *a:[
            LocalArtworkMatch('b',100,100,.3),LocalArtworkMatch('a',20,20,.3)] if verified else []),
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
        threshold_config=lambda:{})
    payload=io.BytesIO()
    Image.fromarray(np.random.default_rng(42).integers(0,255,(825,600,3),dtype=np.uint8)).save(payload,format='JPEG')
    try:
        response=recognize_bytes(payload.getvalue(),settings=Settings(_env_file=None,data_dir=tmp_path,
            enable_matched=True,store_captures=False),runtime=runtime,catalog=catalog,results=results,
            session_id='test',skip_detect=True,language='en')
        assert (response.best_match.card_id if response.best_match else None)==expected
        assert response.status.value!='matched'
    finally:
        catalog.close()
        results.close()


@pytest.mark.parametrize('raw_title,raw_conf,expected,missing_crop_name', [('Example',.99,'uncertain',False),
    ('Unrelated',.99,'retake',False),('Example',.60,'retake',False),
    ('Unrelated',.99,'uncertain',True)])
def test_crop_title_can_only_gain_agreeing_original_evidence(tmp_path,raw_title,raw_conf,expected,missing_crop_name):
    import io
    from types import SimpleNamespace
    import numpy as np
    from app.config import Settings
    from app.db import connect,init_catalog,init_results
    from app.recognition.ocr import OcrResult
    from app.recognition.pipeline import _recognize_bytes_once
    catalog,results=connect(tmp_path/'catalog.sqlite'),connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,printed_collector_number,language) VALUES(?,?,?,?,?,?,?,?)',
        ('card','card','Example','set','Set','001','001/100','en'))
    catalog.commit()
    original=Image.fromarray(np.random.default_rng(23).integers(0,255,(825,600,3),dtype=np.uint8))
    frame=original.resize((300,420))
    reads=[]
    def read(image):
        reads.append(image.size)
        name,conf=(raw_title,raw_conf) if image.size==original.size else ('Exmple',.60)
        hits=[OcrHit(name,conf,'name'),OcrHit('001/100',.99,'collector')]
        if missing_crop_name:
            if image.size==original.size:
                hits.extend([OcrHit('#001',.99,'name'),OcrHit('GEM MT',.99,'name')])
            else:
                name=None
                hits=[OcrHit('001/100',.99,'collector')]
        return OcrResult(name_text=name,hits=hits)
    from app.recognition.local_match import LocalArtworkMatch
    runtime=SimpleNamespace(require=lambda:(SimpleNamespace(card_ids=np.array(['card']),
        embeddings=np.array([[.73,np.sqrt(1-.73**2)]],dtype=np.float32)),
        SimpleNamespace(embed=lambda *a:np.array([1.,0.],dtype=np.float32)),
        SimpleNamespace(read=read)),card_languages=np.array(['en']),printing_index=None,
        artwork_verifier=SimpleNamespace(verify=lambda *a:[LocalArtworkMatch('card',30,30,.3)] if missing_crop_name else []),
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
        threshold_config=lambda:{})
    payload=io.BytesIO()
    original.save(payload,format='JPEG')
    try:
        evaluation=_recognize_bytes_once(payload.getvalue(),settings=Settings(_env_file=None,
            data_dir=tmp_path,enable_matched=True,store_captures=False),runtime=runtime,
            catalog=catalog,results=results,session_id='test',language='en',
            _frame_override=('line_test',frame))
        assert evaluation.response.status.value==expected
        if missing_crop_name:
            assert reads==[(300,420)] and evaluation.ocr.name_text is None
        else:
            assert OcrHit('Exmple',.60,'name') in evaluation.ocr.hits
        assert OcrHit('001/100',.99,'collector') in evaluation.ocr.hits
    finally:
        catalog.close()
        results.close()


def test_artwork_alignment_projects_complete_card_not_reference_pixels(tmp_path):
    import numpy as np
    from app.recognition.local_match import LocalArtworkVerifier
    root=tmp_path/'reference-images'
    root.mkdir()
    reference=Image.new('RGB',(500,700),'lightgray')
    patch=Image.fromarray(np.random.default_rng(10).integers(0,255,(190,380,3),dtype=np.uint8))
    reference.paste(patch,(60,133))
    path=root/'card.png'
    reference.save(path)
    photo=Image.new('RGB',(1000,1400),'darkgray')
    # Footer is deliberately different: a projected crop must keep the input.
    photographed=reference.copy()
    photographed.paste('red',(0,600,500,700))
    photo.paste(photographed,(250,320))
    verifier=LocalArtworkVerifier(tmp_path)
    aligned=verifier.propose_frame(photo,('card',str(path)))
    assert aligned is not None
    assert abs(aligned.width-500)<10 and abs(aligned.height-700)<10
    assert aligned.getpixel((aligned.width//2,round(aligned.height*.93)))[0]>200
    assert verifier.propose_frame(Image.new('RGB',(1000,1400),'white'),('card',str(path))) is None
    assert verifier.propose_frame(photo,('card','/not/a/reference')) is None


def test_artwork_alignment_does_not_invent_missing_corners(tmp_path):
    import numpy as np
    from app.recognition.local_match import LocalArtworkVerifier
    root=tmp_path/'reference-images'
    root.mkdir()
    reference=Image.new('RGB',(500,700),'lightgray')
    reference.paste(Image.fromarray(np.random.default_rng(10).integers(0,255,(190,380,3),dtype=np.uint8)),(60,133))
    path=root/'card.png'
    reference.save(path)
    assert LocalArtworkVerifier(tmp_path).propose_frame(reference.crop((0,0,500,500)),('card',str(path))) is None


def test_holder_hint_requires_confident_grading_label_and_number():
    hits=[OcrHit('GEM MT',.99,'name'),OcrHit('#43',.99,'name')]
    assert extract_collector_candidates([],hits)==[OcrHit('43',.99,'holder_collector')]
    assert extract_collector_candidates([],hits[:1])==[]
    assert extract_collector_candidates([],hits[1:])==[]
    assert extract_collector_candidates([],[hits[0],OcrHit('#43',.50,'name')])==[]
    footer=OcrHit('43',.95,'collector')
    assert extract_collector_candidates([],hits+[footer])==[footer]


def test_holder_number_cannot_veto_printed_fraction_or_certify_printing():
    from app.recognition.rank import rerank,artwork_evidence_compatible
    from app.recognition.identity import structured_identity_agrees
    a=dict(card_id='a',name='Example',collector_number='001',printed_collector_number='001/100',
           visual_score=.9,language='en')
    b=dict(a,card_id='b',collector_number='002',printed_collector_number='002/100',visual_score=.91)
    hint=[OcrHit('001',.99,'holder_collector')]
    args=dict(detected_languages=('en',),name_confidence=.99,require_confident_ocr=True)
    assert rerank([a,b],'Example',hint,False,**args)[0]['card_id']=='a'
    assert rerank([a,b],'Unrelated',hint,False,**args)[0]['card_id']=='b'
    printed=[*hint,OcrHit('002/100',.99,'collector')]
    assert rerank([a,b],'Example',printed,False,**args)[0]['card_id']=='b'
    assert artwork_evidence_compatible(b,ocr_name='Example',name_confidence=.99,numbers=hint,languages=('en',))
    assert not structured_identity_agrees(a,ocr_name='Example',name_confidence=.99,numbers=hint,languages=('en',))
