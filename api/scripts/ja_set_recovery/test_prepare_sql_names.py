import pytest

from prepare_sql_names import check_families, plan_names


def test_name_plan_skips_unchanged_and_requires_the_english_name():
    rows = {"ja:A-1": {"language": "ja", "name": "Pikachu"}, "ja:B-1": {"language": "ja", "name": "N"}}
    accepted = {"ja:A-1": {"en": "Pikachu", "name_ja": "ピカチュウ"}, "ja:B-1": {"en": "N", "name_ja": "N"}}
    assert plan_names(rows, accepted) == {"ja:A-1": ("Pikachu", "ピカチュウ")}
    with pytest.raises(AssertionError):
        plan_names(rows, {"ja:A-1": {"en": "Raichu", "name_ja": "ライチュウ"}})


def test_family_ids_must_be_their_own_base():
    check_families({"en:a": "en:a", "en:PPS1-X-1": "en:a"}, {"en:a", "en:PPS1-X-1"})
    with pytest.raises(AssertionError):
        check_families({"en:PPS1-X-1": "en:a"}, {"en:a", "en:PPS1-X-1"})
