import asyncio
from concurrent.futures import Future
import json
import sqlite3
from types import SimpleNamespace

from app.recognition.grading_completion import persist_grading, schedule_grading_completion, drain_grading_updates
from app.schemas import GradingEvidence


def database():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE scans(id TEXT,ocr_json TEXT,timings_json TEXT,confirmed_card_id TEXT)')
    db.execute('INSERT INTO scans VALUES(?,?,?,?)', ('s', json.dumps({'grading':{'grading_status':'pending'}, 'identity':'keep'}), '{"total_ms":100}', 'user-choice'))
    db.commit()
    return db


def test_late_grade_preserves_card_result_and_user_confirmation():
    db = database()
    evidence = GradingEvidence(company='psa', grade=10, certification_number='172943656', grading_status='graded')
    persist_grading(db, 's', evidence, 300)
    row = db.execute('SELECT * FROM scans').fetchone()
    assert json.loads(row[1])['grading']['certification_number'] == '172943656'
    assert json.loads(row[1])['identity'] == 'keep' and row[3] == 'user-choice'
    assert json.loads(row[2])['total_ms'] == 100
    persist_grading(db, 's', GradingEvidence(), 900)
    assert db.execute('SELECT ocr_json FROM scans').fetchone()[0] == row[1]


def test_async_completion_and_shutdown_drain():
    async def scenario():
        db = database(); future = Future()
        job = SimpleNamespace(future=future, elapsed_ms=500, stop=lambda:None)
        schedule_grading_completion(asyncio.get_running_loop(), db, 's', job)
        await asyncio.sleep(0)
        assert json.loads(db.execute('SELECT ocr_json FROM scans').fetchone()[0])['grading']['grading_status']=='pending'
        future.set_result(GradingEvidence(company='psa', grade=10, grading_status='graded'))
        await drain_grading_updates()
        assert json.loads(db.execute('SELECT ocr_json FROM scans').fetchone()[0])['grading']['grade']==10
    asyncio.run(scenario())


def test_failed_optional_grade_finishes_as_unknown():
    async def scenario():
        db = database()
        future = Future()
        stopped = []
        job = SimpleNamespace(future=future, elapsed_ms=100, stop=lambda: stopped.append(True))
        schedule_grading_completion(asyncio.get_running_loop(), db, 's', job)
        await asyncio.sleep(0)
        future.set_exception(RuntimeError('label reader unavailable'))
        await drain_grading_updates()
        saved = json.loads(db.execute('SELECT ocr_json FROM scans').fetchone()[0])
        assert saved['grading']['grading_status'] == 'unknown'
        assert saved['grading']['is_graded'] is None
        assert saved['identity'] == 'keep' and stopped == [True]
    asyncio.run(scenario())


def test_grading_endpoint_enforces_scan_ownership(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.db import connect, init_results
    from app.routes.scans import router

    db = connect(tmp_path / 'results.sqlite')
    init_results(db)
    db.executemany('INSERT INTO sessions(id,created_at,last_seen) VALUES(?,?,?)',
                   [('owner', 'now', 'now'), ('other', 'now', 'now')])
    db.execute("INSERT INTO scans(id,session_id,created_at,status,preprocessing,ocr_json) VALUES(?,?,?,?,?,?)",
               ('s', 'owner', 'now', 'matched', 'pad', json.dumps({'grading': {'grading_status': 'pending'}})))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.state.settings = Settings(_env_file=None)
    app.state.dbs = SimpleNamespace(results=db)
    with TestClient(app) as client:
        client.cookies.set(app.state.settings.session_cookie, 'other')
        assert client.get('/scans/s/grading').status_code == 403
        assert client.get('/scans/missing/grading').status_code == 404
        client.cookies.set(app.state.settings.session_cookie, 'owner')
        response = client.get('/scans/s/grading')
        assert response.status_code == 200
        assert response.json() == {'scan_id': 's', 'grading': {'grading_status': 'pending'}}
    db.close()
