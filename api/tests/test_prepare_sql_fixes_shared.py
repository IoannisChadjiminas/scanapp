import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'scripts/ja_set_recovery/prepare_sql_fixes.py'
spec = importlib.util.spec_from_file_location('prepare_sql_fixes', path)
fixes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixes)
URL = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Kit/Card'


def test_url_in_use_is_refused_without_shares_link_of():
    with pytest.raises(AssertionError):
        fixes.row_change('ja:b', {'cardmarket_url': None}, {'url': URL}, {URL}, set())


def test_copy_row_may_share_the_link_of_the_row_it_copies():
    change = fixes.row_change('ja:b', {'cardmarket_url': None}, {'url': URL, 'shares_link_of': 'ja:a'},
                              {URL}, set(), shared_url=URL)
    assert change['cardmarket_url'] == URL and change['cardmarket_verified'] == 1


def test_shared_link_must_be_the_named_rows_link():
    with pytest.raises(AssertionError):
        fixes.row_change('ja:b', {'cardmarket_url': None}, {'url': URL, 'shares_link_of': 'ja:a'},
                         {URL}, set(), shared_url=URL + '-V2')
    with pytest.raises(AssertionError):  # a row that already has a link is not changed
        fixes.row_change('ja:b', {'cardmarket_url': URL}, {'url': URL, 'shares_link_of': 'ja:a'},
                         {URL}, set(), shared_url=URL)
