import io
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings, get_settings
from app.db import connect, init_catalog, init_results
from app.recognition import rank
from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.pipeline import recognize_bytes


@pytest.mark.parametrize("on,expected", [(False, "retake"), (True, "uncertain")])
def test_unknown_footer_prefix_no_longer_turns_the_right_card_into_a_retake(tmp_path, monkeypatch, on, expected):
    # Android, Exeggutor 135/132: the outline was not verified and the footer read "KNE2" next to
    # the real number. KNE2 counted as a contradicting set code, vetoed the name+number review and
    # the scan became a retake. With the switch it is noise, and the card stays as a suggestion.
    monkeypatch.setattr(get_settings(), "ocr_known_set_prefixes", on)
    monkeypatch.setattr(rank, "_active_prefixes", None)
    monkeypatch.setattr(rank, "_collector_prefixes", {})
    monkeypatch.setattr('app.recognition.pipeline.detect_and_rectify', lambda im: (im, False))
    monkeypatch.setattr('app.recognition.pipeline.card_frame_candidates', lambda *a, **k: [])
    monkeypatch.setattr('app.recognition.pipeline.loose_frame_candidates', lambda *a, **k: [])
    image = Image.fromarray(np.random.default_rng(11).integers(0, 255, (800, 600, 3), dtype=np.uint8))
    catalog, results = connect(tmp_path/'catalog.sqlite'), connect(tmp_path/'results.sqlite')
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    catalog.executemany('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,'
                        'printed_collector_number,language) VALUES(?,?,?,?,?,?,?,?)', [
        ('en:gym2-135', 'en:gym2-135', 'Exeggutor', 'gym2', 'Gym Challenge', '135', '135/132', 'en'),
        ('en:sv-tg05', 'en:sv-tg05', 'Pikachu', 'tg', 'Trainer Gallery', 'TG05', 'TG05/TG30', 'en')])
    catalog.commit()
    snapshot = SimpleNamespace(card_ids=np.array(['en:gym2-135']),
                               embeddings=np.array([[.73, np.sqrt(1-.73**2)]], dtype=np.float32))
    ocr = OcrResult(name_text='Exeggutor', collector_text='135/132', lines=['Exeggutor', 'KNE2', '135/132'],
                    hits=[OcrHit('Exeggutor', .99, 'name'), OcrHit('KNE2', .95, 'collector'),
                          OcrHit('135/132', .99, 'collector')])
    runtime = SimpleNamespace(require=lambda: (snapshot,
        SimpleNamespace(embed=lambda *a: np.array([1, 0], dtype=np.float32)),
        SimpleNamespace(read=lambda im: ocr)), card_languages=np.array(['en']),
        printing_index=None, artwork_verifier=SimpleNamespace(verify=lambda *a: []),
        versions=lambda: dict(model_revision='test', catalogue='test', ocr='test', ranking='test'),
        threshold_config=lambda: {})
    payload = io.BytesIO()
    image.save(payload, format='JPEG')
    try:
        response = recognize_bytes(payload.getvalue(), settings=Settings(
            _env_file=None, data_dir=tmp_path, enable_matched=True, store_captures=False,
            ocr_known_set_prefixes=on), runtime=runtime, catalog=catalog, results=results,
            session_id='test', language='en')
        assert response.status.value == expected
        if on:
            assert response.suggestions[0].card_id == 'en:gym2-135'
            assert response.status.value != 'matched'  # still needs the collector's confirmation
    finally:
        catalog.close()
        results.close()
