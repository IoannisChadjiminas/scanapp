import pytest

from prepare_sql_cleanup import check_decisions, new_segments, plan_vectors


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
