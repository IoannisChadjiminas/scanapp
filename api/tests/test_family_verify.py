from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.recognition.family_verify import (artwork_families, decisive_family, merge_verified,
                                           promote_family, verify_families)
from app.recognition.local_match import LocalArtworkVerifier


def unit(*values):
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


# Full-card vectors: no pair here is a 0.95 twin, so only the artwork thumbnail can join rows.
VECTORS = {
    "ja:PMCG4-017": unit(1, 0, 0, 0), "ja:web1-042": unit(1, .9, 0, 0),
    "ja:jr-promo-005": unit(0, 1, 0, 0),
    "en:base1-4": unit(0, 0, 1, 0), "ja:SV2a-006": unit(0, 0, 1, 1),
    "en:tk-ex-latia-8": unit(0, 0, 0, 1), "en:tk-ex-m-10": unit(.5, 0, 0, 1),
}
# Artwork thumbnails: the two trainer-kit Potions are one illustration (0.98); the two
# Charizards share a title but not artwork (~0); the Dark Charizard reprint scans differ (0.45).
THUMBS = {
    "en:tk-ex-latia-8": unit(1, 0, 0), "en:tk-ex-m-10": unit(1, .2, 0),
    "en:base1-4": unit(0, 1, 0), "ja:SV2a-006": unit(0, 0, 1),
    "ja:PMCG4-017": unit(1, 1, 0), "ja:web1-042": unit(1, -.6, 1),
    "ja:jr-promo-005": unit(0, 1, 1),
}


def row(card_id, title):
    return {"card_id": card_id, "name": title, "view_title": title}


ROWS = [
    row("ja:jr-promo-005", "Mewtwo"),
    row("ja:PMCG4-017", "Dark Charizard"),
    row("en:base1-4", "Charizard"),
    row("ja:web1-042", "Dark Charizard"),
    row("ja:SV2a-006", "Charizard"),
    row("en:tk-ex-latia-8", "Potion"),
    row("en:tk-ex-m-10", "Potion"),
]


def ids(families):
    return [[r["card_id"] for r in f] for f in families]


def test_same_title_different_artwork_never_joins():
    families = artwork_families(ROWS, VECTORS.get, THUMBS.get)
    assert ["en:base1-4"] in ids(families) and ["ja:SV2a-006"] in ids(families)


def test_title_with_matching_thumbnail_joins():
    families = artwork_families(ROWS, VECTORS.get, THUMBS.get)
    assert ["en:tk-ex-latia-8", "en:tk-ex-m-10"] in ids(families)


def test_title_alone_does_not_join_without_thumbnails():
    families = artwork_families(ROWS, VECTORS.get, lambda card_id: None)
    assert ["en:tk-ex-latia-8"] in ids(families) and ["en:tk-ex-m-10"] in ids(families)


def test_full_card_twins_join_whatever_the_title():
    vectors = {**VECTORS, "en:tk-ex-m-10": VECTORS["ja:jr-promo-005"]}
    families = artwork_families(ROWS, vectors.get, lambda card_id: None)
    assert ["ja:jr-promo-005", "en:tk-ex-m-10"] in ids(families)


def test_reprints_both_verified_on_the_photo_merge_by_title():
    families = artwork_families(ROWS, VECTORS.get, THUMBS.get)
    assert ["ja:PMCG4-017"] in ids(families) and ["ja:web1-042"] in ids(families)
    merged = merge_verified(families, {"ja:web1-042": 31, "ja:PMCG4-017": 18})
    assert ["ja:PMCG4-017", "ja:web1-042"] in ids(merged)
    # one verified Charizard does not pull in an unverified same-title Charizard
    merged = merge_verified(families, {"en:base1-4": 30})
    assert ["en:base1-4"] in ids(merged) and ["ja:SV2a-006"] in ids(merged)


def test_decisive_family_needs_inliers_and_margin():
    families = merge_verified(artwork_families(ROWS, VECTORS.get, THUMBS.get),
                              {"ja:web1-042": 31, "ja:PMCG4-017": 18})
    dark = ids(families).index(["ja:PMCG4-017", "ja:web1-042"])
    assert decisive_family(families, {"ja:web1-042": 31, "ja:PMCG4-017": 18}) == dark
    assert decisive_family(families, {"ja:web1-042": 31, "ja:jr-promo-005": 25}) is None   # margin
    assert decisive_family(families, {"ja:web1-042": 11}) is None                          # too few
    assert decisive_family(families, {}) is None


def test_promote_keeps_the_order_inside_the_family():
    combined = [dict(r) for r in ROWS]
    order = [r["card_id"] for r in combined]
    combined.sort(key=lambda r: r["card_id"] == "ja:web1-042", reverse=True)  # verifier's own sort
    promote_family(combined, [row("ja:PMCG4-017", ""), row("ja:web1-042", "")], order)
    assert [r["card_id"] for r in combined][:3] == ["ja:PMCG4-017", "ja:web1-042", "ja:jr-promo-005"]


def test_verify_families_checks_one_reference_per_family_and_passes_the_cache():
    seen = []

    def verify(image, references, limit=8, prepared=None):
        seen.append((list(references), limit, prepared))
        return [SimpleNamespace(card_id="ja:PMCG4-017", artwork_inliers=40)]
    cards = {r["card_id"]: {"image_path": f"/data/{r['card_id']}.jpg"} for r in ROWS}
    cache = {}
    family, matches, diag = verify_families(SimpleNamespace(verify=verify), None, ROWS, cards,
                                            VECTORS.get, THUMBS.get, 16, prepared=cache)
    assert [r["card_id"] for r in family] == ["ja:PMCG4-017"]
    assert [m.card_id for m in matches] == ["ja:PMCG4-017"]
    assert [r for r, _ in seen[0][0]] == ["ja:jr-promo-005", "ja:PMCG4-017", "en:base1-4", "ja:web1-042",
                                          "ja:SV2a-006", "en:tk-ex-latia-8"]
    assert seen[0][1] == 6 and seen[0][2] is cache and diag["decided"] == ["ja:PMCG4-017"]


def test_verify_families_without_a_leader_changes_nothing():
    cards = {r["card_id"]: {"image_path": "x"} for r in ROWS}
    verifier = SimpleNamespace(verify=lambda image, refs, limit=8, prepared=None: [])
    assert verify_families(verifier, None, ROWS, cards, VECTORS.get, THUMBS.get, 16)[:2] == (None, [])


def test_query_features_are_extracted_once_per_scan(tmp_path, monkeypatch):
    verifier = LocalArtworkVerifier(tmp_path)
    calls = []
    real = verifier._queries

    def counted(*args):
        calls.append(args[1:])
        return real(*args)
    monkeypatch.setattr(verifier, "_queries", counted)
    image = Image.fromarray((np.random.default_rng(1).random((300, 220, 3)) * 255).astype("uint8"))
    cache = {}
    first = verifier.verify(image, [("a", "missing")], prepared=cache)
    second = verifier.verify(image, [("b", "missing")], 16, prepared=cache)
    assert first == second == []
    assert len(calls) == 2            # one first pass and one recovery pass, not four
    verifier.verify(image, [("c", "missing")])
    assert len(calls) == 4            # without a cache nothing is shared


def test_flag_and_depth_are_off_by_default():
    from app.config import Settings
    settings = Settings()
    assert settings.rank_family_verify is False
    assert (settings.family_verify_full_k, settings.family_verify_artwork_k) == (20, 15)
