from app.recognition.ocr import OcrHit
from app.recognition.rank import damaged_footer_named_printing


def row(card_id, number, printed=''):
    return dict(card_id=card_id, collector_number=number, printed_collector_number=printed)


def footer(text, confidence=0.999, region='collector'):
    return OcrHit(text, confidence, region)


GYARADOS = [row('en:hgss1-4', '4', '4/123'), row('en:CLB-007', '7', '007/034')]


def test_lookalike_letter_and_cut_denominator_pick_the_one_printing():
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('C00z/03')]) == 'en:CLB-007'


def test_other_lookalikes_and_a_full_denominator():
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('00Z/034')]) == 'en:CLB-007'
    members = [row('a', '5', '005/102'), row('b', '7', '007/102')]
    assert damaged_footer_named_printing([members[1], members[0]], members, [footer('0O5/102')]) == 'a'
    assert damaged_footer_named_printing([members[1], members[0]], members, [footer('00S/102')]) == 'a'


def test_clean_read_is_left_to_the_normal_matcher():
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('007/034')]) is None


def test_two_fitting_printings_leave_the_order_alone():
    members = [row('a', '7', '007/034'), row('b', '7', '007/034')]
    assert damaged_footer_named_printing(members, members, [footer('00z/034')]) is None


def test_no_fit_or_already_shown_changes_nothing():
    ranked = [GYARADOS[1], GYARADOS[0]]
    assert damaged_footer_named_printing(ranked, GYARADOS, [footer('C00z/03')]) is None
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('C00z/99')]) is None


def test_weak_or_non_footer_reads_are_ignored():
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('C00z/03', 0.5)]) is None
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('C00z/03', region='name')]) is None
    assert damaged_footer_named_printing(GYARADOS, GYARADOS, [footer('00z')]) is None


def test_one_digit_cannot_match_a_different_number():
    assert damaged_footer_named_printing([GYARADOS[1], GYARADOS[0]], GYARADOS, [footer('00z/034')]) is None


def test_card_without_a_printed_total_fits_by_its_padded_number():
    # As staging returns them: Classic Collection has no printed total on record.
    members = [row('en:hgss1-4', '4'), row('en:A1-078', '078'), row('en:CLB-007', '007')]
    assert damaged_footer_named_printing(members, members, [footer('C00z/03')]) == 'en:CLB-007'


def test_unpadded_or_single_digit_numbers_without_a_total_do_not_fit():
    members = [row('en:hgss1-4', '4'), row('en:other-7', '7')]
    assert damaged_footer_named_printing(members, members, [footer('C00z/03')]) is None
    assert damaged_footer_named_printing(members, members, [footer('z/03')]) is None
    twins = [row('en:hgss1-4', '4'), row('a', '007'), row('b', '007')]
    assert damaged_footer_named_printing(twins, twins, [footer('C00z/03')]) is None
