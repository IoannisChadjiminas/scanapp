"""NUMBER_LED_LOOKUP: promo codes and confident bare numbers, with an agreeing name, propose cards."""

from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import OcrHit

ROWS = [
    {'id': 'en:bwp-BW53', 'name': 'Flygon', 'collector_number': 'BW53', 'language': 'en', 'set_id': 'bwp'},
    {'id': 'en:sm12-256', 'name': 'Flygon GX', 'collector_number': '256', 'language': 'en', 'set_id': 'sm12', 'set_total': 236},
    {'id': 'ja:DPP-048', 'name': 'ピカチュウ', 'collector_number': '048', 'language': 'ja', 'set_id': 'DPP'},
    {'id': 'ja:DP2-002', 'name': 'ピカチュウ', 'collector_number': '002', 'language': 'ja', 'set_id': 'DP2'},
    {'id': 'ja:XY2-048', 'name': 'リザードン', 'collector_number': '048', 'language': 'ja', 'set_id': 'XY2'},
]
INDEX = MetadataCandidateIndex(ROWS, indexed_ids={r['id'] for r in ROWS})


def test_promo_code_with_name_is_found_only_with_the_flag():
    numbers = [OcrHit('BW53', 0.9999, 'collector')]
    kw = dict(ocr_name='Flygon', name_confidence=0.9999, numbers=numbers, languages=('en',))
    assert INDEX.candidates(**kw) == []
    assert INDEX.candidates(**kw, promo_codes=True) == ['en:bwp-BW53']


def test_promo_code_with_a_name_that_disagrees_proposes_nothing():
    numbers = [OcrHit('BW53', 0.9999, 'collector')]
    assert INDEX.candidates(ocr_name='Garchomp', name_confidence=0.99, numbers=numbers,
                            languages=('en',), promo_codes=True) == []


def test_bare_number_with_agreeing_name_finds_the_promo():
    numbers = [OcrHit('048', 0.9998, 'collector')]
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=numbers,
                                        languages=('ja',)) == ['ja:DPP-048']


def test_bare_number_needs_high_confidence_name_and_language():
    weak = [OcrHit('048', 0.90, 'collector')]
    strong = [OcrHit('048', 0.9998, 'collector')]
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=weak, languages=('ja',)) == []
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.70, numbers=strong, languages=('ja',)) == []
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=strong, languages=('en',)) == []
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=strong, languages=()) == []


def test_bare_number_steps_aside_when_a_structured_read_exists():
    numbers = [OcrHit('048', 0.9998, 'collector'), OcrHit('048/090', 0.95, 'collector')]
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=numbers, languages=('ja',)) == []


def test_bare_number_with_a_large_family_proposes_nothing():
    rows = [{'id': f'ja:S{i}-048', 'name': 'ピカチュウ', 'collector_number': '048', 'language': 'ja', 'set_id': f'S{i}'} for i in range(4)]
    index = MetadataCandidateIndex(rows, indexed_ids={r['id'] for r in rows})
    assert index.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94,
                                        numbers=[OcrHit('048', 0.9998, 'collector')], languages=('ja',)) == []


def test_a_damage_number_that_names_nothing_does_not_hide_the_footer_number():
    numbers = [OcrHit('10', 0.9999, 'collector'), OcrHit('048', 0.9998, 'collector')]
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=numbers,
                                        languages=('ja',)) == ['ja:DPP-048']


def test_two_bare_numbers_that_both_name_cards_are_ambiguous():
    numbers = [OcrHit('002', 0.9999, 'collector'), OcrHit('048', 0.9998, 'collector')]
    assert INDEX.bare_number_candidates(ocr_name='ピカチュウ', name_confidence=0.94, numbers=numbers,
                                        languages=('ja',)) == []


def test_bare_number_never_displaces_title_candidates():
    # Base Set Charizard: its "100" damage read as a bare footer number named three other
    # Charizards numbered 100. The title lookup's cards (with Base Set #4) must stay.
    from app.recognition.metadata import bare_number_fallback
    title = ["base1-4", "en:base4-4"]
    assert bare_number_fallback(["en:ex15-100", "en:ex3-100", "en:xy2-100"], title) == title


def test_bare_number_is_used_when_the_title_lookup_is_empty():
    from app.recognition.metadata import bare_number_fallback
    assert bare_number_fallback(["en:dpp-DP48"], []) == ["en:dpp-DP48"]
    assert bare_number_fallback([], []) == []
