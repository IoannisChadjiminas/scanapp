import copy
import importlib.util
from pathlib import Path
import sys

import pytest

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('alias_batch',scripts/'prepare_catalogue_alias_batch.py')
batch=importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


@pytest.fixture
def evidence():
    card=dict(id='en:set-015',language='en',set_id='set',name='Squirtle',collector_number='015',
              variants_json='{"holo":true}',remote_image_url='https://example/reference',cardmarket_url=None)
    legacy=dict(card,id='set-015',cardmarket_url='https://example/Squirtle-V3-ABC015',cardmarket_verified=1)
    product=dict(url=legacy['cardmarket_url'],name='Squirtle (ABC 015)From 0,02 €',card_id=legacy['id'],matched=1)
    cards={card['id']:card,legacy['id']:legacy}
    hashes={cid:dict(sha256='a'*64,path='/data/'+cid) for cid in cards}
    helpers={legacy['id']:dict(cardmarket_url=legacy['cardmarket_url'])}
    return cards,{product['url']:product},hashes,helpers


def test_reuses_explicit_primary_without_guessing_finish(evidence):
    original=copy.deepcopy(evidence)
    accepted,held=batch.select_aliases(*evidence)
    assert len(accepted)==1 and not held
    assert 'V3' in accepted[0]['product_before']['url']
    assert accepted[0]['finish'] is None and not accepted[0]['finish_verified']
    assert not accepted[0]['live_access_verified'] and not accepted[0]['published']
    assert evidence==original


@pytest.mark.parametrize('conflict', ['language','stamp','bytes','owner','collector','helper','unverified','url'])
def test_conflict_never_becomes_an_approved_alias(evidence,conflict):
    cards,products,hashes,helpers=evidence
    legacy=cards['set-015'];product=next(iter(products.values()))
    if conflict=='language':legacy['language']='ja'
    if conflict=='stamp':legacy['variants_json']='{"holo":true,"stamp":"prize"}'
    if conflict=='bytes':hashes['set-015']['sha256']='b'*64
    if conflict=='owner':product['card_id']='ja:other'
    if conflict=='collector':product['name']='Squirtle (ABC 015a)'
    if conflict=='helper':helpers['set-015']['cardmarket_url']='https://example/wrong'
    if conflict=='unverified':legacy['cardmarket_verified']=0
    if conflict=='url':
        old_url=legacy['cardmarket_url']
        new_url='https://example/Squirtle-V3-ABC016'
        products[new_url]=products.pop(old_url)
        product['url']=new_url
        legacy['cardmarket_url']=new_url
        helpers['set-015']['cardmarket_url']=new_url
    accepted,held=batch.select_aliases(*evidence)
    assert not accepted and len(held)==1 and held[0]['reasons']
