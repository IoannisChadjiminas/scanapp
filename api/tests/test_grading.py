import io
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.admission import ScanLimiter
from app.db import connect, init_catalog, init_results
from app.recognition.grading import LabelLine, parse_label
from app.recognition.ocr import CardOcr, OcrResult
from app.recognition.pipeline import recognize_bytes
from app.routes.scans import router
from app.schemas import GradingEvidence


def label(*texts):
    return [LabelLine(text, .99, (.1, .1+i*.08, .5, .16+i*.08)) for i,text in enumerate(texts)]


@pytest.mark.parametrize('brand,company,descriptor,number', [
    ('PSA','psa','GEM MT',10), ('Beckett','beckett','GEM MINT',9.5),
    ('BGS','beckett','PRISTINE',10), ('CGC CARDS','cgc','PRISTINE',10),
    ('CGC','cgc','GEM MINT',9.5), ('TAG GRADING','tag','GEM MINT',10),
    ('ACE','ace','GEM MINT',10), ('AGS','ags','MINT',9),
    ('ROBOGRADING','ags','MINT',9.3), ('PSA','psa','EX-MT',6.5),
])
def test_supported_grading_companies_and_printed_grades(brand,company,descriptor,number):
    evidence = parse_label(label(brand, f'{descriptor} {number}', '12345678'))
    assert evidence.company == company and evidence.grade == number
    assert evidence.condition_label == descriptor
    assert evidence.is_graded and evidence.slab_detected
    assert evidence.certification_number == '12345678'
    assert evidence.grading_status == 'graded'
    assert evidence.raw_condition == 'not_assessed'
    assert evidence.authenticity_verified is False and evidence.requires_confirmation


def test_standalone_digit_requires_observed_nearby_descriptor():
    assert parse_label(label('PSA','GEM MT','10')).grade == 10
    assert parse_label([LabelLine(t,.99) for t in ('PSA','GEM MT','10')]).grade is None
    lines = [LabelLine('PSA',.99), LabelLine('GEM MT',.99,(.1,.1,.4,.2)),
             LabelLine('10',.99,(.1,.85,.4,.95))]
    assert parse_label(lines).grade is None


@pytest.mark.parametrize('texts', [
    ['TAG TEAM','Pikachu & Zekrom','HP 240','10'], ['ACE SPEC','Prime Catcher','10'],
    ['PSA'], ['PSA','2023 POKEMON','HP 80','36/198','71772050'],
    ['Beckett','Pikachu','Thunder Shock 10'], ['MINT 10'], [],
])
def test_no_false_grades_from_card_text_or_seller_watermarks(texts):
    result = parse_label(label(*texts))
    assert result.grade is None and result.company is None
    assert result.slab_detected is None and result.is_graded is None
    assert result.grading_status == 'unknown'


@pytest.mark.parametrize('confidence', [.79, None, float('nan')])
def test_low_confidence_company_never_claims_grade(confidence):
    result = parse_label([LabelLine('PSA',confidence), LabelLine('GEM MT 10',.99)])
    assert result.grade is None and result.company is None


@pytest.mark.parametrize('bad', ['0','11','9.5','9.3','10/10','#10','10 HP'])
def test_invalid_psa_grades_and_other_numbers_are_not_grades(bad):
    assert parse_label(label('PSA',f'GEM MT {bad}')).grade is None


def test_conflicting_grades_and_companies_are_not_silently_chosen():
    result = parse_label(label('PSA','GEM MT 10','MINT 9'))
    assert result.grade is None and 'conflicting_overall_grades' in result.warnings
    result = parse_label(label('PSA','CGC','GEM MT 10'))
    assert result.company is None and result.grade is None
    assert 'conflicting_grading_companies' in result.warnings


def test_authentication_only_is_not_a_numerical_grade():
    result = parse_label(label('PSA','AUTHENTIC ALTERED','12345678'))
    assert result.slab_detected and result.is_graded is False
    assert result.grading_status == 'authenticated_only' and result.grade is None
    assert result.authenticity_verified is False


def test_subgrades_and_tag_score_never_become_overall_grade():
    result = parse_label(label('Beckett','GEM MINT','CENTERING 10','CORNERS 9.5',
                               'EDGES 9.5','SURFACE 9'))
    assert result.grade is None
    assert result.subgrades == dict(centering=10, corners=9.5, edges=9.5, surface=9)
    result = parse_label(label('TAG','GEM MINT','SCORE 978'))
    assert result.tag_score == 978 and result.grade is None
    result = parse_label(label('TAG','GEM MINT 10','SCORE 978'))
    assert result.tag_score == 978 and result.grade == 10


def test_subgrade_conflict_and_qualifiers():
    result = parse_label(label('BGS','MINT 9','CORNERS 9.5','CORNERS 10','(OC)'))
    assert result.subgrades == {} and 'conflicting_subgrades' in result.warnings
    assert result.qualifiers == ['OC']


def test_separate_subgrade_digits_are_not_overall_grade():
    lines = [LabelLine('BGS',.99), LabelLine('GEM MINT',.99,(.1,.1,.4,.2)),
        LabelLine('9.5',.99,(.6,.13,.7,.23)),
        LabelLine('CENTERING',.99,(.1,.35,.25,.4)),
        LabelLine('10',.99,(.15,.25,.2,.3)),
        LabelLine('CORNERS',.99,(.35,.35,.5,.4)),
        LabelLine('9',.99,(.39,.25,.46,.3))]
    result = parse_label(lines)
    assert result.grade == 9.5
    assert result.subgrades == {'centering':10, 'corners':9}


def test_explicit_grade_without_space_and_multiple_certificates():
    result = parse_label(label('CGC','2023 POKEMON','Grade:10'))
    assert result.grade == 10
    result = parse_label(label('PSA','GEM MT 10','12345678','87654321'))
    assert result.grade is None and result.certification_number is None
    assert 'certification_number_ambiguous' in result.warnings


@pytest.mark.parametrize('brand,company', [
    ('Beckett®','beckett'),('PSA™','psa'),('&CGC','cgc'),
    ('CGCUNIVERSALGRADE','cgc'),('CGC Universal Grade','cgc'),
])
def test_brand_typography_and_legacy_heading(brand,company):
    result = parse_label(label(brand,'MINT 9'))
    assert result.company == company and result.grade == 9
    assert result.company_source == 'label_ocr'


@pytest.mark.parametrize('descriptor', ['MINT+','NM-MT+','NM/MINT+','NEAR MINT+'])
def test_plus_descriptors_preserve_literal_grade(descriptor):
    result = parse_label(label('Beckett',descriptor+' 8.5'))
    assert result.grade == 8.5 and result.condition_label == descriptor


def test_native_ags_legendary_does_not_supply_a_number():
    assert parse_label(label('AGS','LEGENDARY')).grade is None
    result = parse_label(label('AGS','LEGENDARY 10'))
    assert result.grade == 10 and result.condition_label == 'LEGENDARY'


def test_formatting_differences_are_not_descriptor_conflicts():
    result = parse_label(label('TAG','GEM.MINT 10','GEM MINT','GEMMINT'))
    assert result.grade == 10 and 'conflicting_condition_labels' not in result.warnings
    assert parse_label(label('TAG','GEM MINT 10','PRISTINE')).grade is None


def test_logo_only_requires_independent_label_context():
    assert parse_label(label('MINT 9'),visual_company='ace').company is None
    result = parse_label(label('#TG11','FAIR','2','1234567'),visual_company='ace')
    assert result.company == 'ace' and result.company_source == 'verified_logo'
    assert result.grade == 2
    conflict = parse_label(label('PSA','#TG11','MINT 9','1234567'),visual_company='ace')
    assert conflict.company is None and 'conflicting_grading_companies' in conflict.warnings


@pytest.mark.parametrize('brand', ['BECKETTO','BECKETTs','FSA','PA','TA','AG5','TAG TEAM','ACE SPEC'])
def test_no_fuzzy_issuer_aliases(brand):
    result = parse_label(label(brand,'MINT 9'))
    assert result.company is None and result.grade is None


def test_label_region_hypotheses_are_not_slab_evidence(monkeypatch):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision,'label_panels',lambda image:[image,image])
    monkeypatch.setattr(vision,'logo_company',lambda image,**kwargs:('ace',.99))
    reader = object.__new__(CardOcr)
    calls = []
    def engine(array):
        calls.append(1)
        return SimpleNamespace(txts=['ACE SPEC','TAG TEAM','HP 100','10'],scores=[.99]*4)
    reader.engine = engine
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert len(calls) <= 10
    assert result.company is None and result.grade is None and result.slab_detected is None


def test_no_issuer_transfer_from_unrelated_holder(monkeypatch):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision,'label_panels',lambda image:[image])
    monkeypatch.setattr(vision,'text_label_panel',lambda image,lines,**kwargs:None)
    monkeypatch.setattr(vision,'logo_company',lambda image,**kwargs:None)
    reader = object.__new__(CardOcr)
    observations = iter([label('PSA','2023 POKEMON','MINT','1234567'),
                         label('2023 POKEMON','GEM MT 10','7654321')])
    reader._grading_lines = lambda image: next(observations)
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert result.grade is None and result.company is None
    assert 'certification_number_ambiguous' in result.warnings


def test_card_ex_suffix_below_certificate_cannot_conflict_with_label():
    lines = [LabelLine('2016 POKEMON',.99,(.1,.10,.5,.15)),
             LabelLine('CGC',.99,(.1,.01,.3,.06)),
             LabelLine('NEAR MINT',.99,(.65,.20,.95,.25)),
             LabelLine('7',.99,(.70,.15,.85,.20)),
             LabelLine('1234567',.99,(.65,.35,.95,.40)),
             LabelLine('EX',.99,(.70,.75,.80,.80))]
    result = parse_label(lines)
    assert result.grade == 7 and result.condition_label == 'NEAR MINT'
    repeated = parse_label([*lines,*lines[:-1]])
    assert repeated.grade == 7 and repeated.condition_label == 'NEAR MINT'


def test_conflicting_conditions_within_label_still_abstain():
    lines = label('CGC','2023 POKEMON','GEM MINT 10','MINT','1234567')
    result = parse_label(lines)
    assert result.grade is None and 'conflicting_condition_labels' in result.warnings


def test_visual_logo_does_not_turn_an_unreadable_gold_digit_into_ten():
    result = parse_label(label('#013','PRISTINE','1234567'),visual_company='cgc')
    assert result.company == 'cgc' and result.grade is None


@pytest.mark.parametrize('company', ['psa','beckett','tag','ace','ags'])
def test_official_logo_shape_match_is_independent_of_color(company):
    from app.recognition.label_vision import _logo_masks, logo_company
    mask = _logo_masks()[company]
    scale = 30/mask.shape[0]
    symbol = Image.fromarray(mask).resize((round(mask.shape[1]*scale),30))
    panel = Image.new('RGB',(600,200),'white')
    glyph = Image.fromarray(255-np.asarray(symbol)).convert('RGB')
    panel.paste(glyph,(300-glyph.width//2,10 if company=='tag' else 150))
    found = logo_company(panel)
    assert found is not None and found[0] == company
    inverted = logo_company(Image.fromarray(255-np.asarray(panel)))
    assert inverted is not None and inverted[0] == company
    assert inverted[1] == pytest.approx(found[1],abs=.002)


def test_unstructured_text_cannot_localize_a_grading_label():
    from app.recognition.label_vision import text_label_panel
    lines = label('ACE SPEC','TAG TEAM','Thunder Shock 10','1234567')
    assert text_label_panel(Image.new('RGB',(600,1000)),lines) is None


def test_dated_set_header_needs_independent_label_fields():
    result = parse_label(label('2022 BRILLIANT STARS','FAIR 2','1234567'))
    assert result.grade == 2 and result.company is None
    assert parse_label(label('2022 BRILLIANT STARS','2')).grade is None


def test_tag_alphanumeric_certificate_is_not_a_score_or_grade():
    result = parse_label(label('TAG','MINT 9','X5522404'))
    assert result.certification_number == 'X5522404' and result.grade == 9
    assert result.tag_score is None
    assert parse_label(label('PSA','MINT 9','X5522404')).certification_number is None


def test_landscape_photo_with_upright_slab_is_not_rotated_first():
    image = Image.new('RGB',(1000,600),'black')
    image.paste('white',(0,0,1000,216))
    calls = []
    reader = object.__new__(CardOcr)
    def engine(array):
        calls.append(array.shape)
        return SimpleNamespace(txts=['AGS','MINT+ 9.5','12345678'],scores=[.99]*3) if array.mean()>250 else None
    reader.engine = engine
    result = reader.read_grading(image)
    assert result.company == 'ags' and result.grade == 9.5
    assert len(calls) == 1


@pytest.mark.parametrize('brand,descriptor', [('CGC','PRISTINE'),('BGS','PERFECT'),('AGS','LEGENDARY')])
def test_descriptor_numeric_contradiction_abstains_without_inferring_ten(brand,descriptor):
    result = parse_label(label(brand,descriptor+' 4'))
    assert result.company is not None and result.grade is None
    assert 'condition_grade_contradiction' in result.warnings
    assert parse_label(label(brand,descriptor)).grade is None


@pytest.mark.parametrize('brand',['PSA','BGS','CGC','TAG','ACE','AGS'])
def test_gem_descriptor_cannot_confirm_fragment_of_a_large_ten(brand):
    result = parse_label(label(brand,'GEM MINT 1'))
    assert result.grade is None and 'condition_grade_contradiction' in result.warnings


def test_threshold_only_digit_needs_corroboration(monkeypatch):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision,'label_panels',lambda image:[image])
    monkeypatch.setattr(vision,'text_label_panel',lambda image,lines,**kwargs:None)
    monkeypatch.setattr(vision,'logo_company',lambda image,**kwargs:None)
    reader = object.__new__(CardOcr)
    calls = []
    readings = [label('CGC','2023 POKEMON','MINT','1234567')]*3 + [label('8'),[]]
    def read(image):
        calls.append(1)
        return readings[len(calls)-1] if len(calls)<=len(readings) else []
    reader._grading_lines = read
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert result.grade is None and len(calls) <= 10


@pytest.mark.parametrize('reads,expected', [(['10','10'],10),(['10','9'],None),
                                          (['4','4'],None),(['','10'],None)])
def test_direct_numeral_recovery_needs_repeated_literal_read(monkeypatch,reads,expected):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision,'label_panels',lambda image:[image])
    monkeypatch.setattr(vision,'text_label_panel',lambda image,lines,**kwargs:None)
    monkeypatch.setattr(vision,'logo_company',lambda image,**kwargs:None)
    monkeypatch.setattr(vision,'grade_regions',lambda image,lines,company,**kwargs:
        [(image,(.1,.4,.5,.6))])
    reader = object.__new__(CardOcr)
    reader.engine = SimpleNamespace(get_rec_res=lambda *a:None)
    calls = []
    def read(image):
        calls.append('detector')
        return label('CGC','2023 POKEMON','PRISTINE','1234567')
    reader._grading_lines = read
    sequence = iter(reads)
    def tokens(patches):
        calls.extend(['recognizer']*len(patches))
        return [LabelLine(next(sequence),.99) for _ in patches]
    reader._grading_tokens = tokens
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert result.grade == expected and len(calls) <= 10
    if reads == ['4','4']:
        assert 'condition_grade_contradiction' in result.warnings


def test_direct_recognition_never_mutates_shared_ocr_flags():
    class Engine:
        use_det,use_cls = True,True
        def __call__(self,*a,**kw):
            raise AssertionError('must not mutate engine through parameter update')
        def get_rec_res(self,images):
            assert len(images) == 2
            return SimpleNamespace(txts=['','10'],scores=[.2,.99])
    reader = object.__new__(CardOcr)
    reader.engine = Engine()
    result = reader._grading_tokens([Image.new('RGB',(60,80))]*2)
    assert [l.text for l in result] == ['', '10']
    assert reader.engine.use_det is True and reader.engine.use_cls is True


def test_repeat_contrast_read_losing_same_field_plus_preserves_literal_grade(monkeypatch):
    import app.recognition.label_vision as vision
    monkeypatch.setattr(vision,'label_panels',lambda image:[image])
    monkeypatch.setattr(vision,'text_label_panel',lambda image,lines,**kwargs:None)
    monkeypatch.setattr(vision,'logo_company',lambda image,**kwargs:None)
    reader = object.__new__(CardOcr)
    first = label('2023 POKEMON','MINT+','9.5','1234567')
    repeat = label('2023 POKEMON','MINT','9.5','1234567')
    reader._grading_lines = lambda image: first if image.width != 1200 else repeat
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert result.grade == 9.5 and result.company is None


def test_label_padding_keeps_overhanging_top_and_bottom_marks():
    from app.recognition.label_vision import text_label_panel
    image = Image.new('RGB',(1000,1000),'white')
    image.paste('red',(500,125,540,145))
    image.paste('blue',(500,245,540,265))
    lines = [LabelLine('2023 POKEMON',.99,(.3,.45,.6,.50)),
             LabelLine('MINT',.99,(.6,.55,.7,.60)),
             LabelLine('9',.99,(.6,.50,.7,.55)),
             LabelLine('1234567',.99,(.6,.60,.7,.65))]
    panel = text_label_panel(image,lines)
    pixels = np.asarray(panel)
    assert np.any(np.all(pixels == [255,0,0],axis=2))
    assert np.any(np.all(pixels == [0,0,255],axis=2))


def test_numeric_dated_set_needs_independent_label_evidence():
    assert parse_label(label('2023 123')).slab_detected is None
    assert parse_label(label('2023123','MINT 9')).slab_detected is None
    result = parse_label(label('2023 123','MINT 9','1234567'),visual_company='ace')
    assert result.company == 'ace' and result.grade == 9


def test_supplemental_official_marks_share_the_issuer_not_compete():
    from app.recognition.label_vision import _logo_masks, logo_company
    for name in ('ace-outline','beckett-emblem'):
        mask = _logo_masks()[name]
        panel = Image.new('RGB',(600,200),'white')
        glyph = Image.fromarray(mask).resize((round(40*mask.shape[1]/mask.shape[0]),40))
        glyph = Image.fromarray(255-np.asarray(glyph)).convert('RGB')
        panel.paste(glyph,(300,140 if name.startswith('ace') else 50))
        found = logo_company(panel)
        assert found and found[0] == name.split('-')[0]


def test_monogram_inside_an_ocr_word_is_not_independent_logo_evidence():
    from app.recognition.label_vision import _logo_masks, logo_company
    mask = _logo_masks()['beckett-emblem']
    panel = Image.new('RGB',(600,200),'white')
    width = round(40*mask.shape[1]/mask.shape[0])
    glyph = Image.fromarray(mask).resize((width,40))
    panel.paste(Image.fromarray(255-np.asarray(glyph)).convert('RGB'),(300,50))
    assert logo_company(panel)[0] == 'beckett'
    assert logo_company(panel,text_boxes=[(.49,.24,.65,.46)]) is None
    assert logo_company(panel,text_boxes=[(.05,.65,.25,.8)])[0] == 'beckett'


def test_tiny_monogram_is_not_issuer_proof():
    from app.recognition.label_vision import _logo_masks, logo_company
    mask = _logo_masks()['beckett-emblem']
    panel = Image.new('RGB',(600,200),'white')
    glyph = Image.fromarray(mask).resize((round(12*mask.shape[1]/mask.shape[0]),12))
    panel.paste(Image.fromarray(255-np.asarray(glyph)).convert('RGB'),(300,50))
    found = logo_company(panel)
    assert found is None or found[0] != 'beckett'


def test_ink_regions_do_not_invent_glyphs_on_a_blank_label():
    from app.recognition.label_vision import grade_regions
    assert grade_regions(Image.new('RGB',(600,200),'white'),label('MINT'),'ace') == []


@pytest.mark.parametrize('descriptor,grade', [('EX/NM+',6.5),('EX/NM',6),
    ('EXCELLENT+',5.5),('VG/EX+',4.5),('VERY GOOD+',3.5),('GOOD+',2.5)])
def test_cgc_lower_halfpoint_vocabulary_preserves_printed_number(descriptor,grade):
    result = parse_label(label('CGC',f'{descriptor} {grade}'))
    assert result.grade == grade and result.condition_label == descriptor


@pytest.mark.parametrize('descriptor', ['AUTHENTIC AU','AUTHENTIC ALTERED AA','AUTHENTIC ART ART'])
def test_native_cgc_authentication_designations_do_not_claim_grades(descriptor):
    result = parse_label(label('CGC',descriptor,'AUTO 10'))
    assert result.grading_status == 'authenticated_only' and result.grade is None


def test_targeted_logo_retry_does_not_guess_or_reuse_digits():
    reader = object.__new__(CardOcr)
    calls = []
    def engine(array):
        calls.append(array.shape)
        if len(calls) == 1:
            return SimpleNamespace(txts=['2023 POKEMON','#43','GEM MT','10','12345678'],
                scores=[.99]*5,boxes=np.array([
                [[10,10],[200,10],[200,40],[10,40]],
                [[700,10],[800,10],[800,40],[700,40]],
                [[700,50],[800,50],[800,80],[700,80]],
                [[700,90],[800,90],[800,120],[700,120]],
                [[700,140],[900,140],[900,170],[700,170]]]))
        return SimpleNamespace(txts=['PSA','9','12345679'],scores=[.99]*3)
    reader.engine = engine
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert result.company is None and result.grade == 10
    assert result.certification_number == '12345678'
    assert len(calls) <= 10


def test_readable_label_with_unreadable_logo_preserves_partial_evidence():
    result = parse_label(label('2023 POKEMON','#43','GEM MT','10','12345678'))
    assert result.slab_detected and result.grade == 10
    assert result.company is None
    assert 'grading_company_unreadable_or_unsupported' in result.warnings


def test_logo_retry_exception_respects_budget_and_preserves_partial_read():
    reader = object.__new__(CardOcr)
    calls = []
    def engine(array):
        calls.append(1)
        if len(calls) == 1:
            return SimpleNamespace(txts=['2023 POKEMON','#43','GEM MT 10','12345678'],scores=[.99]*4)
        raise RuntimeError('logo tile failed')
    reader.engine = engine
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert len(calls) == 2
    assert result.grade == 10 and result.company is None
    assert 'grading_ocr_failed' in result.warnings


def test_second_orientation_logo_retry_stays_within_budget():
    reader = object.__new__(CardOcr)
    calls = []
    def engine(array):
        calls.append(1)
        return None if len(calls) == 1 else SimpleNamespace(
            txts=['2023 POKEMON','#43','GEM MT 10','12345678'],scores=[.99]*4)
    reader.engine = engine
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert len(calls) <= 10 and result.grade == 10 and result.company is None


@pytest.mark.parametrize('angle', [0,90,180,270])
def test_label_reader_handles_rotation_and_is_bounded(angle):
    image = Image.new('RGB',(600,1000))
    image.paste('white',(0,0,600,360))
    image = image.rotate(angle,expand=True)
    calls = []
    def engine(array):
        calls.append(array.shape)
        if array.mean() > 250:
            return SimpleNamespace(txts=['PSA','GEM MT','10'], scores=[.99]*3,
                boxes=np.array([[[100,50],[300,50],[300,80],[100,80]],
                    [[100,100],[300,100],[300,130],[100,130]],
                    [[100,140],[300,140],[300,170],[100,170]]]))
        return None
    reader = object.__new__(CardOcr)
    reader.engine = engine
    evidence = reader.read_grading(image)
    assert evidence.company == 'psa' and evidence.grade == 10
    assert len(calls) <= 10


def test_ocr_failure_is_explicit_unknown():
    reader = object.__new__(CardOcr)
    def engine(array):
        raise RuntimeError('model failure')
    reader.engine = engine
    result = reader.read_grading(Image.new('RGB',(600,1000)))
    assert result.grading_status == 'unknown' and 'grading_ocr_failed' in result.warnings


@pytest.mark.parametrize('mode', ['enabled','disabled','failure'])
def test_api_scan_history_persistence_and_ranking_isolation(tmp_path, mode):
    catalog, results = connect(tmp_path/'catalog.sqlite'), connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    settings = Settings(_env_file=None, data_dir=tmp_path, store_captures=False,
                        use_grading=mode != 'disabled')
    app.state.settings = settings
    app.state.dbs = SimpleNamespace(catalog=catalog, results=results)
    client = TestClient(app)
    session = client.get('/api/v1/session/results').json()['session_id']
    catalog.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES('card','card','Pikachu','set','Set','58','en')")
    catalog.commit()
    calls = []
    def read_grading(image):
        calls.append(image.size)
        if mode == 'failure':
            raise RuntimeError('label engine only')
        return parse_label(label('PSA','GEM MT 10','12345678'))
    ocr_engine = SimpleNamespace(read=lambda im: OcrResult(), read_grading=read_grading)
    runtime = SimpleNamespace(require=lambda:(
        SimpleNamespace(card_ids=np.array(['card']),embeddings=np.array([[1.,0.]],dtype=np.float32)),
        SimpleNamespace(embed=lambda *a:np.array([1.,0.],dtype=np.float32)),ocr_engine),
        card_languages=np.array(['en']),artwork_verifier=None,printing_index=None,
        versions=lambda:dict(model_revision='test',catalogue='test',ocr='test',ranking='test'),
        threshold_config=lambda:{})
    image = Image.fromarray(np.random.default_rng(12).integers(0,255,(1000,600,3),dtype=np.uint8))
    payload = io.BytesIO()
    image.save(payload,format='JPEG')
    try:
        response = recognize_bytes(payload.getvalue(),settings=settings,runtime=runtime,
            catalog=catalog,results=results,session_id=session,skip_detect=True,
            crop_x=0,crop_y=.3,crop_w=1,crop_h=.7)
        assert response.best_match.card_id == 'card'
        if mode == 'enabled':
            assert response.grading.grade == 10 and calls == [(600,700)]
        else:
            assert response.grading.grade is None
            assert bool(calls) == (mode == 'failure')
        saved = client.get('/api/v1/session/results').json()['results'][0]
        assert saved['grading'] == response.grading.model_dump(mode='json')
        persisted = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0])
        assert persisted['grading'] == saved['grading']
        assert response.timings_ms['grading_ms'] >= 0
        # Exercise multipart upload and FastAPI response-model serialization,
        # not only the pipeline and GET history paths.
        @asynccontextmanager
        async def lifespan(application):
            with ThreadPoolExecutor(max_workers=1) as executor:
                application.state.loop = asyncio.get_running_loop()
                application.state.executor = executor
                application.state.scan_limiter = ScanLimiter(wait_limit=1)
                application.state.runtime = runtime
                yield
        app.router.lifespan_context = lifespan
        with client:
            uploaded = client.post('/api/v1/scans',data={'skip_detect':'true'},
                files={'image':('scan.jpg',payload.getvalue(),'image/jpeg')})
            assert uploaded.status_code == 200
            assert uploaded.json()['grading'] == response.grading.model_dump(mode='json')
            history = client.get('/api/v1/session/results').json()['results']
            assert next(r for r in history if r['scan_id'] == uploaded.json()['id'])['grading'] == uploaded.json()['grading']
        # Historical rows are unknown; do not fabricate grades on old scans.
        results.execute("INSERT INTO scans(id,session_id,created_at,status,preprocessing) VALUES('legacy',?,'2026-10-02T01:00:00Z','no_match','pad')",(session,))
        results.commit()
        legacy = next(r for r in client.get('/api/v1/session/results').json()['results'] if r['scan_id'] == 'legacy')
        assert legacy['grading'] == GradingEvidence().model_dump(mode='json')
    finally:
        catalog.close()
        results.close()
