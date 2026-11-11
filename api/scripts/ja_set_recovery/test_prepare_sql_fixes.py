import pytest

from prepare_sql_fixes import label_groups, row_change

OLD = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Other-Set/Other-Card"
NEW = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Right-Set/Right-Card"


def _row(**values):
    row = {"name": "A", "view_title": "A", "set_name": "S", "category": None, "rarity": None,
           "printed_collector_number": None, "cardmarket_url": None, "cardmarket_id": None,
           "has_image": 1, "remote_image_url": None}
    row.update(values)
    return row


def test_label_columns_need_a_reason_and_stay_inside_the_list():
    fix = {"set": {"name": "B", "category": "Energy"}, "reason": "printed name on its own image"}
    assert row_change("ja:x-1", _row(), fix, set(), set()) == {"name": "B", "category": "Energy"}
    with pytest.raises(AssertionError):
        row_change("ja:x-1", _row(), {"set": {"name": "B"}}, set(), set())
    with pytest.raises(AssertionError):
        row_change("ja:x-1", _row(), {"set": {"image_path": "/x"}, "reason": "r"}, set(), set())


def test_a_relink_keeps_the_product_id_and_takes_only_the_page_matched_to_this_card():
    row = _row(cardmarket_url=OLD, cardmarket_id=7)
    fix = {"relink": {"url": NEW, "old_url": OLD}, "reason": "the page of another product"}
    used = {OLD}
    change = row_change("ja:x-1", row, fix, used, {7}, {NEW: "ja:x-1"})
    assert change["cardmarket_url"] == NEW and "cardmarket_id" not in change and NEW in used
    # The page some other card was matched to, a page already in use, or a stale old page: refused.
    for products, urls, old in (({NEW: "ja:x-2"}, {OLD}, OLD), ({NEW: "ja:x-1"}, {OLD, NEW}, OLD),
                                ({NEW: "ja:x-1"}, {OLD}, OLD + "x"), ({}, {OLD}, OLD)):
        with pytest.raises(AssertionError):
            row_change("ja:x-1", row, {"relink": {"url": NEW, "old_url": old}, "reason": "r"}, set(urls), {7}, products)


def test_an_image_alias_row_keeps_its_identity_columns():
    aliases = frozenset({"en:exu-A", "en:ex10-unown-A"})
    with pytest.raises(AssertionError):
        row_change("en:exu-A", _row(), {"set": {"set_name": "T"}, "reason": "r"}, set(), set(), alias_ids=aliases)
    with pytest.raises(AssertionError):
        row_change("en:ex10-unown-A", _row(), {"name_en": "Unown"}, set(), set(), alias_ids=aliases)
    fix = {"set": {"printed_collector_number": "A/28"}, "reason": "r"}
    assert row_change("en:exu-A", _row(), fix, set(), set(), alias_ids=aliases) == {"printed_collector_number": "A/28"}


def test_the_older_fix_kinds_are_unchanged():
    assert row_change("ja:x-1", _row(), {"name_en": "Eevee", "name_ja": "イーブイ"}, set(), set()) == {
        "name": "イーブイ", "view_title": "Eevee"}
    cleared = row_change("ja:x-1", _row(cardmarket_url=OLD, cardmarket_id=7), {"clear_link": True, "reason": "r"}, {OLD}, {7})
    assert cleared["cardmarket_url"] is None and cleared["cardmarket_id"] is None and cleared["cardmarket_verified"] == 0
    added = row_change("ja:x-1", _row(), {"url": NEW, "product_id": "9"}, set(), set())
    assert added["cardmarket_url"] == NEW and added["cardmarket_id"] == 9


def test_the_manifest_lists_a_set_wide_rename_once():
    rename = {"set": {"set_name": "T"}, "reason": "the set's printed name"}
    groups = label_groups([("ja:s-1", rename, {"set_name": "S"}), ("ja:s-2", rename, {"set_name": "S"}),
                           ("ja:s-3", rename, {"set_name": "R"}),
                           ("ja:x-1", {"relink": {"url": NEW, "old_url": OLD}, "reason": "r"}, {})])
    assert [g["ids"] for g in groups] == [["ja:s-1", "ja:s-2"], ["ja:s-3"], ["ja:x-1"]]
    assert groups[0] == {"ids": ["ja:s-1", "ja:s-2"], "reason": "the set's printed name", "set": {"set_name": "T"},
                         "before": {"set_name": "S"}}
    assert groups[2]["relink"] == {"url": NEW, "old_url": OLD} and "set" not in groups[2]
