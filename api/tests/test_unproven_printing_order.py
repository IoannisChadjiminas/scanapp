from app.recognition.pipeline import prefer_unproven_visual_match


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
