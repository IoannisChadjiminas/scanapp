from __future__ import annotations

import numpy as np
from PIL import Image

from app.recognition.ocr import OcrHit
from app.recognition.printing import ReferencePrintingIndex, assess_printings, artwork_thumbnail
from app.db import connect, init_catalog


def card(i, number="58", score=.95, set_name="Base Set"):
    return dict(card_id=i, name="Pikachu", language="en", set_name=set_name,
                collector_number=number, visual_score=score, combined_score=score)


def assess(ranked, family=(), hits=(), incomplete=False, retake=False):
    return assess_printings(ranked, family=list(family), hits=list(hits),
        reference_incomplete=incomplete, min_visual=.78, min_gap=.04, retake=retake)


def test_shared_reference_blocks_wide_visual_gap_without_identifier():
    base = card("base")
    classic = card("classic", "014", .6, "30th Classic Collection")
    classic["printed_collector_number"] = "58"
    result = assess([base], family=[base, classic])
    assert result.ambiguous
    assert len(result.members) == 2
    assert "four corners" in result.guidance


def test_shared_number_does_not_prove_a_printing():
    base = card("base", "58/102")
    shadowless = card("shadowless", "58/102", .82, "Base Set Shadowless")
    result = assess([base], [base, shadowless], [OcrHit("58/102", .99, "collector")])
    assert result.ambiguous
    assert result.reason == "shared_printing_identifier"


def test_unique_reliable_fraction_can_remove_printing_block_not_force_match():
    base = card("base", "58/102")
    bs2 = card("bs2", "87/130", .7, "Base Set 2")
    assert not assess([base], [base, bs2], [OcrHit("58/102", .99, "collector")]).ambiguous


def test_weak_unknown_location_or_bare_number_cannot_disambiguate():
    base = card("base", "58/102")
    bs2 = card("bs2", "87/130", .7, "Base Set 2")
    for hit in (OcrHit("58/102", .3, "collector"), OcrHit("58/102", None, "collector"),
                OcrHit("58/102", .99, "name"), OcrHit("58", .99, "collector")):
        assert assess([base], [base, bs2], [hit]).ambiguous


def test_missing_reference_prevents_claim_of_unique_proof():
    base = card("base", "58/102")
    bs2 = card("bs2", "87/130", .7, "Base Set 2")
    assert assess([base], [base, bs2], [OcrHit("58/102", .99, "collector")], incomplete=True).ambiguous


def test_incomplete_coverage_keeps_review_but_excludes_conflicting_numbers():
    base = card('base', '24/102', set_name='Base Set')
    bs2 = card('bs2', '35/130', set_name='Base Set 2')
    legendary = card('lc', '37', set_name='Legendary Collection')
    result = assess([base], [base, bs2, legendary], [OcrHit('24/102', .99, 'collector')], incomplete=True)
    assert result.ambiguous and not result.reference_coverage_complete
    assert [r['card_id'] for r in result.members] == ['base']
    assert result.collector_evidence == ('24/102',)


def test_shared_and_unknown_numbers_remain_reviewable_after_pruning():
    base = card('base', '24/102')
    sibling = card('shadowless', '24/102', set_name='Shadowless')
    unknown = card('unknown', '', set_name='Unknown metadata')
    other = card('other', '35/130', set_name='Other')
    result = assess([base], [base, sibling, unknown, other], [OcrHit('24/102', .99, 'collector')])
    assert result.ambiguous
    assert {r['card_id'] for r in result.members} == {'base', 'shadowless', 'unknown'}


def test_weak_holder_and_conflicting_ocr_never_prune_review_choices():
    base = card('base', '24/102')
    other = card('other', '35/130', set_name='Other')
    for hits in ([OcrHit('24/102', .84, 'collector')],
                 [OcrHit('24/102', .99, 'holder_collector')],
                 [OcrHit('24/102', .99, 'collector'), OcrHit('35/130', .99, 'collector')]):
        result = assess([base], [base, other], hits, incomplete=True)
        assert result.ambiguous and len(result.members) == 2


def test_conflicting_reliable_observations_abstain():
    base = card("base", "58/102")
    bs2 = card("bs2", "87/130", .7, "Base Set 2")
    assert assess([base], [base, bs2], [OcrHit("58/102", .99, "collector"),
                                      OcrHit("999/999", .99, "collector")]).ambiguous


def test_aliases_are_not_printing_choices_and_low_visual_is_not_rescued():
    base = card("base")
    assert not assess([base, card("en:base", score=.95)]).ambiguous
    assert not assess([card("weak", score=.6)], [base, card("bs2", set_name="Base Set 2")]).ambiguous
    assert not assess([base], [base, card("bs2", set_name="Base Set 2")], retake=True).ambiguous


def test_likely_identity_expands_family_without_claiming_unique_printing():
    top = {**card('base', score=.77), 'likely_identity_supported':True}
    sibling = card('classic', '014', .6, 'Classic')
    decision = assess([top], [top, sibling])
    assert decision.ambiguous
    assert {r['card_id'] for r in decision.members} == {'base','classic'}
    assert not assess([top], [top, sibling], retake=True).ambiguous


def test_nearby_same_name_printings_abstain_even_without_reference_family():
    result = assess([card("base"), card("classic", "014", .94, "30th Classic Collection")])
    assert result.ambiguous
    assert not assess([card("base"), {**card("other"), "name": "Raichu"}]).ambiguous
    assert not assess([card("base")], [{**card("other"), "name": "Raichu"}]).ambiguous


def test_reference_index_expands_beyond_top_k_and_keeps_distinct_cards(tmp_path):
    root = tmp_path / "reference-images"
    root.mkdir()
    rng = np.random.default_rng(2)
    image = Image.fromarray(rng.integers(0, 255, (320, 224, 3), dtype=np.uint8))
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    try:
        for i, set_name in (("base", "Base Set"), ("classic", "Classic")):
            path = root / f"{i}.png"
            image.save(path)
            conn.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,image_path,has_image) VALUES (?,?,?,?,?,?,?,?,1)",
                         (i, i, "Pikachu", i, set_name, "58", "en", str(path)))
        index = ReferencePrintingIndex(tmp_path)
        members, incomplete = index.family(conn, card("base"))
        assert {r["id"] for r in members} == {"base", "classic"}
        assert not incomplete
        assert artwork_thumbnail(Image.new("RGB", (224, 320), "white")) is None
    finally:
        conn.close()
