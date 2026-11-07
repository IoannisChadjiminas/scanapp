from types import SimpleNamespace

import numpy as np

from app.recognition.family_verify import artwork_families, decisive_family, promote_family, verify_families


def unit(*values):
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


VECTORS = {
    "ja:PMCG4-017": unit(1, 0, 0), "ja:web1-042": unit(1, .4, 0),      # same art, cosine ~0.93
    "ja:jr-promo-005": unit(0, 1, 0),
    "ja:PCG6-075": unit(0, 0, 1), "en:ex11-113": unit(0, .05, 1),       # same art, other language
}
ROWS = [
    {"card_id": "ja:jr-promo-005", "name": "Mewtwo", "view_title": "Mewtwo"},
    {"card_id": "ja:PMCG4-017", "name": "わるいリザードン", "view_title": "Dark Charizard"},
    {"card_id": "en:ex11-113", "name": "Metagross Star", "view_title": None},
    {"card_id": "ja:web1-042", "name": "わるいリザードン", "view_title": "Dark Charizard"},
    {"card_id": "ja:PCG6-075", "name": "メタグロススター", "view_title": "Metagross Gold Star"},
]


def test_families_join_reprints_by_title_and_languages_by_vector():
    families = artwork_families(ROWS, VECTORS.get)
    assert [[r["card_id"] for r in f] for f in families] == [
        ["ja:jr-promo-005"], ["ja:PMCG4-017", "ja:web1-042"], ["en:ex11-113", "ja:PCG6-075"]]


def test_decisive_family_needs_inliers_and_margin():
    families = artwork_families(ROWS, VECTORS.get)
    assert decisive_family(families, {"ja:web1-042": 31, "ja:jr-promo-005": 18}) == 1
    assert decisive_family(families, {"ja:web1-042": 31, "ja:jr-promo-005": 25}) is None   # margin
    assert decisive_family(families, {"ja:web1-042": 11}) is None                          # too few
    # two members of one family never compete with each other
    assert decisive_family(families, {"ja:web1-042": 31, "ja:PMCG4-017": 30}) == 1
    assert decisive_family(families, {}) is None


def test_promote_keeps_the_order_inside_the_family():
    combined = [dict(r) for r in ROWS]
    order = [r["card_id"] for r in combined]
    combined.sort(key=lambda r: r["card_id"] == "ja:web1-042", reverse=True)  # verifier's own sort
    family = artwork_families(ROWS, VECTORS.get)[1]
    promote_family(combined, family, order)
    assert [r["card_id"] for r in combined] == [
        "ja:PMCG4-017", "ja:web1-042", "ja:jr-promo-005", "en:ex11-113", "ja:PCG6-075"]


def test_verify_families_checks_one_reference_per_family():
    seen = []

    def verify(image, references, limit=8):
        seen.append((list(references), limit))
        return [SimpleNamespace(card_id="ja:PMCG4-017", artwork_inliers=40)]
    cards = {r["card_id"]: {"image_path": f"/data/{r['card_id']}.jpg"} for r in ROWS}
    family, matches, diag = verify_families(SimpleNamespace(verify=verify), None, ROWS, cards, VECTORS.get, 16)
    assert [r["card_id"] for r in family] == ["ja:PMCG4-017", "ja:web1-042"]
    assert [m.card_id for m in matches] == ["ja:PMCG4-017"]
    assert [r for r, _ in seen[0][0]] == ["ja:jr-promo-005", "ja:PMCG4-017", "en:ex11-113"]
    assert seen[0][1] == 3 and diag["decided"] == ["ja:PMCG4-017", "ja:web1-042"]


def test_verify_families_without_a_leader_changes_nothing():
    cards = {r["card_id"]: {"image_path": "x"} for r in ROWS}
    verifier = SimpleNamespace(verify=lambda image, refs, limit=8: [])
    assert verify_families(verifier, None, ROWS, cards, VECTORS.get, 16)[:2] == (None, [])


def test_flag_is_off_by_default():
    from app.config import Settings
    assert Settings().rank_family_verify is False
