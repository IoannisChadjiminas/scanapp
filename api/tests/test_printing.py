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


def _charmander_scan():
    # The shape of a real scan: four same-artwork Charmander prints, the true one (9/108)
    # 0.042 below the shown card, just outside the 0.04 window.
    def char(i, number, score, set_name):
        return dict(card_id=i, name="Charmander", language="en", set_name=set_name,
                    collector_number=number, visual_score=score, combined_score=score)
    return [char("base1-46", "46", .891, "Base Set"), char("lc-70", "70", .870, "Legendary Collection"),
            char("base4-69", "69", .858, "Base Set 2"), char("xy12-9", "9", .849, "Evolutions"),
            char("cel-1", "1", .80, "Celebrations")]


def test_without_the_wider_list_the_true_print_is_left_out():
    result = assess(_charmander_scan())
    assert result.ambiguous
    assert "xy12-9" not in {r["card_id"] for r in result.members}


def test_wider_list_offers_the_same_name_print_and_keeps_the_shown_card():
    ranked = _charmander_scan()
    result = assess_printings(ranked, family=[], hits=[], reference_incomplete=False,
                              min_visual=.78, min_gap=.04, retake=False, wider_gap=.08)
    ids = [r["card_id"] for r in result.members]
    assert ids[0] == "base1-46"
    assert "xy12-9" in ids
    assert "cel-1" not in ids  # 0.091 below the shown card: outside the wider window


def test_wider_list_never_makes_a_sure_printing_unsure():
    lone = [dict(card_id="base1-46", name="Charmander", language="en", set_name="Base Set",
                 collector_number="46", visual_score=.95, combined_score=.95),
            dict(card_id="xy12-9", name="Charmander", language="en", set_name="Evolutions",
                 collector_number="9", visual_score=.89, combined_score=.89)]
    result = assess_printings(lone, family=[], hits=[], reference_incomplete=False,
                              min_visual=.78, min_gap=.04, retake=False, wider_gap=.08)
    assert not result.ambiguous


def test_wider_list_skips_other_names_languages_and_respects_the_cap():
    ranked = _charmander_scan()
    ranked.append(dict(card_id="ja:x", name="Charmander", language="ja", set_name="JP",
                       collector_number="4", visual_score=.86, combined_score=.86))
    ranked.append(dict(card_id="vulpix", name="Vulpix", language="en", set_name="Base Set",
                       collector_number="68", visual_score=.86, combined_score=.86))
    result = assess_printings(ranked, family=[], hits=[], reference_incomplete=False,
                              min_visual=.78, min_gap=.04, retake=False, wider_gap=.08, max_choices=4)
    ids = [r["card_id"] for r in result.members]
    assert "ja:x" not in ids and "vulpix" not in ids
    assert len(ids) == 4


class _ArtByCard:
    # Base-set Charizard artwork for the 1996 card and its reprints; other art for the rest.
    BASE_ART = {"ja:PMCG1-021", "ja:CP6-011", "ja:S8a-P-001"}

    def thumbnail(self, card_id, raw_path):
        del raw_path
        vector = np.zeros(8, dtype=np.float32)
        vector[0 if card_id in self.BASE_ART else 1] = 1
        return vector


def _species_catalog():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE cards (id, name, language, set_id, set_name, collector_number, image_path)")
    conn.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, 'x')", [
        ("ja:PMCG1-021", "リザードン", "ja", "PMCG1", "拡張パック", "021"),
        ("ja:CP6-011", "Charizard", "ja", "CP6", "20th Anniversary", "011"),
        ("ja:S8a-P-001", "リザードン", "ja", "S8a-P", "25th Anniversary", "001"),
        ("ja:M6a-137", "メガリザードンXex", "ja", "M6a", "M6a", "137"),
        ("ja:PMCG1-020", "リザード", "ja", "PMCG1", "拡張パック", "020"),
    ])
    return conn


def _species_switch(monkeypatch, on):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "printing_family_species", on)


def test_printing_family_by_exact_name_misses_a_reprint_stored_in_latin(monkeypatch, tmp_path):
    _species_switch(monkeypatch, False)
    index = ReferencePrintingIndex(tmp_path, feature_store=_ArtByCard())
    top = {"card_id": "ja:CP6-011", "name": "Charizard", "language": "ja"}
    members, _ = index.family(_species_catalog(), top)
    assert [m["id"] for m in members] == ["ja:CP6-011"]


def test_printing_family_by_species_finds_same_artwork_across_scripts(monkeypatch, tmp_path):
    _species_switch(monkeypatch, True)
    index = ReferencePrintingIndex(tmp_path, feature_store=_ArtByCard())
    top = {"card_id": "ja:CP6-011", "name": "Charizard", "language": "ja"}
    members, _ = index.family(_species_catalog(), top)
    # Same species and same artwork only: not the Mega Charizard art, not Charmeleon.
    assert sorted(m["id"] for m in members) == ["ja:CP6-011", "ja:PMCG1-021", "ja:S8a-P-001"]


def test_assess_printings_offers_same_species_family_only_with_the_switch():
    top = dict(card_id="ja:CP6-011", name="Charizard", language="ja", set_id="CP6", set_name="20th Anniversary",
               collector_number="011", visual_score=.9, combined_score=.9)
    base = dict(card_id="ja:PMCG1-021", id="ja:PMCG1-021", name="リザードン", language="ja", set_id="PMCG1",
                set_name="拡張パック", collector_number="021")
    off = assess_printings([top], family=[top, base], hits=[], reference_incomplete=False,
                           min_visual=.78, min_gap=.04, retake=False)
    on = assess_printings([top], family=[top, base], hits=[], reference_incomplete=False,
                          min_visual=.78, min_gap=.04, retake=False, by_species=True)
    assert not off.ambiguous
    assert on.ambiguous
    assert sorted(m["card_id"] for m in on.members) == ["ja:CP6-011", "ja:PMCG1-021"]
