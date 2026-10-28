import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.health import router


def test_health_vector_count_is_opt_in_and_uses_loaded_snapshot():
    catalog = sqlite3.connect(':memory:', check_same_thread=False)
    catalog.row_factory = sqlite3.Row
    catalog.execute('CREATE TABLE cards (language TEXT, has_image INTEGER)')
    catalog.executemany('INSERT INTO cards VALUES (?, ?)', [('en', 1), ('ja', 1), ('ja', 0)])
    app = FastAPI()
    app.include_router(router)
    settings = SimpleNamespace(health_vector_coverage=False, preprocess_config='pad', use_ocr=True,
                               snapshot_name='pad', catalogue_backend='sqlite', planetscale_import_id='')
    app.state.settings = settings
    app.state.dbs = SimpleNamespace(catalog=catalog)
    app.state.runtime = SimpleNamespace(snapshot=SimpleNamespace(indexed_count=1,
        catalogue_version='test', model_revision='test'), ready=True, error=None)
    client = TestClient(app)

    disabled = client.get('/health').json()['coverage']
    assert disabled['indexed'] == 2
    assert 'vectors' not in disabled
    assert 'with_images' not in disabled

    settings.health_vector_coverage = True
    enabled = client.get('/health').json()['coverage']
    assert enabled['indexed'] == 2
    assert enabled['with_images'] == 2
    assert enabled['vectors'] == 1

    app.state.runtime.snapshot = None
    app.state.runtime.ready = False
    missing = client.get('/health').json()
    assert missing['ready'] is False
    assert missing['coverage']['vectors'] is None
    catalog.close()
