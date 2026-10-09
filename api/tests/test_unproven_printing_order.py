from app.recognition.pipeline import prefer_unproven_visual_match, settle_unproven_twins


def row(card_id, visual, combined):
    return dict(card_id=card_id, name='Pikachu', language='en',
                visual_score=visual, combined_score=combined)


def test_unproven_printing_shows_the_closest_image():
    roaring = row('xy6-20', 0.7872, 0.8881)
    earlier = row('2015xy-6', 0.7968, 0.8464)
    promo = row('2016xy-6', 0.8323, 0.8820)
    ranked = [roaring, promo, earlier]
    prefer_unproven_visual_match(ranked, [roaring, earlier, promo])
    assert [item['card_id'] for item in ranked] == ['2016xy-6', 'xy6-20', '2015xy-6']


def test_visual_leader_already_shown_keeps_the_other_order():
    promo = row('2016xy-6', 0.8323, 0.8820)
    roaring = row('xy6-20', 0.7872, 0.8881)
    ranked = [promo, roaring]
    prefer_unproven_visual_match(ranked, [promo, roaring])
    assert [item['card_id'] for item in ranked] == ['2016xy-6', 'xy6-20']


def test_cards_outside_the_printing_group_do_not_take_the_display():
    other = row('other', 0.95, 0.95)
    close = row('2016xy-6', 0.83, 0.80)
    far = row('xy6-20', 0.78, 0.90)
    ranked = [far, other, close]
    prefer_unproven_visual_match(ranked, [far, close])
    assert [item['card_id'] for item in ranked] == ['2016xy-6', 'xy6-20', 'other']


def test_small_visual_gap_keeps_the_current_card():
    shown = row('sv08-247', 0.8243, 0.9850)
    closer = row('sv08-219', 0.8382, 0.8213)
    ranked = [shown, closer]
    prefer_unproven_visual_match(ranked, [shown, closer])
    assert [item['card_id'] for item in ranked] == ['sv08-247', 'sv08-219']


def test_one_group_member_is_left_alone():
    ranked = [row('only', 0.80, 0.90), row('other', 0.99, 0.70)]
    prefer_unproven_visual_match(ranked, [ranked[0]])
    assert [item['card_id'] for item in ranked] == ['only', 'other']


def twin(card_id, set_id, number, visual, combined, **flags):
    return dict(card_id=card_id, name='Charmeleon', language='en', set_id=set_id,
                collector_number=number, visual_score=visual, combined_score=combined, **flags)


def shown_first(ranked, members=None):
    settle_unproven_twins(ranked, members or list(ranked))
    return [item['card_id'] for item in ranked]


def test_twins_show_the_same_printing_whichever_scored_higher():
    base = twin('base1-24', 'base1', '24', 0.901, 0.961)
    reprint = twin('en:base4-35', 'base4', '35', 0.905, 0.965)
    assert shown_first([reprint, base]) == ['base1-24', 'en:base4-35']
    base, reprint = dict(base, visual_score=0.91, combined_score=0.97), dict(reprint)
    assert shown_first([base, reprint]) == ['base1-24', 'en:base4-35']


def test_set_numbers_order_by_value_not_by_text():
    second = twin('base2-1', 'base2', '1', 0.90, 0.96)
    tenth = twin('base10-1', 'base10', '1', 0.91, 0.97)
    assert shown_first([tenth, second]) == ['base2-1', 'base10-1']


def test_a_set_id_is_read_from_the_card_id_when_the_row_has_none():
    base = twin('base1-24', None, '24', 0.90, 0.96)
    reprint = twin('en:base4-35', None, '35', 0.91, 0.97)
    assert shown_first([reprint, base]) == ['base1-24', 'en:base4-35']


def test_a_clear_image_or_score_lead_is_not_a_twin():
    base = twin('base1-24', 'base1', '24', 0.85, 0.91)
    reprint = twin('en:base4-35', 'base4', '35', 0.90, 0.96)
    assert shown_first([reprint, base]) == ['en:base4-35', 'base1-24']
    # The image is close, but the collector number moved the combined score.
    base = twin('base1-24', 'base1', '24', 0.90, 0.88)
    reprint = twin('en:base4-35', 'base4', '35', 0.90, 0.98)
    assert shown_first([reprint, base]) == ['en:base4-35', 'base1-24']


def test_a_different_ocr_verdict_is_not_a_twin():
    base = twin('base1-24', 'base1', '24', 0.90, 0.95, collector_conflict=True)
    reprint = twin('en:base4-35', 'base4', '35', 0.90, 0.96, collector_conflict=False)
    assert shown_first([reprint, base]) == ['en:base4-35', 'base1-24']
    base = twin('base1-24', 'base1', '24', 0.90, 0.95, ocr_consistent=None)
    reprint = twin('en:base4-35', 'base4', '35', 0.90, 0.96, ocr_consistent=True)
    assert shown_first([reprint, base]) == ['en:base4-35', 'base1-24']


def test_only_printings_of_the_shown_group_are_settled():
    base = twin('base1-24', 'base1', '24', 0.90, 0.96)
    reprint = twin('en:base4-35', 'base4', '35', 0.90, 0.96)
    other = dict(twin('aaa-1', 'aaa', '1', 0.90, 0.96), name='Charmander')
    # A card outside the group never takes the display, and neither does
    # another card that only shares the score.
    assert shown_first([reprint, other, base], [reprint, base]) == ['base1-24', 'en:base4-35', 'aaa-1']
    assert shown_first([reprint, base], [base]) == ['en:base4-35', 'base1-24']
    assert shown_first([reprint, other], [reprint, other]) == ['en:base4-35', 'aaa-1']


def test_base_set_charmeleon_scan_shows_base_set_first():
    # Scores of a real scan whose footer number was not read: three printings
    # of the same picture within the gap, a fourth outside it, and a second
    # catalogue id of the first printing that is not a member of the group.
    verdict = dict(ocr_consistent=True, collector_conflict=False, structured_collector_conflict=False)
    base2 = twin('en:base4-35', 'base4', '35', 0.8623, 0.9723, **verdict)
    base = twin('en:base1-24', 'base1', '24', 0.8593, 0.9693, **verdict)
    legendary = twin('en:lc-37', 'lc', '37', 0.8476, 0.9576, **verdict)
    evolutions = twin('en:xy12-10', 'xy12', '10', 0.8130, 0.9229, **verdict)
    alias = twin('base1-24', 'base1', '24', 0.8593, 0.9693, **verdict)
    ranked = [base2, base, legendary, evolutions, alias]
    assert shown_first(ranked, [base2, base, legendary, evolutions])[0] == 'en:base1-24'
