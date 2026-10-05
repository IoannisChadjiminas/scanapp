"""Generic regressions without photo-specific IDs or hardcoded predictions."""
import pytest
from PIL import Image
from app.recognition.grading import LabelLine, parse_label
from app.recognition.label_vision import text_label_panel
from app.recognition.ocr import OcrHit, OcrResult, pick_name_line, inverted_card_layout
from app.recognition.rank import extract_collector_candidates


@pytest.mark.parametrize('text,number',[
    ('SM9038/095RR','038/095'),('5M9038/095RR','038/095'),
    ('SM12a083/173RR','083/173'),('SM120083/173RR','0083/173'),
    ('SM7a055/060SR','055/060')])
def test_glued_japanese_series_not_collector_namespace(text,number):
    assert [h.text for h in extract_collector_candidates([],hits=[OcrHit(text,.99,'collector')])] == [number]


@pytest.mark.parametrize('text', ['SM123','SM123/999','XY123/999','ABC123/456RR'])
def test_real_promo_and_unknown_prefix_preserved(text):
    hits=extract_collector_candidates([],hits=[OcrHit(text,.99,'collector')])
    assert hits and hits[0].text.startswith(text.split('/')[0])


@pytest.mark.parametrize('header',['TAG TEAM','MEGA EVOLUTION BLACK STAR','CERTIFIED GUARANTY COMPANY','UNIVERSAL GRADE'])
def test_holder_or_layout_header_not_card_title(header):
    assert pick_name_line([header,'Example V'])=='Example V'


def test_internal_title_punctuation_preserved_but_sentences_skipped():
    assert pick_name_line(['Mr. Mime'])=='Mr. Mime'
    assert pick_name_line(['It hides in the forest.','Example'])=='Example'


def label(cert_box):
    return [LabelLine('TAG',.99),LabelLine('2023 POKEMON',.99),
            LabelLine('MINT',.99,(.70,.20,.90,.30)),
            LabelLine('9',.99,(.74,.32,.88,.50)),
            LabelLine('M123456',.99,(.10,.55,.25,.75)),
            LabelLine('M1234567',.99,cert_box)]


def test_different_reads_of_same_cert_field_do_not_erase_independent_grade():
    result=parse_label(label((.10,.55,.26,.76)))
    assert result.grade==9 and result.certification_number is None
    assert 'certification_number_unreadable_or_ambiguous' in result.warnings


@pytest.mark.parametrize('box',[None,(.60,.55,.80,.76)])
def test_unlocalized_or_separate_certificates_remain_hard_conflict(box):
    result=parse_label(label(box))
    assert result.grade is None and result.certification_number is None
    assert 'certification_number_ambiguous' in result.warnings


def test_two_independent_label_markers_can_propose_pixels_not_issuer():
    lines=[LabelLine('2024 POKEMON',.99,(.10,.30,.50,.40)),
           LabelLine('MINT',.99,(.70,.30,.90,.40))]
    assert text_label_panel(Image.new('RGB',(600,900)),lines) is not None
    assert parse_label(lines).company is None and parse_label(lines).grade is None


def test_seller_watermark_and_card_name_cannot_propose_label():
    lines=[LabelLine('TAG',.99,(.10,.30,.30,.40)),
           LabelLine('Example',.99,(.40,.30,.70,.40))]
    assert text_label_panel(Image.new('RGB',(600,900)),lines) is None


def test_inverted_layout_requires_independent_evidence_at_both_ends():
    hits=[OcrHit('42/100',.99,'name'),OcrHit('Evolves from Example',.99,'collector')]
    assert inverted_card_layout(OcrResult(hits=hits))
    assert not inverted_card_layout(OcrResult(hits=hits[:1]))
    assert not inverted_card_layout(OcrResult(hits=hits[1:]))
    assert not inverted_card_layout(OcrResult(hits=[hits[0],OcrHit('Stage 1',.50,'collector')]))
    assert not inverted_card_layout(OcrResult(hits=[OcrHit('42/100',.99,'collector'),OcrHit('Stage 1',.99,'name')]))


def test_adjacent_observed_promo_namespace_not_incidental_bare_numbers():
    hits=[OcrHit('SVP EN',.99,'collector'),OcrHit('052',.98,'collector')]
    assert 'SVP052' in [h.text for h in extract_collector_candidates([],hits)]
    for weak in ([OcrHit('SVPEN',.50,'collector'),hits[1]],
                 [OcrHit('SVPEN',.99,'name'),hits[1]],
                 [hits[0],OcrHit('52',.99,'collector')],
                 [hits[0],OcrHit('retreat',.99,'collector'),hits[1]]):
        assert 'SVP052' not in [h.text for h in extract_collector_candidates([],weak)]


def test_namespaced_promo_cannot_match_bare_digit_in_other_set():
    from app.recognition.rank import accepted_collector_numbers, number_matches_identifiers
    hits=[OcrHit('SVP052',.99,'collector')]
    assert number_matches_identifiers(hits,accepted_collector_numbers(dict(set_id='svp',collector_number='052'))) is True
    assert number_matches_identifiers(hits,accepted_collector_numbers(dict(set_id='normal',collector_number='052'))) is False


def test_fuzzy_title_is_only_complete_bounded_geometry_proposal():
    from app.recognition.metadata import MetadataCandidateIndex
    rows=[dict(id=str(i),name='Example',collector_number=str(i),language='en') for i in range(3)]
    index=MetadataCandidateIndex(rows,indexed_ids={'0','1','2'})
    options=dict(ocr_name='Examp1e',name_confidence=.99,numbers=[],languages=('en',))
    assert index.title_candidates(**options)==['0','1','2']
    assert index.title_candidates(**options,limit=2)==[]
    assert index.title_candidates(**dict(options,name_confidence=.50))==[]
    assert index.title_candidates(**dict(options,numbers=[OcrHit('1/100',.99,'collector')]))==[]


def test_weak_unknown_language_title_channel_is_bounded_and_not_identity_proof():
    from app.recognition.metadata import MetadataCandidateIndex
    rows=[dict(id=str(i),name='Example',collector_number=str(i),language='en') for i in range(3)]
    index=MetadataCandidateIndex(rows,indexed_ids={'0','1','2'})
    options=dict(ocr_name='Examp1e',name_confidence=.70,numbers=[],languages=())
    assert index.geometry_candidates(**options)==['0','1','2']
    assert index.title_candidates(**options)==[]
    assert index.geometry_candidates(**options,limit=2)==[]
    assert index.geometry_candidates(**dict(options,name_confidence=.50))==[]
    assert index.geometry_candidates(**dict(options,numbers=[OcrHit('1/100',.99,'collector')]))==[]


def test_exact_geometry_title_family_is_not_inflated_with_similar_names():
    from app.recognition.metadata import MetadataCandidateIndex
    rows=[dict(id=str(i),name='Example',collector_number=str(i),language='en') for i in range(3)]
    rows += [dict(id='other'+str(i),name='Example Plus',collector_number=str(i),language='en') for i in range(6)]
    index=MetadataCandidateIndex(rows,indexed_ids={r['id'] for r in rows})
    options=dict(ocr_name='Example',name_confidence=.99,numbers=[],languages=('en',))
    assert index.geometry_candidates(**options,limit=3)==['0','1','2']
    assert index.geometry_candidates(**options,limit=2)==[]


@pytest.mark.parametrize('first_matches',[False,True])
def test_dense_keypoints_are_recovery_only_not_a_competing_printing_vote(first_matches,tmp_path):
    from app.recognition.local_match import LocalArtworkVerifier
    verifier=LocalArtworkVerifier(tmp_path)
    calls=[]
    def verify(*args):
        calls.append(args[3:])
        return ['established'] if first_matches else ([] if len(calls)==1 else ['recovery'])
    verifier._verify=verify
    assert verifier.verify(Image.new('RGB',(300,420)),[])==(['established'] if first_matches else ['recovery'])
    assert calls==([(1000,.04,False)] if first_matches else [(1000,.04,False),(2000,.02,True)])


@pytest.mark.parametrize('badge',[False,True])
def test_readable_issuer_date_condition_scope_translated_holder_title_without_certificate(badge):
    from app.recognition.ocr import CardOcr
    reader=object.__new__(CardOcr)
    header=['CGC','CERTIFIED GUARANTY COMPANY','Example ex','GEM MINT','Pokémon (2024) Japanese']
    if badge:header+=['Basic']
    outputs=iter([(header,[.99]*len(header)),(['042/071'],[.99])])
    reader._run=lambda im:next(outputs)
    result=reader.read(Image.new('RGB',(500,700)))
    expected='name' if badge else 'holder_name'
    assert OcrHit('Example ex',.99,expected) in result.hits
    assert OcrHit('042/071',.99,'collector') in result.hits


def test_grading_bypasses_line_rotation_without_mutating_shared_engine(monkeypatch):
    import sys
    from types import SimpleNamespace
    import numpy as np
    from app.recognition.ocr import CardOcr
    monkeypatch.setitem(sys.modules,'rapidocr.ch_ppocr_cls.utils',SimpleNamespace(TextClsOutput=SimpleNamespace))
    monkeypatch.setitem(sys.modules,'rapidocr.main',SimpleNamespace(RapidOCRError=RuntimeError))
    calls=[]
    def finalize(*args):
        calls.append('finalize')
        return SimpleNamespace(txts=['9'],scores=[.99],boxes=np.array([[[1,1],[15,1],[15,15],[1,15]]]))
    engine=SimpleNamespace(use_cls=True,use_det=True,use_rec=True,
        preprocess_img=lambda a:(a,{}),get_det_res=lambda a,r:([a],SimpleNamespace()),
        get_rec_res=lambda p:SimpleNamespace(),finalize_results=finalize)
    reader=object.__new__(CardOcr);reader.engine=engine
    lines=reader._grading_lines(Image.new('RGB',(50,50)))
    assert lines[0].text=='9' and calls==['finalize']
    assert engine.use_cls is True and engine.use_det is True and engine.use_rec is True


@pytest.mark.parametrize('badge',[False,True])
def test_structured_holder_header_does_not_become_card_title_contradiction(badge):
    from app.recognition.ocr import CardOcr
    reader=object.__new__(CardOcr)
    header=['2024 POKEMON','BECKETTO','GEM MT','12345678']
    if badge:header+=['Basic','Example V']
    outputs=iter([(header,[.99]*len(header)),(['42/100'],[.99])])
    reader._run=lambda im:next(outputs)
    result=reader.read(Image.new('RGB',(500,700)))
    expected='name' if badge else 'holder_name'
    assert any(h.region==expected and h.text=='BECKETTO' for h in result.hits)
    assert result.name_text==('Example V' if badge else 'BECKETTO')
    assert OcrHit('42/100',.99,'collector') in result.hits


def test_badge_at_clipped_header_can_request_one_wider_title_read():
    from app.recognition.ocr import CardOcr
    reader=object.__new__(CardOcr)
    outputs=iter([(['#042','6007zz00','STAGE1'],[.99,.79,.99]),
                  (['42/100'],[.99]),
                  (['#042','6007zz00','STAGE1','Example V'],[.99,.79,.99,.99])])
    calls=[]
    def run(image):
        calls.append(image.size)
        return next(outputs)
    reader._run=run
    result=reader.read(Image.new('RGB',(500,700)))
    assert result.name_text=='Example V' and len(calls)==3
    assert OcrHit('Example V',.99,'name') in result.hits


def test_numeric_barcode_noise_not_title_but_porygon2_preserved():
    assert pick_name_line(['6007zz00','12345']) is None
    assert pick_name_line(['Porygon2'])=='Porygon2'
