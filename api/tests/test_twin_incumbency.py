import numpy as np

from app.recognition.twin_incumbency import incumbent_first, new_release_start


def unit(*v):
    a = np.asarray(v, dtype=np.float32)
    return a / np.linalg.norm(a)


EMB = np.asarray([unit(1, 0, 0), unit(0, 1, 0), unit(1, .05, 0), unit(0, 0, 1)])  # row 2 (new) twins row 0
POS = {"ja:old": 0, "ja:other": 1, "ja:new": 2, "en:old": 3}


def test_new_release_start_from_segments():
    assert new_release_start((2, 1, 1), 4, 1) == 3
    assert new_release_start((4,), 4, 1) is None
    assert new_release_start(None, 4, 1) is None


def test_a_new_leader_yields_to_its_served_twin():
    combined = [{"card_id": "ja:new", "language": "ja"}, {"card_id": "ja:other", "language": "ja"},
                {"card_id": "ja:old", "language": "ja"}]
    assert incumbent_first(combined, POS, EMB, 2, ("ja",)) == "ja:old"
    assert [r["card_id"] for r in combined] == ["ja:old", "ja:new", "ja:other"]


def test_negative_no_twin_no_change():
    combined = [{"card_id": "ja:new", "language": "ja"}, {"card_id": "ja:other", "language": "ja"}]
    assert incumbent_first(combined, POS, EMB, 2, ("ja",)) is None
    assert combined[0]["card_id"] == "ja:new"


def test_negative_a_served_leader_or_another_language_is_left_alone():
    served_lead = [{"card_id": "ja:old", "language": "ja"}, {"card_id": "ja:new", "language": "ja"}]
    assert incumbent_first(served_lead, POS, EMB, 2, ("ja",)) is None
    emb = EMB.copy(); emb[3] = emb[2]  # an English twin of the new card
    other_language = [{"card_id": "ja:new", "language": "ja"}, {"card_id": "en:old", "language": "en"}]
    pos = {"ja:new": 2, "en:old": 1}
    assert incumbent_first(other_language, pos, emb, 2, ()) is None


def test_flag_is_on_by_default():
    from app.config import Settings
    assert Settings().rank_twin_incumbency is True
