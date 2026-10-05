from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import OcrHit


def index():
    rows = [dict(id='original', name='Lugia V', collector_number='186',
                 printed_collector_number='186/195', language='en'),
            dict(id='reprint', name='Lugia V', collector_number='050',
                 printed_collector_number='186/195', language='en'),
            dict(id='foreign', name='Lugia V', collector_number='186',
                 printed_collector_number='186/195', language='ja'),
            dict(id='different', name='Pikachu', collector_number='186',
                 printed_collector_number='186/195', language='en'),
            dict(id='missing-vector', name='Lugia V', collector_number='186',
                 printed_collector_number='186/195', language='en')]
    return MetadataCandidateIndex(rows, indexed_ids={r['id'] for r in rows[:-1]})


def query(**kwargs):
    args = dict(ocr_name='Lugia V', name_confidence=.99,
                numbers=[OcrHit('186/195', .99, 'collector')], languages=('en',))
    args.update(kwargs)
    return index().candidates(**args)


def test_metadata_proposes_all_matching_printings_not_only_original():
    assert query() == ['original', 'reprint']


def test_unknown_language_preserves_foreign_candidates_for_review():
    assert query(languages=()) == ['foreign', 'original', 'reprint']


def test_metadata_does_not_guess_missing_or_weak_or_unknown_region_identity():
    assert query(ocr_name=None) == []
    assert query(name_confidence=.84) == []
    for hit in [OcrHit('186', .99, 'collector'), OcrHit('186/195', .84, 'collector'),
                OcrHit('186/195', .99, 'unknown')]:
        assert query(numbers=[hit]) == []


def test_contradictory_visible_denominators_veto_metadata_retrieval():
    assert query(numbers=[OcrHit('186/195', .99, 'collector'),
                          OcrHit('186/198', .99, 'collector')]) == []


def test_metadata_bound_never_silently_selects_one_printing():
    assert query(limit=1) == []
