"""The printing picker needs the same identity-filtered finishes as a scan."""

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.routes.cards import router
from app.routes.scans import router as scans_router


def test_card_detail_returns_only_identity_valid_finish_choices(tmp_path):
    catalog = connect(tmp_path / "catalog.sqlite")
    results = connect(tmp_path / "results.sqlite")
    init_catalog(catalog)
    init_results(results)
    prefix = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Scarlet-Violet/"
    normal, holo, wrong = (prefix + slug for slug in
                          ("Fuecoco-V1-SV036", "Fuecoco-V2-SV036", "Victini-V1-SV036"))
    try:
        catalog.execute("""INSERT INTO cards
            (id,provider_id,name,set_id,set_name,collector_number,language,cardmarket_url)
            VALUES ('en:sv01-036','sv01-036','Fuecoco','sv01','Scarlet & Violet','036','en',?)""", (normal,))
        catalog.executemany("""INSERT INTO cardmarket_expansion_products
            (url,expansion,name,source,page_url,card_id,matched,imported_at)
            VALUES (?,'Scarlet-Violet',?,'test',?,'en:sv01-036',1,'2026-10-01')""",
            [(normal, 'Fuecoco (SV 036)', normal), (holo, 'Fuecoco (SV 036)', holo),
             (wrong, 'Victini (SV 036)', wrong)])
        catalog.commit()
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.include_router(scans_router, prefix="/api/v1")
        app.state.settings = Settings(data_dir=tmp_path)
        app.state.dbs = SimpleNamespace(catalog=catalog, results=results)
        client = TestClient(app)
        response = client.get("/api/v1/cards/en%3Asv01-036")
        assert response.status_code == 200
        payload = response.json()
        assert payload['id'] == 'en:sv01-036'
        assert {item['url'] for item in payload['cardmarket_variants']} == {normal, holo}
        assert client.get('/api/v1/cards/nonexistent').status_code == 404
        session = client.get('/api/v1/session/results').json()['session_id']
        review = {'reason': 'printing_not_proven', 'candidate_group_id': 'test',
                  'plausible_printings': [{'card_id': payload['id'], 'name': payload['name'],
                    'set_name': payload['set_name'], 'collector_number': payload['collector_number'],
                    'language': 'en', 'image_url': ''}], 'guidance': 'Choose the printing.'}
        results.execute("""INSERT INTO scans
            (id,session_id,created_at,status,preprocessing,ocr_json)
            VALUES ('crop',?,'2026-10-01','printing_ambiguous','pad',?)""", (session, json.dumps({'printing_review': review})))
        results.commit()
        assert client.post('/api/v1/scans/crop/feedback', json={
            'action': 'confirm', 'card_id': payload['id'], 'printing_selected': True}).status_code == 409
        for url in (normal, holo):
            confirmed = client.post('/api/v1/scans/crop/feedback', json={
                'action': 'confirm', 'card_id': payload['id'], 'printing_selected': True,
                'cardmarket_url': url})
            assert confirmed.status_code == 200, confirmed.text
            saved = client.get('/api/v1/session/results').json()['results'][0]
            assert saved['confirmed_card_id'] == payload['id']
            assert saved['chosen_cardmarket_url'] == url
        assert client.post('/api/v1/scans/crop/feedback', json={
            'action': 'confirm', 'card_id': payload['id'], 'printing_selected': True,
            'cardmarket_url': wrong}).status_code == 409
        assert client.get('/api/v1/session/results').json()['results'][0]['chosen_cardmarket_url'] == holo
    finally:
        catalog.close()
        results.close()
