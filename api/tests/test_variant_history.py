import json
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.routes.scans import router
from app.schemas import RecognitionConfidence


@pytest.mark.parametrize('status', ['retake', 'no_match', 'failed'])
def test_abstentions_hide_guesses_but_allow_explicit_manual_correction(tmp_path, status):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.state.settings = Settings(data_dir=tmp_path)
    app.state.dbs = SimpleNamespace(catalog=catalog, results=results)
    try:
        client = TestClient(app)
        session = client.get('/api/v1/session/results').json()['session_id']
        ranking = [{'card_id': 'guess', 'name': 'Pikachu', 'set_name': 'Base Set',
                    'collector_number': '58', 'image_url': '', 'visual_score': .4,
                    'combined_score': .4}]
        results.execute('INSERT INTO scans (id,session_id,created_at,status,preprocessing,combined_ranking_json) VALUES (?,?,?,?,?,?)',
                        ('abstain', session, '2026-10-01', status, 'pad', json.dumps(ranking)))
        results.commit()
        saved = client.get('/api/v1/session/results').json()['results'][0]
        assert saved['suggestions'] == [] and saved['best_match'] is None
        assert saved['alternatives'] == [] and saved['match_state'] == 'unavailable'
        assert client.post('/api/v1/scans/abstain/feedback', json={
            'action': 'confirm', 'card_id': 'guess'}).status_code == 409
        catalog.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language) VALUES ('manual-printing','manual-printing','Pikachu','classic','Classic','014','en')")
        catalog.commit()
        assert client.post('/api/v1/scans/abstain/feedback', json={
            'action': 'correct', 'card_id': 'manual-printing'}).status_code == 200
        assert client.post('/api/v1/scans/abstain/feedback', json={
            'action': 'confirm', 'card_id': 'manual-printing'}).status_code == 200
        assert client.post('/api/v1/scans/abstain/feedback', json={
            'action': 'confirm', 'card_id': 'guess'}).status_code == 409
    finally:
        catalog.close()
        results.close()


def test_history_preserves_chosen_listing_and_session_isolation(tmp_path):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.state.settings = Settings(data_dir=tmp_path)
    app.state.dbs = SimpleNamespace(catalog=catalog, results=results)
    try:
        client = TestClient(app)
        session = client.get('/api/v1/session/results').json()['session_id']
        url = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/EX-Emerald/Whismur-V2-EM73'
        ranking = [{'card_id':'en:ex9-73', 'name':'Whismur', 'set_name':'EX Emerald',
                    'collector_number':'73', 'image_url':'', 'visual_score':.99,
                    'combined_score':.99, 'cardmarket_variants':[{'url':url,'label':'V2'}]}]
        results.execute('INSERT INTO scans (id,session_id,created_at,status,preprocessing,combined_ranking_json,confirmed_card_id,chosen_cardmarket_url) VALUES (?,?,?,?,?,?,?,?)',
                        ('chosen',session,'2026-10-01T14:00:00Z','uncertain','pad',json.dumps(ranking),'en:ex9-73',url))
        results.commit()
        response = client.get('/api/v1/session/results')
        assert response.status_code == 200
        saved = response.json()['results'][0]
        assert saved['chosen_cardmarket_url'] == url
        assert saved['confirmed_card_id'] == 'en:ex9-73'
        assert saved['suggestions'][0]['cardmarket_variants'][0]['url'] == url
        assert saved['best_match']['card_id'] == 'en:ex9-73'
        assert saved['best_match']['cardmarket_variants'][0]['url'] == url
        assert saved['match_state'] == 'likely'
        assert TestClient(app).get('/api/v1/session/results').json()['results'] == []
    finally:
        catalog.close()
        results.close()


def test_ambiguous_printing_requires_explicit_choice_and_survives_history(tmp_path):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.state.settings = Settings(data_dir=tmp_path)
    app.state.dbs = SimpleNamespace(catalog=catalog, results=results)
    try:
        client = TestClient(app)
        session = client.get('/api/v1/session/results').json()['session_id']
        review = {'reason': 'printing_not_proven', 'candidate_group_id': 'test',
                  'plausible_printings': [{'card_id': 'classic', 'name': 'Pikachu',
                    'set_name': 'Classic', 'collector_number': '014', 'language': 'en',
                    'image_url': ''}], 'guidance': 'Include the full card.'}
        confidence = RecognitionConfidence(identity='likely', printing='ambiguous',
            visual_similarity=.77).model_dump(mode='json')
        results.execute('INSERT INTO scans (id,session_id,created_at,status,preprocessing,ocr_json) VALUES (?,?,?,?,?,?)',
                        ('crop',session,'2026-10-01T14:00:00Z','printing_ambiguous','pad',
                         json.dumps({'printing_review': review, 'confidence':confidence})))
        results.commit()
        assert client.post('/api/v1/scans/crop/feedback', json={'action':'confirm','card_id':'classic'}).status_code == 409
        assert client.post('/api/v1/scans/crop/feedback', json={'action':'confirm','card_id':'unoffered','printing_selected':True}).status_code == 409
        catalog.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language) VALUES ('classic','classic','Pikachu','classic','Classic','014','en')")
        wrong_url = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu-BS58'
        catalog.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,cardmarket_url) VALUES ('base','base','Pikachu','base','Base Set','58','en',?)", (wrong_url,))
        catalog.commit()
        assert client.post('/api/v1/scans/crop/feedback', json={'action':'confirm','card_id':'classic',
            'printing_selected':True, 'cardmarket_url':wrong_url}).status_code == 409
        history = client.get('/api/v1/session/results').json()['results'][0]
        assert history['printing_review']['candidate_group_id'] == 'test'
        assert history['best_match']['card_id'] == 'classic'
        assert history['best_match']['visual_score'] is None
        assert history['match_state'] == 'tentative'
        assert history['confidence'] == confidence
        assert history['confirmed_card_id'] is None
        assert client.post('/api/v1/scans/crop/feedback', json={
            'action':'confirm','card_id':'classic','printing_selected':True}).status_code == 200
        assert client.get('/api/v1/session/results').json()['results'][0]['confirmed_card_id'] == 'classic'
    finally:
        catalog.close()
        results.close()
