from app.recognition.name_evidence import verification_name
from app.recognition.ocr import OcrHit
from app.recognition.rank import rerank

# dev-ja-vintage-110: a base Machamp photo whose name strip read the evolution note. The Japanese-named
# original pays a name penalty for not matching it; the English-named Evolutions reprint pays none.
BOGUS = "モンスターカードに重ねて使います。"
ORIGINAL = {"card_id": "ja:PMCG1-057", "name": "カイリキー", "language": "ja", "set_id": "PMCG1",
            "collector_number": "057", "visual_score": .8847}
REPRINT = {"card_id": "ja:CP6-057", "name": "Machamp", "language": "ja", "set_id": "CP6",
           "collector_number": "057", "visual_score": .8619}
NUMBERS = [OcrHit("60", .9, "collector")]


def rank(name, confidence):
    return [r["card_id"] for r in rerank([ORIGINAL, REPRINT], name, NUMBERS, False, detected_languages=("ja",),
                                         name_confidence=confidence, require_confident_ocr=True)]


def test_the_bogus_read_names_no_candidate():
    assert verification_name(BOGUS, .996, [ORIGINAL, REPRINT], languages=("ja",), numbers=NUMBERS)[2] is True


def test_with_the_read_the_reprint_wins_without_it_the_better_picture_does():
    assert rank(BOGUS, .996)[0] == "ja:CP6-057"
    assert rank(None, 0.0)[0] == "ja:PMCG1-057"


def test_negative_a_read_naming_a_candidate_is_kept():
    assert verification_name("カイリキー", .99, [ORIGINAL, REPRINT], languages=("ja",), numbers=NUMBERS)[2] is False


def test_flag_is_on_by_default():
    from app.config import Settings
    assert Settings().rank_unmatched_name is True
