from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from types import SimpleNamespace

from PIL import Image
import pytest

from app.config import Settings
from app.recognition import pipeline
from app.recognition.grading_parallel import grading_requested
from app.recognition.ocr import CardOcr, OcrHit, OcrResult
from app.recognition.ocr_budget import title_only_allowed, title_only_confirmed
from app.recognition.ocr_cache import RequestOcrCache
from app.schemas import GradingEvidence, ScanStatus


@pytest.mark.parametrize('requires,graded,expected', [
    (False, None, True), (False, True, True), (False, False, False),
    (True, None, False), (True, True, True), (True, False, False)])
def test_client_hint_decides_grading(requires, graded, expected):
    settings = Settings(_env_file=None, grading_requires_client_hint=requires)
    assert grading_requested(settings, graded) is expected


def evaluation():
    response = SimpleNamespace(status=ScanStatus.uncertain, id='scan', versions={})
    saved = []
    item = pipeline._ScanEvaluation(response, {'total_ms': 1.}, Image.new('RGB', (60,90)),
        lambda: saved.append(response.grading.model_dump()), None, OcrResult(), [], ('en',), 0., False, {})
    return item, saved


def scan(monkeypatch, *, graded, requires=False):
    item, saved = evaluation()
    observed = {}
    def card(data, **kwargs):
        observed['observer'] = kwargs.get('_input_observer')
        if observed['observer'] is not None:
            observed['observer'](item.input_image)
            assert rt.grading_slots.acquire(timeout=2)
            rt.grading_slots.release()
        return item
    monkeypatch.setattr(pipeline, '_recognize_bytes_once', card)
    labels = []
    def grade(image):
        labels.append(image.size)
        return GradingEvidence(company='psa', grade=9, is_graded=True, grading_status='graded')
    serial = SimpleNamespace(read_grading=lambda image: pytest.fail('No serial grading'))
    with ThreadPoolExecutor(max_workers=1) as worker:
        rt = SimpleNamespace(ocr=serial, grading_ocr=SimpleNamespace(read_grading=grade),
            grading_executor=worker, grading_slots=BoundedSemaphore(1),
            require=lambda: (None, None, serial))
        result = pipeline.recognize_bytes(b'test', settings=Settings(_env_file=None,
            grading_at_card_deadline=True, grading_requires_client_hint=requires),
            runtime=rt, catalog=None, results=None, session_id='test',
            skip_detect=True, graded=graded)
    return result, observed, labels, saved


@pytest.mark.parametrize('graded,requires', [(False, False), (None, True), (False, True)])
def test_unrequested_grading_never_starts_label_ocr(monkeypatch, graded, requires):
    result, observed, labels, saved = scan(monkeypatch, graded=graded, requires=requires)
    assert observed['observer'] is None and labels == []
    assert result.grading.grading_status == 'ungraded' and result.grading.company is None
    assert result.grading.warnings == ['grading_not_requested']
    assert saved == [result.grading.model_dump()]


@pytest.mark.parametrize('graded,requires', [(None, False), (True, True)])
def test_requested_grading_keeps_the_parallel_label_read(monkeypatch, graded, requires):
    result, observed, labels, _ = scan(monkeypatch, graded=graded, requires=requires)
    assert observed['observer'] is not None and labels == [(60, 90)]
    assert result.grading.company == 'psa'


def test_title_only_read_runs_one_strip_and_no_footer_retries(monkeypatch):
    calls = []
    def run(self, image):
        calls.append(image.size)
        return ['Toxel'], [.99]
    monkeypatch.setattr(CardOcr, '_run', run)
    result = CardOcr.__new__(CardOcr).read(Image.new('RGB', (600, 840)), read_footer=False)
    assert len(calls) == 1 and calls[0][1] < 840 * .25
    assert result.footer_skipped and not result.collector_retry_used
    assert [h.region for h in result.hits] == ['name'] and result.collector_text is None


def test_default_read_still_reads_the_footer(monkeypatch):
    monkeypatch.setattr(CardOcr, '_run', lambda self, image: (['Toxel'], [.99]))
    result = CardOcr.__new__(CardOcr).read(Image.new('RGB', (600, 840)))
    assert not result.footer_skipped
    assert 'collector' in {p['region'] for p in result.passes}


def family(*rows):
    return [dict(id=card_id, set_id=set_id, set_name=set_id, collector_number=number,
                 language='en') for card_id, set_id, number in rows]


def allowed(*, members=(('first', 'swsh', '1'),), incomplete=False, visual=.90, runner=.70,
            art=.88, size=(600, 840)):
    return title_only_allowed(
        [dict(card_id='first', name='Toxel', visual_score=visual),
         dict(card_id='second', name='Other', visual_score=runner)],
        [SimpleNamespace(card_id='first', score=art)], family(*members),
        family_incomplete=incomplete, image_size=size)


def test_single_printing_with_agreeing_visual_streams_reads_title_only():
    assert allowed() is True
    # Provider aliases of one printing are still one printing.
    assert allowed(members=(('first', 'swsh', '1'), ('alias', 'swsh', '1'))) is True


@pytest.mark.parametrize('kwargs', [
    dict(members=(('first', 'swsh', '1'), ('reprint', 'cel', '1'))),
    dict(members=(('other', 'swsh', '1'),)), dict(members=()), dict(incomplete=True),
    dict(visual=.84), dict(runner=.83), dict(art=.79), dict(size=(800, 600))])
def test_reprints_or_weak_evidence_keep_the_footer(kwargs):
    assert allowed(**kwargs) is False


def title(name, confidence=.99):
    return OcrResult(name_text=name, hits=[OcrHit(name, confidence, 'name')], footer_skipped=True)


def test_title_only_needs_a_confident_agreeing_title():
    assert title_only_confirmed(title('Toxel'), 'Toxel')
    assert not title_only_confirmed(title('Toxel', .94), 'Toxel')
    assert not title_only_confirmed(title('Pikachu'), 'Toxel')
    assert not title_only_confirmed(OcrResult(failed=True), 'Toxel')


def test_cache_never_serves_a_title_only_read_as_complete_evidence():
    reads = []
    def read(image, **options):
        reads.append(options)
        return OcrResult(name_text='Toxel', footer_skipped=not options.get('read_footer', True))
    engine = SimpleNamespace(read=read)
    cache, image = RequestOcrCache(), Image.new('RGB', (60, 84))
    assert cache.read(engine, image, read_footer=False)[0].footer_skipped
    complete, cached = cache.read(engine, image)
    assert not complete.footer_skipped and not cached
    # A complete read satisfies a later title-only request without rereading.
    again, cached = cache.read(engine, image, read_footer=False)
    assert cached and not again.footer_skipped and len(reads) == 2


def run_pipeline(tmp_path, monkeypatch, *, title, members):
    import io
    import numpy as np
    from app.db import connect, init_catalog, init_results
    catalog = connect(tmp_path/'catalog.sqlite'); results = connect(tmp_path/'results.sqlite')
    init_catalog(catalog); init_results(results)
    results.execute("INSERT INTO sessions VALUES('test','test','test')")
    for cid, name, number in [('first', 'Toxel', '078/185'), ('second', 'Other card', '079/185')]:
        catalog.execute('INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES(?,?,?,?,?,?,?)',
                        (cid, cid, name, 'viv', 'Vivid Voltage', number, 'en'))
    catalog.commit()
    regions = []; reader = CardOcr.__new__(CardOcr)
    def read(image):
        regions.append(image.size)
        return ([title], [.99]) if len(regions) == 1 else (['078/185'], [.99])
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
    printings = SimpleNamespace(family=lambda catalog, top: (
        [{**top, 'id': top['card_id'], **row} for row in members], False))
    runtime = SimpleNamespace(require=lambda: (snapshot, None, reader), artwork_index=artwork,
        artwork_verifier=None, printing_index=printings,
        versions=lambda: dict(ocr='test', ranking='test', model_revision='test', catalogue='test'),
        threshold_config=lambda: {})
    image = Image.fromarray(np.random.default_rng(9).integers(0, 255, (840, 600, 3), dtype=np.uint8))
    buffer = io.BytesIO(); image.save(buffer, format='JPEG')
    try:
        response = pipeline.recognize_bytes(buffer.getvalue(), settings=Settings(_env_file=None,
            data_dir=tmp_path, store_captures=False, use_grading=False, enable_matched=True,
            ocr_adaptive_footer=True, ocr_title_only_single_printing=True), runtime=runtime,
            catalog=catalog, results=results, session_id='test', skip_detect=True)
    finally:
        catalog.close(); results.close()
    return response, regions


def test_pipeline_reads_only_the_title_for_a_lone_printing(tmp_path, monkeypatch):
    response, regions = run_pipeline(tmp_path, monkeypatch, title='Toxel', members=[{}])
    assert len(regions) == 1 and response.best_match.card_id == 'first'
    assert response.timings_ms['ocr_footer_skipped'] == 1.
    assert 'footer_ocr_skipped_single_printing' in response.confidence.reasons
    assert response.ocr.collector_text is None


def test_pipeline_reads_the_footer_when_the_title_disagrees(tmp_path, monkeypatch):
    response, regions = run_pipeline(tmp_path, monkeypatch, title='Pikachu', members=[{}])
    # Title-only probe, then the complete read: title plus footer.
    assert len(regions) == 3 and response.timings_ms['ocr_footer_skipped'] == 0.
    assert response.ocr.collector_text == '078/185'


def test_pipeline_reads_the_footer_for_same_art_reprints(tmp_path, monkeypatch):
    response, regions = run_pipeline(tmp_path, monkeypatch, title='Toxel',
        members=[{}, dict(id='reprint', set_id='cel', set_name='Celebrations')])
    assert len(regions) == 2 and response.timings_ms['ocr_footer_skipped'] == 0.


def test_label_text_seen_by_card_ocr_overrides_a_missing_hint(monkeypatch):
    item, saved = evaluation()
    item.ocr = OcrResult(hits=[OcrHit('PSA 10', .99, 'holder_name')])
    monkeypatch.setattr(pipeline, '_recognize_bytes_once', lambda data, **kwargs: item)
    labels = []
    def grade(image):
        labels.append(image.size)
        return GradingEvidence(company='psa', grade=10, is_graded=True, grading_status='graded')
    card = SimpleNamespace(read_grading=grade)
    rt = SimpleNamespace(ocr=card, require=lambda: (None, None, card))
    result = pipeline.recognize_bytes(b'test', settings=Settings(_env_file=None),
        runtime=rt, catalog=None, results=None, session_id='test', skip_detect=True, graded=False)
    assert labels == [(60, 90)] and result.grading.company == 'psa'
    assert result.timings_ms['grading_safety_net'] == 1.


def test_no_label_text_keeps_grading_skipped(monkeypatch):
    item, _ = evaluation()
    monkeypatch.setattr(pipeline, '_recognize_bytes_once', lambda data, **kwargs: item)
    card = SimpleNamespace(read_grading=lambda image: pytest.fail('Must not read the label'))
    rt = SimpleNamespace(ocr=card, require=lambda: (None, None, card))
    result = pipeline.recognize_bytes(b'test', settings=Settings(_env_file=None),
        runtime=rt, catalog=None, results=None, session_id='test', skip_detect=True, graded=False)
    assert result.grading.warnings == ['grading_not_requested']
