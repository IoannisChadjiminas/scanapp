"""OCR_PRINTING_FROM_TEXT, the number alone: the printing the phone's own footer number names
orders an ambiguous result when its text has no name.

The Redmi round of 6 November 2026 (pokesingle, phone-first-results-2026-11-06-redmi-ppocr-band):
the phone's PP-OCR read `9/108` on an Evolutions Charmander and sent it with no name; the
server's own OCR read `3`, the picture could not tell the Evolutions reprint from Base Set 46
of the same art, and Base Set went first. `_text_named_card` needs the name, so the number
goes through the footer fraction rule against the ambiguous printings instead. It only
orders: the status stays printing_ambiguous.
"""
from types import SimpleNamespace

from app.recognition.pipeline import _hint_number_named_printing


def _row(card_id, number, total=None, **extra):
    return {'card_id': card_id, 'name': 'Charmander', 'collector_number': number, 'set_total': total,
            'language': 'en', **extra}


# The stored staging top 3 of scan bd643ddd (6 November 2026): Base Set first, Evolutions third.
BASE = _row('base1-46', '46', 102)
BASE_EN = _row('en:base1-46', '46', 102)
EVOLUTIONS = _row('en:xy12-9', '9', 108)
RANKED = [BASE, BASE_EN, EVOLUTIONS]
MEMBERS = [BASE, EVOLUTIONS]


def _text(number, conf=.966, name=None):
    return SimpleNamespace(name=name, number=number, number_conf=conf)


def test_the_phone_number_alone_names_the_evolutions_printing():
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('9/108')) == 'en:xy12-9'


def test_a_number_matching_no_candidate_changes_nothing():
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('77/128')) is None


def test_a_number_the_shown_card_already_matches_changes_nothing():
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('46/102')) is None


def test_a_number_two_printings_share_names_nothing():
    twin = _row('ja:xy12-9', '9', 108, language='ja')
    assert _hint_number_named_printing([BASE, EVOLUTIONS, twin], [BASE, EVOLUTIONS, twin], _text('9/108')) is None


def test_a_wrong_set_total_names_nothing():
    # 9/102 is not the Evolutions number; a bare 9 with no total does not override a known total.
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('9/102')) is None
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('9')) is None


def test_a_number_without_confidence_or_below_the_footer_bar_names_nothing():
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('9/108', conf=None)) is None
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('9/108', conf=.8)) is None
    assert _hint_number_named_printing(RANKED, MEMBERS, SimpleNamespace(name=None, number=None, number_conf=None)) is None
    assert _hint_number_named_printing(RANKED, MEMBERS, None) is None


def test_a_name_beside_the_number_does_not_stop_it():
    assert _hint_number_named_printing(RANKED, MEMBERS, _text('9/108', name='Charmander')) == 'en:xy12-9'
