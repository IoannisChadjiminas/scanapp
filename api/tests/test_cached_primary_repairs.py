from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_cached_primary_repairs import checked_repair

def sample():
    card=dict(id='en:base4-1',set_id='base4',set_name='Base Set 2',language='en',name='Alakazam',collector_number='1',cardmarket_url=None,cardmarket_id=273924,image_path='/data/reference-images/en/base4-1.webp')
    product=dict(url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set-2/Alakazam-B21',name='Alakazam (B2 1)',expansion='Base-Set-2',card_id=card['id'],matched=1)
    review=dict(url=product['url'],metadata=dict(photo_key='cm273924'))
    decision=dict(card_id=card['id'],visible_name='Alakazam',primary_identity_approved=True,primary_url=product['url'],visible_language='en',visible_set_symbol='Base Set 2 numeral-2/Pokeball symbol',visible_collector_raw='1/130',unexpected_stamp_observed=False,listing_photo_key='cm273924',original_sha256='original',reviewed_at='2026-10-04T04:30:00Z')
    feature=dict(source_sha256='original',image_path=card['image_path'],available=True)
    return card,product,[product],review,decision,feature

def test_exact_ordinary_primary_preserves_source_and_ownership():
    values=sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['cardmarket_url']==helper['cardmarket_url']==values[1]['url']
    assert after['image_path']==values[0]['image_path']
    assert values==before

@pytest.mark.parametrize('field,value',[('language','ja'),('set_name','Japanese Expansion Pack'),('collector_number','10')])
def test_same_name_short_code_cannot_override_exact_scope(field,value):
    values=sample();values[0][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def test_extra_finish_cannot_be_implicitly_selected():
    values=sample();sibling=deepcopy(values[1]);sibling['url']+='-V2';values[2].append(sibling)
    with pytest.raises(AssertionError):checked_repair(*values)

def test_cached_photo_binding_must_agree():
    values=sample();values[3]['metadata']['photo_key']='cm000000'
    with pytest.raises(AssertionError):checked_repair(*values)

def test_reference_bytes_must_match_deployed_manifest():
    values=sample();values[5]['source_sha256']='different'
    with pytest.raises(AssertionError):checked_repair(*values)

def test_visible_name_contradiction_is_rejected():
    values=sample();values[4]['visible_name']='Dark Alakazam'
    with pytest.raises(AssertionError):checked_repair(*values)

def test_stamp_and_print_number_cannot_be_inferred():
    values=sample();values[4]['visible_collector_raw']='1/102'
    with pytest.raises(AssertionError):checked_repair(*values)

@pytest.mark.parametrize('field,value',[
    ('expansion','Japanese-Expansion-Pack'),('card_id','ja:B2-001'),
    ('url','https://www.cardmarket.com/en/Pokemon/Products/Singles/Japanese-Expansion-Pack/Alakazam-B21'),
    ('matched',0)])
def test_wrong_product_owner_or_expansion_stays_pending(field,value):
    values=sample();values[1][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)
    values=sample();values[4]['unexpected_stamp_observed']=True
    with pytest.raises(AssertionError):checked_repair(*values)

def fusion_sample():
    card=dict(id='en:swsh8-106',set_id='swsh8',set_name='Fusion Strike',language='en',name='Toxel',collector_number='106',cardmarket_url=None,cardmarket_id=582499,image_path='/data/reference-images/en/swsh8-106.webp',variants_json='{"firstEdition":false,"holo":false,"normal":true,"reverse":true}')
    product=dict(url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Fusion-Strike/Toxel-V2',name='Toxel (FST 106)',expansion='Fusion-Strike',card_id=card['id'],matched=1)
    review=dict(url=product['url'],metadata=dict(photo_key='cm582499'))
    decision=dict(card_id=card['id'],visible_name='Toxel',primary_identity_approved=True,primary_url=product['url'],visible_language='en',visible_set_symbol='Fusion Strike three-loop set symbol',visible_collector_raw='106/264',unexpected_stamp_observed=False,listing_photo_key='cm582499',original_sha256='original',reviewed_at='2026-10-04T05:00:00Z',visible_regulation_mark='E',visible_copyright_year='2021',edition_stamp_observed=False)
    feature=dict(source_sha256='original',image_path=card['image_path'],available=True)
    return card,product,[product],review,decision,feature

def test_v_number_is_selected_by_reviewed_full_collector_and_preserves_finish():
    values=fusion_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['cardmarket_url'].endswith('Toxel-V2')
    assert after['variants_json']==before[0]['variants_json']
    assert helper['provenance'].endswith(':Fusion-Strike')
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_regulation_mark','F'),('visible_copyright_year','2022'),
    ('edition_stamp_observed',True),('unexpected_stamp_observed',True),
    ('visible_collector_raw','105/264'),('visible_set_symbol','Evolving Skies symbol')])
def test_modern_printing_marks_must_match(field,value):
    values=fusion_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def test_v2_does_not_disambiguate_same_collector_finish_siblings():
    values=fusion_sample();other=deepcopy(values[1]);other['url']+='-Reverse';values[2].append(other)
    with pytest.raises(AssertionError):checked_repair(*values)

def test_printed_zero_padding_keeps_raw_evidence_without_losing_full_number():
    values=fusion_sample();values[0]['collector_number']='29';values[1]['name']='Toxel (FST 29)';values[4]['visible_collector_raw']='029/264'
    checked_repair(*values)
    assert values[4]['visible_collector_raw']=='029/264'
    values[4]['visible_collector_raw']='029a/264'
    with pytest.raises(AssertionError):checked_repair(*values)

def evolving_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:swsh7-110',set_id='swsh7',set_name='Evolving Skies',name='Rayquaza V',collector_number='110')
    product.update(card_id=card['id'],name='Rayquaza V (EVS 110)',expansion='Evolving-Skies',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Evolving-Skies/Rayquaza-V-V1')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Evolving Skies mountain set symbol',visible_collector_raw='110/203')
    return values

def test_evolving_exact_print_scope_preserves_variant_properties():
    values=evolving_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['variants_json']==before[0]['variants_json']
    assert helper['cardmarket_url']==values[1]['url']
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_collector_raw','110/264'),('visible_regulation_mark','F'),
    ('visible_copyright_year','2022'),('edition_stamp_observed',True),
    ('visible_set_symbol','Fusion Strike three-loop set symbol')])
def test_evolving_other_set_or_print_evidence_is_rejected(field,value):
    values=evolving_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def battle_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:swsh5-169',set_id='swsh5',set_name='Battle Styles',name='Rapid Strike Urshifu VMAX',collector_number='169')
    product.update(card_id=card['id'],name='Rapid Strike Urshifu VMAX (BST 169)',expansion='Battle-Styles',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Battle-Styles/Rapid-Strike-Urshifu-VMAX-V2')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Battle Styles fist set symbol',visible_collector_raw='169/163')
    return values

def test_battle_secret_collector_preserves_identity_and_variants():
    values=battle_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['collector_number']=='169'
    assert after['variants_json']==before[0]['variants_json']
    assert helper['cardmarket_url']==values[1]['url']
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_collector_raw','169/203'),('visible_regulation_mark','F'),
    ('visible_copyright_year','2022'),('edition_stamp_observed',True),
    ('visible_set_symbol','Evolving Skies mountain set symbol')])
def test_battle_other_set_or_print_evidence_is_rejected(field,value):
    values=battle_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def chilling_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:swsh6-20',set_id='swsh6',set_name='Chilling Reign',name='Blaziken V',collector_number='20')
    product.update(card_id=card['id'],name='Blaziken V (CRE 20)',expansion='Chilling-Reign',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Chilling-Reign/Blaziken-V-V1')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Chilling Reign crown set symbol',visible_collector_raw='020/198')
    return values

def test_chilling_exact_collector_preserves_identity_and_variants():
    values=chilling_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['collector_number']=='20'
    assert after['variants_json']==before[0]['variants_json']
    assert helper['cardmarket_url']==values[1]['url']
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_collector_raw','020/163'),('visible_regulation_mark','F'),
    ('visible_copyright_year','2022'),('edition_stamp_observed',True),
    ('visible_set_symbol','Battle Styles fist set symbol')])
def test_chilling_other_set_or_print_evidence_is_rejected(field,value):
    values=chilling_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def destined_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:sv10-027',set_id='sv10',set_name='Destined Rivals',name='Growlithe',collector_number='027')
    product.update(card_id=card['id'],name='Growlithe (DRI 027)',expansion='Destined-Rivals',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Destined-Rivals/Growlithe-DRI027')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Destined Rivals DRI EN set code',visible_collector_raw='027/182',visible_regulation_mark='I',visible_copyright_year='2025')
    return values

def test_destined_exact_language_code_and_print_marks_preserve_variants():
    values=destined_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['collector_number']=='027'
    assert after['variants_json']==before[0]['variants_json']
    assert helper['cardmarket_url']==values[1]['url']
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_collector_raw','027/198'),('visible_regulation_mark','E'),
    ('visible_copyright_year','2021'),('edition_stamp_observed',True),
    ('visible_set_symbol','DRI JP')])
def test_destined_other_language_or_print_evidence_is_rejected(field,value):
    values=destined_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def rising_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:pl2-104',set_id='pl2',set_name='Rising Rivals',name='Floatzel GL LV.X',collector_number='104')
    product.update(card_id=card['id'],name='Floatzel [GL] LV.X (RR 104)',expansion='Rising-Rivals',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Rising-Rivals/Floatzel-GL-LVX-RR104')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Rising Rivals rising-sun set symbol',visible_collector_raw='104/111',visible_regulation_mark=None,visible_copyright_year='2009',edition_stamp_observed=False)
    return values

def test_rising_gl_lvx_identity_is_preserved():
    values=rising_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['name']=='Floatzel GL LV.X'
    assert after['variants_json']==before[0]['variants_json']
    assert helper['cardmarket_url']==values[1]['url']
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_name','Floatzel LV.X'),('visible_collector_raw','104/127'),
    ('visible_copyright_year','2010'),('edition_stamp_observed',True),
    ('visible_regulation_mark','E')])
def test_rising_other_identity_or_print_evidence_is_rejected(field,value):
    values=rising_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

@pytest.mark.parametrize('name',['Floatzel LV.X (RR 104)','Floatzel [C] LV.X (RR 104)'])
def test_rising_listing_print_identifier_cannot_be_removed(name):
    values=rising_sample();values[1]['name']=name
    with pytest.raises(AssertionError):checked_repair(*values)

def chaos_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:me04-107',set_id='me04',set_name='Chaos Rising',name='Emma',collector_number='107')
    product.update(card_id=card['id'],name='Emma (CRI 107)',expansion='Chaos-Rising',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Chaos-Rising/Emma-V2-CRI107')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Chaos Rising CRI EN set code',visible_collector_raw='107/086',visible_regulation_mark='J',visible_copyright_year='2026')
    return values

def test_chaos_secret_number_and_full_denominator_are_preserved():
    values=chaos_sample();before=deepcopy(values)
    after,helper=checked_repair(*values)
    assert after['collector_number']=='107'
    assert after['variants_json']==before[0]['variants_json']
    assert helper['cardmarket_url']==values[1]['url']
    assert values==before

@pytest.mark.parametrize('field,value',[
    ('visible_collector_raw','077/086'),('visible_regulation_mark','I'),
    ('visible_copyright_year','2025'),('edition_stamp_observed',True),
    ('visible_set_symbol','CRI JP')])
def test_chaos_other_collector_language_or_print_evidence_is_rejected(field,value):
    values=chaos_sample();values[4][field]=value
    with pytest.raises(AssertionError):checked_repair(*values)

def test_reviewed_reference_contradiction_blocks_primary_repair():
    values=destined_sample();values[4]['reference_pair_matches']=False
    with pytest.raises(AssertionError):checked_repair(*values)

def celebration_sample():
    values=fusion_sample()
    card,product,_,review,decision,feature=values
    card.update(id='en:cel25-11',set_id='cel25',set_name='Celebrations',name='Mew',collector_number='11')
    product.update(card_id=card['id'],name='Mew (CEL 011)',expansion='Celebrations',url='https://www.cardmarket.com/en/Pokemon/Products/Singles/Celebrations/Mew-CEL011')
    review['url']=product['url']
    decision.update(card_id=card['id'],visible_name=card['name'],primary_url=product['url'],visible_set_symbol='Celebrations set emblem and intrinsic Pikachu 25 logo',visible_collector_raw='011/025',visible_regulation_mark='E',visible_copyright_year='2021',reference_pair_matches=True)
    return values

def test_celebrations_intrinsic_anniversary_print_keeps_full_denominator():
    values=celebration_sample();before=deepcopy(values)
    after,_=checked_repair(*values)
    assert after['variants_json']==before[0]['variants_json']
    assert values[4]['visible_collector_raw']=='011/025'
    assert values==before

def test_celebrations_extra_distribution_stamp_is_not_intrinsic_logo():
    values=celebration_sample();values[4]['unexpected_stamp_observed']=True
    with pytest.raises(AssertionError):checked_repair(*values)

def test_same_name_suffixed_collector_cannot_replace_numbered_print():
    values=sample();values[4]['visible_collector_raw']='1a/130'
    with pytest.raises(AssertionError):checked_repair(*values)
