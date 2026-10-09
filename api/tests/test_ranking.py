from __future__ import annotations

from app.recognition.ocr import OcrHit, pick_collector_text, pick_name_line


def test_names_ignore_trainer_titles_hp_and_grading_labels():
    assert pick_name_line(['Supporter', "Professor's Research", '201/202']) == "Professor's Research"
    assert pick_name_line(['2023 POKEMON SV2a JP', 'GEM MT 10', 'ピカチュウ']) == 'ピカチュウ'
    assert pick_name_line(['HP 220', '220', '271/264', '©2021 Pokémon/Nintendo GAME FREAK']) is None
    assert pick_name_line(['サポート', 'ナンジャモ']) == 'ナンジャモ'
    assert pick_name_line(['AUTHENTIC', '220 ex', 'Lugia V']) == 'Lugia V'
    assert pick_name_line(['POKEMON', 'Umbreon VMAX']) == 'Umbreon VMAX'
    assert pick_name_line(['TAGE2', 'Charizard ex']) == 'Charizard ex'


def test_visual_leader_cannot_restore_foreign_printing_over_japanese_evidence():
    visual = [_card('english','Pikachu','173',.91,'en'),
              _card('japanese','ピカチュウ','173',.84,'ja')]
    ranked = rerank(visual,'ピカチュウ',[OcrHit('173/165',.99,'collector')],False,
                    detected_languages=('ja',),name_confidence=.99,require_confident_ocr=True)
    assert ranked[0]['card_id'] == 'japanese'
    assert ranked[1]['language_conflict']
    assert decide_status(ranked,enable_matched=True,min_visual=.78,min_gap=.04,retake=False) == 'matched'


def test_confident_card_name_contradiction_cannot_become_automatic_match():
    ranked = rerank([_card('wrong','Arctibax','129',.99,'en')], 'Fuecoco', [], False,
                    detected_languages=('en',),name_confidence=.99,require_confident_ocr=True)
    assert ranked[0]['strong_name_conflict']
    assert decide_status(ranked,enable_matched=True,min_visual=.78,min_gap=.04,retake=False) != 'matched'


def test_abutting_set_language_codes_are_not_collector_prefixes():
    from app.recognition.rank import extract_collector_candidates
    hits = extract_collector_candidates([],hits=[OcrHit('PAL EN 269/193',.99,'collector'),
                                                OcrHit('SV2a 173/165',.99,'collector')])
    assert {h.text for h in hits} == {'269/193','173/165'}


def test_set_and_rarity_text_do_not_invent_collector_conflicts():
    hits = extract_collector_candidates([], hits=[
        OcrHit('PAL269/193', .99, 'collector'),
        OcrHit('sv2a', .99, 'collector'),
        OcrHit('173/165AR', .99, 'collector'),
        OcrHit('348/190SAR', .99, 'collector'),
        OcrHit('SVIE251/198★★', .99, 'collector'),
    ])
    assert {h.text for h in hits} == {'269/193', '173/165', '348/190', '251/198'}


def test_low_confidence_title_does_not_hide_readable_name():
    from app.recognition.ocr import pick_confident_name
    assert pick_confident_name(['Surter','TRAINER','Miriam'], [.79,.99,.99]) == 'Miriam'
    assert pick_confident_name(['UmbreonVAX','SINGLE'], [.89,.99]) == 'UmbreonVAX'
    assert pick_confident_name(['Pikchu'], [.8]) == 'Pikchu'
    assert pick_confident_name(['TRAINER','220'], [.99,.99]) is None


def test_real_collector_namespaces_survive_set_code_cleanup():
    hits = extract_collector_candidates([], hits=[
        OcrHit(s, .99, 'collector') for s in
        ['TG05/030', 'GG25/070', 'SWSH051', 'SM183', 'SV2', 'SVP002']
    ])
    assert {h.text for h in hits} == {'TG05/030', 'GG25/070', 'SWSH051',
                                   'SM183', 'SV2', 'SVP002'}


def test_known_printed_denominator_cannot_be_overridden_by_bare_catalogue_number():
    from app.recognition.rank import number_matches_identifiers
    assert number_matches_identifiers([OcrHit('186/198', .99, 'collector')],
                                      ['186', '186/195']) is False
    assert number_matches_identifiers(['186/195'], ['186', '186/195']) is True
    assert number_matches_identifiers(['186/198'], ['186']) is True
    card = _card('lugia', 'Lugia V', '186', .99)
    card['printed_collector_number'] = '186/195'
    ranked = rerank([card], 'Lugia V', [OcrHit('186/198', .99, 'collector')], False,
                    name_confidence=.99, require_confident_ocr=True)
    assert ranked[0]['structured_collector_conflict']
    assert ranked[0]['printed_collector_number'] == '186/195'
    assert decide_status(ranked, enable_matched=True, min_visual=.78, min_gap=.04, retake=False) != 'matched'


def test_missing_catalogue_identifier_is_unknown_not_a_contradiction():
    from app.recognition.rank import number_matches_identifiers
    assert number_matches_identifiers(['199/165'], []) is None
    assert number_matches_identifiers(['199/165'], ['unknown']) is None
    assert number_matches_identifiers([], ['199/165']) is None


def test_conflicting_ocr_language_cannot_automatically_accept_only_foreign_candidate():
    ranked = rerank([_card('english','Pikachu','173',.99,'en')], 'ピカチュウ', [], False,
                    detected_languages=('ja',), name_confidence=.99, require_confident_ocr=True)
    assert decide_status(ranked,enable_matched=True,min_visual=.78,min_gap=.04,retake=False) != 'matched'
from app.recognition.rank import decide_status, extract_collector_candidates, name_match, number_match, rerank


def test_gameplay_numbers_are_not_collectors():
    lines = ["HP80", "80 HP", "×2", "x2", "LV. 12", "IV 12", "#25", "STAGE1"]
    hits = [OcrHit(text=s, confidence=.99, region="collector") for s in lines]
    assert extract_collector_candidates(lines, hits) == []
    assert pick_name_line(["BASIC", "Fuecoco", "HP80"]) == "Fuecoco"


def test_real_collectors_survive_gameplay_filter():
    hits = [OcrHit(text="036/198 ★", confidence=.99, region="collector"),
            OcrHit(text="SVP002", confidence=.99, region="collector")]
    assert {h.text for h in extract_collector_candidates([], hits)} == {"036/198", "SVP002"}


def test_hidden_fuecoco_number_does_not_favor_promo_from_weakness():
    visual = [_card("set", "Fuecoco", "036", .983),
              _card("alias", "Fuecoco", "036", .983),
              _card("promo", "Fuecoco", "002", .844)]
    hits = [OcrHit(text="HP80", confidence=.99, region="name"),
            OcrHit(text="×2", confidence=.99, region="collector")]
    numbers = extract_collector_candidates([h.text for h in hits], hits)
    ranked = rerank(visual, "Fuecoco", numbers, ocr_failed=False)
    assert ranked[0]["card_id"] in {"set", "alias"}
    assert ranked[0]["collector_conflict"] is False
    assert decide_status(ranked, enable_matched=True, min_visual=.78,
                         min_gap=.04, retake=False) == "uncertain"


def test_confidence_scales_positive_and_negative_ocr_without_dropping_candidates():
    cards = [_card("a", "Pikachu", "58", .8), _card("b", "Pikachu", "87", .8)]
    weak = rerank(cards, None, [OcrHit("58/102", .2, "collector")], False,
                  require_confident_ocr=True)
    strong = rerank(cards, None, [OcrHit("58/102", .99, "collector")], False,
                    require_confident_ocr=True)
    assert len(weak) == len(strong) == 2
    assert weak[0]["combined_score"] < strong[0]["combined_score"]
    assert weak[0]["ocr_consistent"] is None
    assert weak[1]["collector_conflict"] is False
    assert strong[1]["collector_conflict"] is True


def test_missing_or_unknown_confidence_is_neutral_in_live_evidence_mode():
    cards = [_card("a", "Pikachu", "58", .8)]
    ranked = rerank(cards, "Pikachu", [OcrHit("58/102", None, "collector")], False,
                    name_confidence=None, require_confident_ocr=True)
    assert ranked[0]["combined_score"] == .8
    assert ranked[0]["ocr_consistent"] is None


def test_confidence_from_unrelated_number_does_not_boost_a_weak_match():
    cards = [_card("a", "Pikachu", "58", .8)]
    ranked = rerank(cards, None, [OcrHit("58/102", .1, "collector"),
                                 OcrHit("87/130", .99, "collector")], False,
                    require_confident_ocr=True)
    assert ranked[0]["combined_score"] < .8
    assert ranked[0]["collector_conflict"] is True


def _card(card_id: str, name: str, number: str, score: float, language: str = "en") -> dict:
    return {
        "card_id": card_id,
        "name": name,
        "set_name": "Base",
        "collector_number": number,
        "image_url": f"/api/v1/cards/{card_id}/image",
        "visual_score": score,
        "combined_score": score,
        "ocr_consistent": None,
        "language": language,
    }


def test_ocr_boosts_matching_number() -> None:
    visual = [
        _card("a", "Pikachu", "25", 0.80),
        _card("b", "Raichu", "26", 0.79),
    ]
    ranked = rerank(visual, "Pikachu", ["25"], ocr_failed=False)
    assert ranked[0]["card_id"] == "a"
    assert ranked[0]["ocr_consistent"] is True
    assert ranked[0]["combined_score"] > ranked[0]["visual_score"]


def test_conflicting_number_penalizes_candidate() -> None:
    visual = [_card("a", "Pikachu", "25", 0.91)]
    ranked = rerank(visual, None, ["99"], ocr_failed=False)
    assert ranked[0]["ocr_consistent"] is False
    assert ranked[0]["combined_score"] < ranked[0]["visual_score"]


def test_missing_ocr_does_not_block_visual_order() -> None:
    visual = [
        _card("a", "Pikachu", "25", 0.88),
        _card("b", "Pikachu", "26", 0.70),
    ]
    ranked = rerank(visual, None, [], ocr_failed=True)
    assert [item["card_id"] for item in ranked] == ["a", "b"]
    assert ranked[0]["ocr_consistent"] is None


def test_matched_when_visual_and_gap_pass() -> None:
    suggestions = [
        _card("a", "Pikachu", "25", 0.92),
        _card("b", "Raichu", "26", 0.70),
    ]
    suggestions[0]["ocr_consistent"] = False
    status = decide_status(
        suggestions,
        enable_matched=False,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "uncertain"


def test_no_match_when_visual_is_low() -> None:
    suggestions = [
        _card("a", "Pikachu", "25", 0.62),
        _card("b", "Raichu", "26", 0.40),
    ]
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "no_match"


def test_ocr_consistent_leader_matches_below_visual_bar() -> None:
    suggestions = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.73, "ja"),
        _card("tyranitar", "M Tyranitar EX", "089/081", 0.65, "ja"),
    ]
    suggestions[0]["ocr_consistent"] = True
    suggestions[1]["ocr_consistent"] = False
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_visual_ocr=0.70,
        min_gap=0.04,
        retake=False,
    )
    assert status == "matched"


def test_ocr_does_not_rescue_weak_or_tied_visual() -> None:
    no_ocr = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.73, "ja"),
        _card("tyranitar", "M Tyranitar EX", "089/081", 0.65, "ja"),
    ]
    assert (
        decide_status(
            no_ocr,
            enable_matched=True,
            min_visual=0.78,
            min_visual_ocr=0.70,
            min_gap=0.04,
            retake=False,
        )
        == "no_match"
    )
    weak = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.62, "ja"),
        _card("tyranitar", "M Tyranitar EX", "089/081", 0.50, "ja"),
    ]
    weak[0]["ocr_consistent"] = True
    assert (
        decide_status(
            weak,
            enable_matched=True,
            min_visual=0.78,
            min_visual_ocr=0.70,
            min_gap=0.04,
            retake=False,
        )
        == "no_match"
    )
    tied = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.73, "ja"),
        _card("other", "Gengar & Mimikyu GX", "038/095", 0.72, "ja"),
    ]
    tied[0]["ocr_consistent"] = True
    assert (
        decide_status(
            tied,
            enable_matched=True,
            min_visual=0.78,
            min_visual_ocr=0.70,
            min_gap=0.04,
            retake=False,
        )
        == "no_match"
    )


def test_no_match_when_gap_is_small() -> None:
    suggestions = [
        _card("a", "Switch", "95", 0.88),
        _card("b", "Scoop Up", "78", 0.87),
    ]
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "no_match"


def test_short_ocr_digit_does_not_match_collector() -> None:
    visual = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.722, "en"),
    ]
    ranked = rerank(visual, "たね", ["2", "240", "102/0955"], ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "gengar"


def test_ocr_cannot_outrank_clear_visual_leader() -> None:
    visual = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.722, "en"),
    ]
    ranked = rerank(visual, "Crobat V", ["182"], ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "gengar"


def test_japanese_print_wins_when_art_matches_english() -> None:
    visual = [
        _card("en-zard", "Charizard", "4", 0.91, "en"),
        _card("ja-zard", "リザードン", "006", 0.89, "ja"),
    ]
    ranked = rerank(visual, "リザードン", [], ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "ja-zard"


def test_matched_uses_visual_gap_not_ocr_scores() -> None:
    suggestions = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.722, "en"),
    ]
    suggestions[0]["combined_score"] = 0.798
    suggestions[1]["combined_score"] = 0.802
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "matched"


def test_retake_when_image_unsuitable() -> None:
    status = decide_status(
        [_card("a", "Pikachu", "25", 0.95)],
        enable_matched=True,
        min_visual=0.7,
        min_gap=0.01,
        retake=True,
    )
    assert status == "retake"


def test_number_match_ignores_short_damage_digits() -> None:
    assert number_match(["2", "240", "102/0955"], "182") is False
    assert number_match(["2"], "2") is True
    assert number_match(["103/095"], "103/095") is True
    assert number_match(["103"], "103/095") is True


def test_ocr_fraction_distinguishes_reprints() -> None:
    assert number_match(["008/034", "008034"], "008/034") is True
    assert number_match(["008/034", "008034"], "008/015") is False
    assert number_match(["008"], "008/015") is True
    assert number_match(["008"], "008/034") is True
    assert number_match(["008"], "007/015") is False
    assert number_match(["008/034"], "007/015") is False


def test_reprint_with_matching_fraction_is_matched() -> None:
    visual = [
        _card("mcd", "Pikachu", "007/015", 0.9997),
        _card("clc", "Pikachu", "008/034", 0.9989),
        _card("base", "Pikachu", "58", 0.84),
    ]
    ranked = rerank(visual, "Pikachu", ["008/034"], ocr_failed=False, detected_languages=("en",))
    assert ranked[0]["card_id"] == "clc"
    assert ranked[0]["ocr_consistent"] is True
    assert ranked[1]["card_id"] == "mcd"
    assert ranked[1]["ocr_consistent"] is False
    status = decide_status(
        ranked,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "matched"


def test_pick_collector_prefers_fraction_line() -> None:
    assert pick_collector_text(["008/034", "33 Pokemoen/Mrtendo"]) == "008/034"
    assert pick_collector_text(["Illus. Mitsuhiro Arita"]) == "Illus. Mitsuhiro Arita"


def test_pick_name_skips_japanese_stage_label() -> None:
    assert pick_name_line(["たね", "ゲンガー&ミミッキュGX"]) == "ゲンガー&ミミッキュGX"
    assert pick_name_line(["Basic Pokémon", "Pikachu"]) == "Pikachu"


def test_japanese_ocr_name_does_not_match_english_card() -> None:
    assert not name_match("ゲンガー&ミミッキュGX", "Gengar & Mimikyu GX")


def test_collector_prefix_is_required() -> None:
    assert number_match(["TG01"], "GG01") is False
    assert number_match(["TG01"], "TG01") is True


def test_collector_number_is_not_a_prefix_of_another() -> None:
    assert number_match(["1030"], "103") is False
    assert number_match(["103"], "1030") is False
    assert number_match(["103"], "103") is True


def test_enable_matched_false_never_returns_matched() -> None:
    suggestions = [
        _card("a", "Pikachu", "25", 0.95),
        _card("b", "Raichu", "26", 0.50),
    ]
    assert (
        decide_status(
            suggestions,
            enable_matched=False,
            min_visual=0.78,
            min_gap=0.04,
            retake=False,
        )
        == "uncertain"
    )


def test_language_gap_uses_all_candidates() -> None:
    suggestions = [
        _card("en-zard", "Charizard", "4", 0.90, "en"),
        _card("ja-zard", "リザードン", "006", 0.89, "ja"),
    ]
    assert (
        decide_status(
            suggestions,
            enable_matched=True,
            min_visual=0.78,
            min_gap=0.04,
            retake=False,
        )
        == "no_match"
    )


def test_printed_number_lets_the_closer_image_win() -> None:
    visual = [
        _card("reprint", "Mew VMAX", "026", 1.0),
        _card("original", "Mew VMAX", "114", 0.98),
    ]
    visual[0]["printed_collector_number"] = "114"
    hits = [OcrHit(text="114/264", confidence=0.95, region="collector")]
    ranked = rerank(
        visual,
        "Mew VMAX",
        hits,
        ocr_failed=False,
        detected_languages=("en",),
    )
    assert ranked[0]["card_id"] == "reprint"
    assert ranked[0]["collector_conflict"] is False
    assert ranked[1]["collector_conflict"] is False


def test_wide_visual_gap_beats_a_false_collector_hit() -> None:
    visual = [
        _card("celebi", "Shining Celebi", "024", 1.0),
        _card("gengar", "Gengar", "018", 0.83),
    ]
    hits = [
        OcrHit(text="18", confidence=0.9, region="collector"),
        OcrHit(text="106/105", confidence=0.92, region="collector"),
    ]
    ranked = rerank(
        visual,
        "Shining Celebi",
        hits,
        ocr_failed=False,
        detected_languages=("en",),
    )
    assert ranked[0]["card_id"] == "celebi"


def test_same_name_does_not_override_confident_fraction_without_printed_number_metadata() -> None:
    visual = [
        _card("reprint", "Darkrai & Cresselia LEGEND", "019", 1.0),
        _card("original", "Darkrai & Cresselia LEGEND", "99", 0.93),
    ]
    hits = [OcrHit(text="99/102", confidence=0.92, region="collector")]
    ranked = rerank(
        visual,
        "Darkrai & Cresselia LEGEND",
        hits,
        ocr_failed=False,
        detected_languages=("en",),
    )
    assert ranked[0]["card_id"] == "original"
    assert ranked[0]["collector_conflict"] is False
    close = [
        _card("reprint", "Darkrai & Cresselia LEGEND", "019", 0.94),
        _card("original", "Darkrai & Cresselia LEGEND", "99", 0.93),
    ]
    tied = rerank(
        close,
        "Darkrai & Cresselia LEGEND",
        hits,
        ocr_failed=False,
        detected_languages=("en",),
    )
    assert tied[0]["card_id"] == "original"


def test_reliable_collector_conflict_is_uncertain() -> None:
    visual = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.90, "en"),
    ]
    hits = [OcrHit(text="182", confidence=0.92, region="collector")]
    ranked = rerank(visual, "Crobat V", hits, ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "crobat"
    assert ranked[1].get("collector_conflict") is True
    status = decide_status(
        ranked,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "uncertain"


def test_finish_twins_are_uncertain() -> None:
    suggestions = [
        _card("holo", "Pikachu", "25", 0.91),
        _card("nonholo", "Pikachu", "25", 0.905),
    ]
    suggestions[0]["set_name"] = "Base"
    suggestions[1]["set_name"] = "Base"
    assert (
        decide_status(
            suggestions,
            enable_matched=True,
            min_visual=0.78,
            min_gap=0.04,
            retake=False,
        )
        == "uncertain"
    )


def test_decide_status_says_which_branch_decided():
    from app.recognition.rank import decide_status_with_reason
    def row(card_id, visual, **extra):
        return dict(card_id=card_id, visual_score=visual, **extra)
    kwargs = dict(enable_matched=True, min_visual=.78, min_visual_ocr=.70, min_gap=.04, retake=False)
    assert decide_status_with_reason([], **kwargs) == ('no_match', 'no_candidates')
    assert decide_status_with_reason([row('a', .9)], **{**kwargs, 'retake': True}) == ('retake', 'retake_input')
    assert decide_status_with_reason([row('a', .9), row('b', .6)], **kwargs) == ('matched', 'visual_ok')
    assert decide_status_with_reason([row('a', .74, ocr_consistent=True), row('b', .5)], **kwargs) == ('matched', 'ocr_floor')
    assert decide_status_with_reason([row('a', .6), row('b', .5)], **kwargs) == ('no_match', 'below_visual_floor')
    assert decide_status_with_reason([row('a', .9, collector_conflict=True)], **kwargs) == ('uncertain', 'conflict')
    assert decide_status_with_reason([row('a', .9), row('b', .6)], **{**kwargs, 'enable_matched': False}) == (
        'uncertain', 'matched_disabled')
