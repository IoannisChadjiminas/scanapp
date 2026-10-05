"""Additive catalogue proposals must not overwrite or invent marketplace identity."""
import copy
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image
from app.db import init_catalog

spec = importlib.util.spec_from_file_location('reference_candidate_builder',
    Path(__file__).resolve().parents[1] / 'scripts' / 'build_recovered_reference_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def catalogue(tmp_path):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_catalog(conn)
    conn.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language,cardmarket_url,cardmarket_verified) VALUES(?,?,?,?,?,?,?,?,1)',
        ('ja:existing-27','ja:existing-27','Ralts','known-set','Known Set','27','ja','https://example.invalid/verified'))
    conn.execute('INSERT INTO cards_fts(id,name,set_name,collector_number) VALUES(?,?,?,?)',
        ('ja:existing-27','Ralts','Known Set','27'))
    image = tmp_path/'reference.png'
    Image.new('RGB',(64,88),'red').save(image)
    row = dict(id='ja:known-set-29',name='Gardevoir',set_id='known-set',set_name='Known Set',
        collector_number='29',printed_collector_number='029/055',language='ja',
        cardmarket_url=None,cardmarket_verified=False,verification='manual_visual',
        source_page='https://example.invalid/card',source_kind='independent_catalogue_not_official',
        image_url='https://example.invalid/image.png',reference_edition='1st Edition',
        source_file=str(image),sha256=hashlib.sha256(image.read_bytes()).hexdigest())
    yield conn,row
    conn.close()


def test_addition_preserves_existing_rows_and_pending_mapping(catalogue):
    conn,row = catalogue
    before = tuple(conn.execute('SELECT * FROM cards').fetchone())
    assert builder.insert_candidate_cards(conn,[row]) == {row['id']}
    assert tuple(conn.execute('SELECT * FROM cards WHERE id=?',('ja:existing-27',)).fetchone()) == before
    added = conn.execute('SELECT * FROM cards WHERE id=?',(row['id'],)).fetchone()
    assert added['cardmarket_url'] is None and added['cardmarket_id'] is None
    assert added['cardmarket_verified'] == 0
    assert added['printed_collector_number'] == '029/055'
    assert json.loads(added['variants_json'])['catalogue_reference']['edition_of_query_unconfirmed'] is True
    assert {r[0] for r in conn.execute('SELECT id FROM cards_fts')} == {row['id'],'ja:existing-27'}


@pytest.mark.parametrize('patch',[
    {'id':'ja:existing-27'}, {'id':'../unsafe'}, {'language':'en'},
    {'set_id':'missing-set','set_name':'Missing Set'}, {'set_id':'wrong-alias'},
    {'collector_number':'027','printed_collector_number':'27/055'},
    {'printed_collector_number':'030/055'}, {'collector_number':'029/056'},
    {'printed_collector_number':None}, {'verification':'not-reviewed'},
    {'source_kind':None}, {'source_kind':'test_query_photo'}, {'source_page':None},
    {'reference_edition':None}, {'cardmarket_url':'https://example.invalid/guess'},
    {'cardmarket_id':'guessed-id'}, {'cardmarket_verified':True}, {'sha256':'0'*64},
])
def test_reject_invalid_addition(catalogue,patch):
    conn,row = catalogue
    row.update(patch)
    with pytest.raises(ValueError):
        builder.insert_candidate_cards(conn,[row])
    assert conn.execute('SELECT count(*) FROM cards').fetchone()[0] == 1


def test_ambiguous_set_alias_rejected(catalogue):
    conn,row = catalogue
    conn.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES(?,?,?,?,?,?,?)',
        ('ja:other','ja:other','Other','conflicting-set','Known Set','31','ja'))
    with pytest.raises(ValueError,match='ambiguous'):
        builder.insert_candidate_cards(conn,[row])


def test_second_new_alias_of_same_number_rejected(catalogue):
    conn,row = catalogue
    builder.insert_candidate_cards(conn,[row])
    other = copy.deepcopy(row)
    other.update(id='ja:alternate-029',collector_number='029')
    with pytest.raises(ValueError,match='already represented'):
        builder.insert_candidate_cards(conn,[other])


def test_id_duplicate_rejected(catalogue):
    conn,row = catalogue
    builder.insert_candidate_cards(conn,[row])
    with pytest.raises(ValueError,match='duplicate'):
        builder.insert_candidate_cards(conn,[row])
