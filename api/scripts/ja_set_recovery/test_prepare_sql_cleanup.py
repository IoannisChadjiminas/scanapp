import pytest

from cleanup_features import new_manifest, removed_files
from prepare_sql_cleanup import check_decisions, new_segments, plan_artwork, plan_vectors


def test_segments_lose_removed_rows_and_drop_when_empty():
    assert new_segments([5, 2, 3], [0, 4, 5, 6]) == [3, 3]
    assert new_segments([5, 2, 3], []) == [5, 2, 3]
    assert new_segments([1, 1], [1]) == [1]


def test_vector_plan_keeps_order_and_renames_moves():
    ids = ["en:a", "a", "en:P-A-1", "extra-x", "ja:y"]
    d = {"delete": {"a": "dup", "extra-x": "dup"}, "unvector": {"en:P-A-1": "pocket"},
         "move_vector": {"extra-x": "ja:z"}}
    assert plan_vectors(ids, d) == (["en:a", "ja:z", "ja:y"], [0, 3, 4], [1, 2])


def test_decisions_are_checked():
    cards = {"en:a", "a", "extra-x", "ja:z", "en:P-A-1"}
    vectors = {"en:a", "a", "extra-x", "en:P-A-1"}
    ok = {"delete": {"a": "", "extra-x": ""}, "successor": {"a": "en:a", "extra-x": "ja:z"},
          "unvector": {"en:P-A-1": ""}, "move_vector": {"extra-x": "ja:z"}, "relink": {"ja:z": "extra-x"}}
    check_decisions(ok, cards, vectors)
    with pytest.raises(AssertionError):  # a moved vector needs a target without one
        check_decisions({**ok, "move_vector": {"extra-x": "en:a"}}, cards, vectors)
    with pytest.raises(AssertionError):  # a successor cannot be deleted
        check_decisions({**ok, "successor": {"a": "extra-x"}}, cards, vectors)
    with pytest.raises(AssertionError):  # an unvectored row must have a vector
        check_decisions({**ok, "unvector": {"ja:z": ""}}, cards, vectors)


def test_adopted_image_moves_artwork_and_requires_its_move():
    cards = {"dup": {"id": "dup"}, "orig": {"id": "orig", "name": "Magcargo", "set_name": "Dawn Dash", "collector_number": "014"},
             "x": {"id": "x"}}
    d = {"delete": {"dup": "", "x": ""}, "successor": {"dup": "orig"}, "unvector": {},
         "move_vector": {"dup": "orig"}, "relink": {}, "adopt_image": {"orig": "dup"}}
    check_decisions(d, set(cards), {"dup", "x"})
    recs = [{"card_id": "dup", "profile": "p", "name": "Magcargo Lv.35", "set_name": "MP&DD", "collector_number": "u69"},
            {"card_id": "x", "profile": "p"}, {"card_id": "y", "profile": "p"}]
    keep, out = plan_artwork(recs, d, cards)
    assert keep == [0, 2]
    assert out[0] == {"card_id": "orig", "profile": "p", "name": "Magcargo", "set_name": "Dawn Dash", "collector_number": "014"}
    with pytest.raises(AssertionError):  # a moved vector with regions must adopt the image
        plan_artwork(recs, {**d, "adopt_image": {}}, cards)
    with pytest.raises(AssertionError):  # adoption needs the matching move
        check_decisions({**d, "adopt_image": {"orig": "x"}}, set(cards), {"dup", "x"})


def test_feature_manifest_adopts_record_and_drops_unused_files():
    parent = {"records": {"dup": {"available": True, "filename": "d.npz", "image_path": "/i/dup.jpg"},
                          "orig": {"available": True, "filename": "o.npz", "image_path": "/i/orig.jpg"},
                          "x": {"available": True, "filename": "x.npz", "image_path": "/i/x.jpg"}}}
    sig = [{"id": "orig", "image_path": "/i/dup.jpg", "rarity": None}]
    m = new_manifest(parent, sig, ["dup", "x"], {"orig": "dup"})
    assert m["records"] == {"orig": parent["records"]["dup"]} and m["available"] == 1
    assert removed_files(parent, m) == {"o.npz", "x.npz"}
    with pytest.raises(AssertionError):  # the catalogue row must point at the adopted image
        new_manifest(parent, [{"id": "orig", "image_path": "/i/orig.jpg"}], ["dup", "x"], {"orig": "dup"})
