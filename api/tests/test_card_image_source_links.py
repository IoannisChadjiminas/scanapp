import sqlite3
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse,RedirectResponse
from app.routes.cards import card_image

def request(path,url,has_image=1):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE cards(id TEXT,image_path TEXT,has_image INTEGER,remote_image_url TEXT)')
    db.execute('INSERT INTO cards VALUES (?,?,?,?)',('en:test',str(path),has_image,url))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dbs=SimpleNamespace(catalog=db))))

def test_feature_only_reference_links_to_observed_https_source(tmp_path):
    response=card_image('en:test',request(tmp_path/'private-original.jpg','https://pkmncards.com/wp-content/uploads/h01.jpg'))
    assert isinstance(response,RedirectResponse) and response.status_code==307
    assert response.headers['location']=='https://pkmncards.com/wp-content/uploads/h01.jpg'
    assert not (tmp_path/'private-original.jpg').exists()

def test_existing_local_reference_keeps_file_response(tmp_path):
    path=tmp_path/'existing.webp';path.write_bytes(b'unchanged')
    response=card_image('en:test',request(path,'https://example.com/source.jpg'))
    assert isinstance(response,FileResponse) and response.path==path

@pytest.mark.parametrize('url',['http://example.com/card.jpg','https:///card.jpg','', 'https://example.com/\r\ncard.jpg'])
def test_missing_reference_does_not_redirect_to_invalid_source(tmp_path,url):
    with pytest.raises(HTTPException) as e:card_image('en:test',request(tmp_path/'missing.jpg',url))
    assert e.value.status_code==404

def test_unindexed_reference_remains_missing(tmp_path):
    with pytest.raises(HTTPException):card_image('en:test',request(tmp_path/'missing.jpg','https://example.com/source.jpg',0))
