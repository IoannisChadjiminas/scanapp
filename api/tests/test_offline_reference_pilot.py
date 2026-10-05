from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_offline_reference_pilot import validate_selection


def evidence():
    card=dict(name='Starmie',language='en',set_id='ecard3',collector_number='H28',cardmarket_url=None,has_image=0,image_path=None)
    selected=dict(card,verification='manual_visual',identity_approved=True,readable_contradictions=False,unexpected_stamp_observed=False)
    return card,selected


@pytest.mark.parametrize('field,value',[('name','Staryu'),('language','ja'),('set_id','E5'),('collector_number','28'),('cardmarket_url','https://example.com/a'),('unexpected_stamp_observed',True),('readable_contradictions',True),('identity_approved',False)])
def test_unapproved_or_contradictory_source_cannot_enter_pilot(field,value):
    card,selection=evidence();selection[field]=value
    with pytest.raises(ValueError):validate_selection(card,selection)


def test_existing_reference_is_never_replaced():
    card,selection=evidence();card.update(has_image=1,image_path='/data/reference-images/existing.jpg')
    with pytest.raises(ValueError):validate_selection(card,selection)
