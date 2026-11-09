"""RANK_FRACTION_CONFIRMED: a clean printed fraction keeps its card ahead of a same-name twin."""

from app.recognition.fraction_confirmed import fraction_confirmed_twin
from app.recognition.ocr import OcrHit


def card(cid, name, number, total, **extra):
    return {'card_id': cid, 'name': name, 'collector_number': number, 'set_total': total, **extra}


OAK_88 = card('en:base1-88', 'Professor Oak', '88', 102)
OAK_116 = card('en:base4-116', 'Professor Oak', '116', 130)
IMPOSTOR = card('en:base4-102', 'Impostor Professor Oak', '102', 130)


def hit(text, conf=0.96, region='collector'):
    return [OcrHit(text, conf, region)]


def test_fraction_keeps_the_original_over_the_verified_reprint():
    assert fraction_confirmed_twin([OAK_116, OAK_88, IMPOSTOR], 'en:base4-116', hit('88/102')) == 'en:base1-88'


def test_chosen_card_that_agrees_with_the_fraction_stays():
    assert fraction_confirmed_twin([OAK_116, OAK_88], 'en:base4-116', hit('116/130')) is None


def test_low_confidence_or_bare_number_or_other_region_changes_nothing():
    rows = [OAK_116, OAK_88]
    assert fraction_confirmed_twin(rows, 'en:base4-116', hit('88/102', conf=0.79)) is None
    assert fraction_confirmed_twin(rows, 'en:base4-116', hit('88')) is None
    assert fraction_confirmed_twin(rows, 'en:base4-116', hit('88/102', region='unknown')) is None
    assert fraction_confirmed_twin(rows, 'en:base4-116', []) is None


def test_a_different_card_matching_the_fraction_is_never_promoted():
    other = card('en:base1-88x', 'Gyarados', '88', 102)
    assert fraction_confirmed_twin([OAK_116, other], 'en:base4-116', hit('88/102')) is None


def test_two_confirmed_twins_are_ambiguous_and_change_nothing():
    twin = card('en:base1-88b', 'Professor Oak', '88', 102)
    assert fraction_confirmed_twin([OAK_116, OAK_88, twin], 'en:base4-116', hit('88/102')) is None


def test_same_name_across_languages_uses_the_english_title():
    ja = card('ja:DPt1-051', 'ギラティナ', '051', 96, view_title='Giratina')
    en = card('en:pl1-10', 'Giratina', '10', 127)
    assert fraction_confirmed_twin([en, ja], 'en:pl1-10', hit('051/096', 0.95)) == 'ja:DPt1-051'


def test_an_unprefixed_english_duplicate_counts_as_the_same_card():
    bare = card('base1-88', 'Professor Oak', '88', 102)
    assert fraction_confirmed_twin([OAK_116, bare, OAK_88], 'en:base4-116', hit('88/102')) == 'en:base1-88'


from app.recognition.fraction_confirmed import guard_fraction_total


def _texts(hits):
    return [(h.text, h.region, h.confidence) for h in hits]


def test_bare_total_beside_a_fraction_becomes_the_fraction():
    hits = [OcrHit('070', 0.92, 'collector'), OcrHit('074/070', None, 'unknown'), OcrHit('210', None, 'unknown')]
    assert _texts(guard_fraction_total(hits)) == [('074/070', 'collector', 0.92), ('210', 'unknown', None)]


def test_bare_number_that_is_not_a_total_stays():
    hits = [OcrHit('074', 0.92, 'collector'), OcrHit('074/070', None, 'unknown')]
    assert _texts(guard_fraction_total(hits)) == _texts(hits)


def test_fraction_whose_number_equals_its_total_does_not_count():
    hits = [OcrHit('070', 0.92, 'collector'), OcrHit('070/070', None, 'unknown')]
    assert _texts(guard_fraction_total(hits)) == _texts(hits)


def test_two_different_fractions_with_that_total_are_ambiguous():
    hits = [OcrHit('060', 0.9, 'collector'), OcrHit('015/060', None, 'unknown'), OcrHit('016/060', None, 'unknown')]
    assert _texts(guard_fraction_total(hits)) == _texts(hits)


def test_promo_and_non_collector_reads_are_left_alone():
    hits = [OcrHit('060', 0.9, 'holder_name'), OcrHit('015/060', None, 'unknown'), OcrHit('SM60', 0.9, 'collector')]
    assert _texts(guard_fraction_total(hits)) == _texts(hits)


def test_truncated_fraction_never_promotes_a_reprint_without_a_total():
    # Base Set Charizard read as "4/1": the 30th-anniversary reprint (no stored total) must not win.
    reprint = card('en:30th-c-001', 'Charizard', '001', None, printed_collector_number='4')
    base = card('en:base1-4', 'Charizard', '4', 102)
    assert fraction_confirmed_twin([reprint, base], 'en:base1-4', hit('4/1', 0.95)) is None
