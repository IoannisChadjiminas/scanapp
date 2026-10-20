"""The phone's card text may only let the server skip optional re-reads, never pick a card."""
import io
import json
import logging
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.config import Settings
from app.recognition import pipeline
from app.recognition.client_text import (ClientText, fast_path_decision, parse_client_text,
                                         server_read_agrees)
from app.recognition.ocr import CardOcr, OcrHit, OcrResult
from app.recognition.ocr_cache import RequestOcrCache
from app.routes.health import scan_price_config


def payload(**changes):
    body = dict(v=1, engine='apple-vision', name='Toxel', name_conf=.98, number='078/185',
                number_conf=.97, ms=120)
    body.update(changes)
    return json.dumps({k: v for k, v in body.items() if v is not ...})


def test_a_complete_hint_is_read_and_normalised():
    hint, reason = parse_client_text(payload(number='TG01/TG30'))
    assert reason == 'ok' and hint == ClientText('apple-vision', 'Toxel', .98, 'TG01/30', .97, 120)
    assert parse_client_text(payload(number='SVP 045'))[0].number == 'SVP045'
    assert parse_client_text(payload(name=None, name_conf=None))[0].name is None
    assert parse_client_text(payload(name='ピカチュウ'))[0].name == 'ピカチュウ'


@pytest.mark.parametrize('raw,reason', [
    (None, 'absent'), ('', 'absent'), ('not json', 'not_json'), ('[1]', 'not_object'),
    (payload(extra=1), 'unknown_keys'), (payload(v=2), 'bad_version'), (payload(v=True), 'bad_version'),
    (payload(engine='Apple Vision'), 'bad_engine'), (payload(engine=None), 'bad_engine'),
    (payload(name='x' * 65), 'bad_name'), (payload(name='12/34'), 'bad_name'),
    (payload(name='Tox\nel'), 'bad_name'), (payload(name=7), 'bad_name'),
    (payload(number='HP 120 ATTACK'), 'bad_number'), (payload(number='1/2/3'), 'bad_number'),
    (payload(number=45), 'bad_number'), (payload(name_conf=1.5), 'bad_confidence'),
    (payload(number_conf=True), 'bad_confidence'), (payload(name_conf='high'), 'bad_confidence'),
    ('{"v":1,"engine":"x","name_conf":NaN,"name":"Toxel"}', 'bad_confidence'),
    (payload(ms=-1), 'bad_ms'), (payload(name=None, number=None), 'empty'),
    (payload(name='Toxel' + ' ' * 600), 'too_long'),
])
def test_malformed_hints_are_dropped_with_a_reason(raw, reason):
    assert parse_client_text(raw) == (None, reason)


class Catalog:
    """Same-name rows the printing check reads."""
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        name, language = params
        return SimpleNamespace(fetchall=lambda: [r for r in self.rows
                                                 if r['name'] == name and r['language'] == language])


def card(card_id, number, set_id='viv', name='Toxel', printed=''):
    return dict(id=card_id, card_id=card_id, name=name, set_id=set_id, set_name=set_id,
                collector_number=number, printed_collector_number=printed, language='en',
                set_total=185)


def decide(hint=None, *, visual=.90, runner=.70, art=.88, size=(600, 840), rows=None, lead=None,
           extra=()):
    hint = hint or parse_client_text(payload())[0]
    lead = lead or card('first', '78')
    return fast_path_decision(hint, [dict(card_id='first', name='Toxel', visual_score=visual, language='en'),
                                     *extra,
                                     dict(card_id='second', name='Other', visual_score=runner, language='en')],
        lead, [SimpleNamespace(card_id='first', score=art)], Catalog(rows or [lead]),
        image_size=size, min_confidence=.9)


def test_a_hint_that_confirms_a_clear_lone_printing_is_eligible():
    assert decide() == (True, 'eligible')
    # A same-number alias of the one printing is still one printing.
    assert decide(rows=[card('first', '78'), card('alias', '78')]) == (True, 'eligible')


@pytest.mark.parametrize('kwargs,reason', [
    (dict(hint=ClientText('x', 'Toxel', .99, None, None)), 'incomplete'),
    (dict(hint=ClientText('x', 'Toxel', .89, '078/185', .99)), 'low_confidence'),
    (dict(hint=ClientText('x', 'Toxel', .99, '078/185', None)), 'low_confidence'),
    (dict(size=(840, 600)), 'frame_shape'), (dict(visual=.84), 'visual_margin'),
    (dict(runner=.83), 'visual_margin'), (dict(art=.79), 'artwork'),
    (dict(hint=ClientText('x', 'Pikachu', .99, '078/185', .99)), 'name_disagrees'),
    (dict(hint=ClientText('x', 'Toxel', .99, '079/185', .99)), 'number_disagrees'),
    (dict(hint=ClientText('x', 'Toxel', .99, '078/186', .99), lead=card('first', '78', printed='078/185')),
     'number_disagrees'),
    (dict(rows=[card('first', '78'), card('reprint', '78', set_id='cel')]), 'printings'),
])
def test_any_doubt_keeps_the_full_path(kwargs, reason):
    assert decide(**kwargs) == (False, reason)


def test_the_margin_is_to_another_card_in_the_leader_s_language():
    alias = dict(card_id='en:first', name='Toxel', visual_score=.90, language='en')
    assert decide(extra=[alias]) == (True, 'eligible')
    japanese = dict(card_id='ja:S1-001', name='エレズン', visual_score=.89, language='ja')
    # The same art in Japanese is a near tie that only the server's own title read may settle.
    assert decide(extra=[japanese]) == (True, 'eligible_title_required')
    assert decide(extra=[dict(japanese, visual_score=.80)]) == (True, 'eligible')
    assert decide(extra=[dict(japanese, language='en', name='Other')]) == (False, 'visual_margin')


def test_no_hint_means_no_fast_path():
    assert fast_path_decision(None, [], None, [], None, image_size=(600, 840),
                              min_confidence=.9) == (False, 'no_hint')


def read(name='Toxel', confidence=.99, number=None, number_confidence=.99):
    return OcrResult(name_text=name, hits=([OcrHit(name, confidence, 'name')] if name else [])
        + ([OcrHit(number, number_confidence, 'collector')] if number else []))


def test_the_server_read_must_not_contradict_the_phone():
    hint = ClientText('x', 'Toxel', .99, '078/185', .99)
    assert server_read_agrees(hint, read())
    assert server_read_agrees(hint, read(number='078/185'))
    assert server_read_agrees(hint, read(name=None))           # a missing title is no conflict
    assert server_read_agrees(hint, read('Pikachu', .40))      # neither is a weak one
    assert not server_read_agrees(hint, read('Pikachu'))
    assert not server_read_agrees(hint, read(number='079/185'))
    assert not server_read_agrees(hint, OcrResult(failed=True))
    assert server_read_agrees(hint, read(), require_title=True)
    assert not server_read_agrees(hint, read(name=None), require_title=True)
    assert not server_read_agrees(hint, read(confidence=.80), require_title=True)


def engine_reads(monkeypatch, gate):
    calls = []
    def run(self, image):
        calls.append(image.size)
        return (['Toxel'], [.99]) if len(calls) == 1 else (['retreat'], [.97])
    monkeypatch.setattr(CardOcr, '_run', run)
    result = CardOcr.__new__(CardOcr).read(Image.new('RGB', (600, 840)), optional_retry_gate=gate)
    return result, calls


def test_an_agreeing_gate_leaves_out_the_footer_retries_and_marks_the_printing_unconfirmed(monkeypatch):
    result, calls = engine_reads(monkeypatch, lambda ocr: True)
    assert len(calls) == 2 and result.client_text_gate is True
    assert result.collector_retry_skipped and not result.collector_retry_used
    assert [h.text for h in result.hits] == ['Toxel', 'retreat']


@pytest.mark.parametrize('gate', [lambda ocr: False, lambda ocr: 1 / 0])
def test_a_disagreeing_or_failing_gate_runs_every_retry(monkeypatch, gate):
    result, calls = engine_reads(monkeypatch, gate)
    assert len(calls) == 4 and result.client_text_gate is False
    assert result.collector_retry_used and not result.collector_retry_skipped


def test_the_gate_skips_a_weak_header_retry_too(monkeypatch):
    calls = []
    def run(self, image):
        calls.append(image.size)
        # The footer strip of this small card is 152 px high once enlarged.
        return (['Toxel'], [.70]) if image.height != 152 else (['078/185'], [.99])
    monkeypatch.setattr(CardOcr, '_run', run)
    reader = CardOcr.__new__(CardOcr)
    reader.read(Image.new('RGB', (300, 420)), optional_retry_gate=lambda ocr: True)
    assert len(calls) == 2
    reader.read(Image.new('RGB', (300, 420)))
    assert len(calls) == 5  # title, footer, then the weak-header re-read


def test_cache_never_serves_a_fast_path_read_as_complete_evidence():
    reads = []
    def read_image(image, **options):
        reads.append(options)
        return OcrResult(name_text='Toxel', collector_retry_skipped='optional_retry_gate' in options)
    engine, cache, image = SimpleNamespace(read=read_image), RequestOcrCache(), Image.new('RGB', (60, 84))
    assert cache.read(engine, image, optional_retry_gate=lambda ocr: True)[0].collector_retry_skipped
    complete, cached = cache.read(engine, image)
    assert not complete.collector_retry_skipped and not cached
    again, cached = cache.read(engine, image, optional_retry_gate=lambda ocr: True)
    assert cached and not again.collector_retry_skipped and len(reads) == 2


def run_pipeline(tmp_path, monkeypatch, *, hint, fast_path=True, rows=(('first', 'Toxel', '078/185'),)):
    from app.db import connect, init_catalog, init_results
    catalog = connect(tmp_path/'catalog.sqlite'); results = connect(tmp_path/'results.sqlite')
    init_catalog(catalog); init_results(results)
    results.execute("INSERT INTO sessions VALUES('test','test','test')")
    for cid, name, number in [*rows, ('second', 'Other card', '079/185')]:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES(?,?,?,?,?,?,?)',
                        (cid, cid, name, 'viv' if cid != 'reprint' else 'cel', 'Vivid Voltage', number, 'en'))
    catalog.commit()
    regions = []; reader = CardOcr.__new__(CardOcr)
    def read(image):
        regions.append(image.size)
        # The footer strip holds no readable number, so the footer retries are due.
        return (['Toxel'], [.99]) if len(regions) == 1 else (['weakness'], [.99])
    reader._run = read
    def oriented(image, *args, **kwargs):
        kwargs['query_vectors'][id(image)] = np.array([1., 0.], dtype=np.float32)
        kwargs['selection_metadata'].update(profile='primary')
        return image, np.array([0, 1]), np.array([.90, .70]), {'orientation_degrees': 0.}
    monkeypatch.setattr(pipeline, 'retrieve_oriented', oriented)
    snapshot = SimpleNamespace(card_ids=np.array(['first', 'second']),
        embeddings=np.array([[1., 0.], [0., 1.]], dtype=np.float32))
    artwork = SimpleNamespace(search=lambda *a, **k: ([SimpleNamespace(card_id='first', score=.88,
        reference_profile='conventional_window', query_profile='as_supplied')], {}))
    runtime = SimpleNamespace(require=lambda: (snapshot, None, reader), artwork_index=artwork,
        artwork_verifier=None, printing_index=None,
        versions=lambda: dict(ocr='test', ranking='test', model_revision='test', catalogue='test'),
        threshold_config=lambda: {})
    image = Image.fromarray(np.random.default_rng(9).integers(0, 255, (840, 600, 3), dtype=np.uint8))
    buffer = io.BytesIO(); image.save(buffer, format='JPEG')
    parsed, reason = parse_client_text(hint)
    try:
        response = pipeline.recognize_bytes(buffer.getvalue(), settings=Settings(_env_file=None,
            data_dir=tmp_path, store_captures=False, use_grading=False, enable_matched=True,
            client_text_hints=True, client_text_fast_path=fast_path), runtime=runtime,
            catalog=catalog, results=results, session_id='test', skip_detect=True,
            client_text=parsed, client_text_reason=reason)
        saved = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0])
    finally:
        catalog.close(); results.close()
    return response, regions, saved


def test_pipeline_skips_the_footer_retries_when_the_phone_confirms_the_leader(tmp_path, monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger='scan.diagnostics'):
        response, regions, saved = run_pipeline(tmp_path, monkeypatch, hint=payload())
    assert len(regions) == 2 and response.best_match.card_id == 'first'
    assert response.timings_ms['client_text_fast_path'] == 1.
    assert response.ocr.collector_retry_skipped and response.status.value != 'matched'
    assert saved['client_text']['fast_path'] == 'used'
    assert saved['frame_selection']['client_text_fast_path'] == 'eligible'
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith('client_text '))
    assert 'fast_path=used' in line and 'top_name_agrees=true' in line and 'Toxel' not in line


@pytest.mark.parametrize('kwargs,reason', [
    (dict(hint=payload(number='079/185')), 'number_disagrees'),
    (dict(hint=payload(name='Pikachu')), 'name_disagrees'),
    (dict(hint=payload(name_conf=.5)), 'low_confidence'),
    (dict(hint=payload(), rows=(('first', 'Toxel', '078/185'), ('reprint', 'Toxel', '078/185'))), 'printings'),
])
def test_pipeline_runs_the_full_read_on_any_doubt(tmp_path, monkeypatch, kwargs, reason):
    response, regions, saved = run_pipeline(tmp_path, monkeypatch, **kwargs)
    assert len(regions) == 4 and response.timings_ms['client_text_fast_path'] == 0.
    assert saved['frame_selection']['client_text_fast_path'] == reason
    assert not response.ocr.collector_retry_skipped


def test_with_the_fast_path_off_the_hint_is_only_logged(tmp_path, monkeypatch):
    response, regions, saved = run_pipeline(tmp_path, monkeypatch, hint=payload(), fast_path=False)
    assert len(regions) == 4 and 'client_text_fast_path' not in response.timings_ms
    assert saved['client_text']['fast_path'] == 'off'


def test_config_tells_the_phone_whether_to_send_client_text():
    assert scan_price_config(Settings(_env_file=None)).client_text is False
    assert scan_price_config(Settings(_env_file=None, app_client_text=True)).client_text is True
