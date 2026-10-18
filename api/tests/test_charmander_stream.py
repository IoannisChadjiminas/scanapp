"""Preview/final regression using the saved Charmander recognition evidence."""
import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.pipeline import recognize_bytes


def test_charmander_preview_and_final_agree_despite_dropped_footer_digits(tmp_path):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    ids = ['en:swsh4-23', 'en:2015xy-3']
    scores = [.818983793258667, .7995504140853882]
    try:
        for cid, name, set_id, number, total in [
            (ids[0], 'Charmander', 'swsh4', '23', 185),
            (ids[1], 'Torchic', '2015xy', '3', 12),
        ]:
            catalog.execute('INSERT INTO cards '
                '(id,provider_id,name,set_id,set_name,collector_number,language) '
                'VALUES (?,?,?,?,?,?,?)', (cid, cid, name, set_id, set_id, number, 'en'))
            catalog.execute('INSERT INTO set_totals VALUES (?,?,?,?)', ('en', set_id, total, 'test'))
        catalog.commit()
        snapshot = SimpleNamespace(card_ids=np.array(ids), embeddings=np.array(
            [[s, np.sqrt(1-s*s)] for s in scores], dtype=np.float32))
        observed = OcrResult(name_text='Charmander', collector_text='3/185',
            lines=['Charmander', '3/185'],
            hits=[OcrHit('Charmander', .99995, 'name'), OcrHit('3/185', .99962, 'collector')])
        runtime = SimpleNamespace(require=lambda: (snapshot,
            SimpleNamespace(embed=lambda *args: np.array([1, 0], dtype=np.float32)),
            SimpleNamespace(read=lambda image: observed)), card_languages=np.array(['en', 'en']),
            printing_index=None, artwork_verifier=None,
            versions=lambda: dict(model_revision='test', catalogue='test', ocr='test', ranking='test'),
            threshold_config=lambda: {})
        image = Image.fromarray(np.random.default_rng(42).integers(0, 255, (825, 600, 3), dtype=np.uint8))
        payload = io.BytesIO()
        image.save(payload, format='JPEG')
        previews = []
        response = recognize_bytes(payload.getvalue(), settings=Settings(_env_file=None,
            data_dir=tmp_path, store_captures=False, enable_matched=True), runtime=runtime,
            catalog=catalog, results=results, session_id='test', skip_detect=True,
            language='en', graded=False, _progress_observer=previews.append)
        assert previews[0]['candidates'][0]['card_id'] == ids[0]
        assert response.suggestions[0].card_id == response.best_match.card_id == ids[0]
        assert response.status == 'uncertain'
        assert response.match_state == 'tentative'
        saved = results.execute('SELECT ocr_json FROM scans WHERE id=?', (response.id,)).fetchone()
        evidence = json.loads(saved[0])
        assert evidence['collector_text'] == '3/185'
        assert evidence['match_presentation']['best_match']['card_id'] == ids[0]
    finally:
        catalog.close()
        results.close()
