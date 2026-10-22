"""Background recognition uses the real pipeline without saving user results."""
import io
import logging
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.ocr import OcrResult
from app.recognition.pipeline import recognize_bytes
from app.recognition.stage1_check import CheckJob, Stage1Checker


@pytest.fixture
def recognition(tmp_path, monkeypatch):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test', 'now', 'now')")
    results.commit()
    catalog.execute(
        'INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) '
        'VALUES(?,?,?,?,?,?,?)', ('card', 'card', 'Pikachu', 'set', 'Set', '25', 'en'))
    catalog.commit()
    snapshot = SimpleNamespace(card_ids=np.array(['card']), embeddings=np.array([[1, 0]], dtype=np.float32))
    runtime = SimpleNamespace(
        require=lambda: (snapshot, SimpleNamespace(embed=lambda *a: np.array([1, 0], dtype=np.float32)),
                         SimpleNamespace(read=lambda image: OcrResult())),
        card_languages=np.array(['en']), printing_index=None, artwork_verifier=None,
        versions=lambda: dict(model_revision='test', catalogue='test', ocr='test', ranking='test'),
        threshold_config=lambda: {})
    image = Image.fromarray(np.random.default_rng(8).integers(0, 255, (825, 600, 3), dtype=np.uint8))
    payload = io.BytesIO()
    image.save(payload, format='JPEG')
    captures = []
    monkeypatch.setattr('app.recognition.pipeline.save_scan_capture',
                        lambda **kwargs: captures.append(kwargs['scan_id']))
    settings = Settings(_env_file=None, data_dir=tmp_path, use_ocr=False, use_grading=False,
                        store_captures=True)

    def run(data=None, **kwargs):
        return recognize_bytes(
            payload.getvalue() if data is None else data, settings=settings, runtime=runtime,
            catalog=catalog, session_id='test', skip_detect=True, language='en', **kwargs)

    try:
        yield SimpleNamespace(run=run, results=results, captures=captures, data=payload.getvalue())
    finally:
        catalog.close()
        results.close()


@pytest.mark.parametrize('with_results', [True, False])
def test_real_recognition_without_persistence_writes_no_scan_or_session(recognition, with_results, caplog):
    db = recognition.results
    changes = db.total_changes
    completions = []
    with caplog.at_level(logging.INFO, logger='scan.diagnostics'):
        result = recognition.run(
            results=db if with_results else None, persist=False,
            _grading_completion=lambda *args: completions.append(args))
    assert result.suggestions[0].card_id == 'card'
    assert db.execute('SELECT COUNT(*) FROM scans').fetchone()[0] == 0
    assert tuple(db.execute('SELECT * FROM sessions').fetchone()) == ('test', 'now', 'now')
    assert db.total_changes == changes
    assert recognition.captures == [] and completions == []
    assert not any(record.getMessage().startswith('scan_saved ') for record in caplog.records)


def test_real_recognition_still_persists_by_default(recognition):
    result = recognition.run(results=recognition.results)
    row = recognition.results.execute('SELECT id,session_id FROM scans').fetchone()
    assert tuple(row) == (result.id, 'test')
    assert recognition.captures == [result.id]


@pytest.mark.parametrize('agree', [True, False])
def test_background_check_with_real_recognition_logs_its_outcome(recognition, caplog, agree):
    card_id = 'card' if agree else 'different-card'
    checker = Stage1Checker()
    job = CheckJob('original-scan', card_id, recognition.data,
                   lambda data: recognition.run(data, results=None, persist=False))
    with caplog.at_level(logging.INFO, logger='scan.diagnostics'):
        assert checker.run_job(job) is agree
    expected = (f'stage1_check scan_id=original-scan stage1_card={card_id} '
                f'full_card=card agree={str(agree).lower()}')
    assert expected in [record.getMessage() for record in caplog.records]
    assert checker.checks == 1 and checker.disagreements == int(not agree)
    assert recognition.results.execute('SELECT COUNT(*) FROM scans').fetchone()[0] == 0
    assert recognition.captures == []
