from app.recognition.name_evidence import verification_name
from app.recognition.ocr import OcrHit
from app.recognition.rank import artwork_evidence_compatible

# PMCG4-017-2 on the all-eras catalogue: the name strip read the evolution note, and the
# shortlist holds new cards with English-only names plus the right card with its Japanese name.
BOGUS = "モンスターカードに重ねて使います。"
SHORTLIST = [
    {"card_id": "ja:jr-miscellaneous-promos-027", "name": "Mewtwo", "view_title": "Mewtwo", "language": "ja"},
    {"card_id": "ja:jr-intro-pack-neo-chikorita-16", "name": "Cyndaquil", "view_title": "Cyndaquil", "language": "ja"},
    {"card_id": "ja:PMCG4-017", "name": "わるいリザードン", "view_title": "Dark Charizard", "language": "ja"},
]
NO_FRACTION = [OcrHit("30", .99, "collector"), OcrHit("006", .99, "collector")]


def test_a_confident_read_naming_no_shortlisted_card_is_set_aside():
    assert verification_name(BOGUS, .995, SHORTLIST, languages=("ja",), numbers=NO_FRACTION) == (None, 0.0, True)


def test_the_set_aside_name_no_longer_drops_the_right_card_from_verification():
    right = SHORTLIST[2]
    # with the bogus read, the Japanese-named right card is filtered out and the
    # English-only-named new cards stay: the verifier would never see the right artwork
    assert not artwork_evidence_compatible(right, ocr_name=BOGUS, name_confidence=.995,
                                           numbers=[], languages=("ja",))
    assert artwork_evidence_compatible(SHORTLIST[0], ocr_name=BOGUS, name_confidence=.995,
                                       numbers=[], languages=("ja",))
    name, confidence, _ = verification_name(BOGUS, .995, SHORTLIST, languages=("ja",), numbers=NO_FRACTION)
    kept = [r["card_id"] for r in SHORTLIST if artwork_evidence_compatible(
        r, ocr_name=name, name_confidence=confidence, numbers=[], languages=("ja",))]
    assert kept == [r["card_id"] for r in SHORTLIST]


def test_a_read_that_names_a_shortlisted_card_is_kept():
    assert verification_name("わるいリザードン", .99, SHORTLIST, languages=("ja",), numbers=NO_FRACTION) == \
        ("わるいリザードン", .99, False)
    assert verification_name("Mewtwo", .99, SHORTLIST, languages=("ja",), numbers=NO_FRACTION)[2] is False


def test_out_of_scope_reads_are_kept():
    fraction = [OcrHit("017/065", .99, "collector")]
    assert verification_name(BOGUS, .995, SHORTLIST, languages=("ja",), numbers=fraction)[2] is False   # numbered
    assert verification_name(BOGUS, .995, SHORTLIST, languages=("en",), numbers=NO_FRACTION)[2] is False  # not Japanese
    assert verification_name(BOGUS, .60, SHORTLIST, languages=("ja",), numbers=NO_FRACTION)[2] is False   # not confident
    assert verification_name(None, 0.0, SHORTLIST, languages=("ja",), numbers=NO_FRACTION)[2] is False
    assert verification_name(BOGUS, .995, [], languages=("ja",), numbers=NO_FRACTION)[2] is False


def test_flag_is_off_by_default():
    from app.config import Settings
    assert Settings().verify_unmatched_name is False
