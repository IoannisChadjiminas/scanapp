import pytest
from PIL import Image
from app.recognition.stamp_printing import stamp_printing_hint, observe_play_stamp
from app.recognition.ocr import OcrHit


def row(card_id,set_name,number='159',score=.88,name='Arbitrary Card'):
    return dict(card_id=card_id,name=name,language='en',collector_number=number,
                printed_collector_number=number+'/182',set_name=set_name,
                combined_score=score,visual_score=score)


@pytest.mark.parametrize('observed,expected',[(True,'stamped'),(False,'base')])
def test_stamp_is_only_a_display_hint_and_does_not_drop_alternatives(observed,expected):
    rows=[row('stamped','Play! Pokémon Prize Pack Series Five'), row('base','Original Set',score=.86),
          row('reprint','Other Set',number='140',score=.87)]
    hint=stamp_printing_hint(rows,rows,Image.new('RGB',(600,840)),ocr_name='Arbitrary Card',
        name_confidence=.99,numbers=[OcrHit('159/182',.99,'collector')],languages=('en',),
        observer=lambda _:dict(observed=observed,inliers=12 if observed else 0))
    assert hint['preferred_card_id']==expected
    assert 'does not prove' in hint['policy'] and len(rows)==3 and rows[0]['card_id']=='stamped'


def test_wrong_collector_language_identity_or_large_gap_is_never_promoted():
    lead=row('stamped','Play! Pokémon Prize Pack Series Five')
    for alternate in (row('base','Original Set',number='140'),row('base','Original Set',score=.7),
                      row('base','Original Set',name='Unrelated Card'),dict(row('base','Original Set'),language='ja')):
        assert stamp_printing_hint([lead,alternate],[lead,alternate],None,
            ocr_name='Arbitrary Card',name_confidence=.99,numbers=[],languages=('en',),
            observer=lambda _:pytest.fail('Do not spend time on ineligible choices')) is None


def test_logo_matcher_does_not_claim_stamp_on_empty_or_textless_patch():
    assert not observe_play_stamp(Image.new('RGB',(600,840),'white'))['observed']
