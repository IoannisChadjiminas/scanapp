from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_catalogue_seed_plan import chunks, identifier, literal


def test_bounds_use_utf8_c_order_and_do_not_overlap():
    batches = chunks('cards', [('é',), ('Z',), ('a',)], ['id'], 'parent', 'candidate', 'release', 2)
    assert [b['expected_rows'] for b in batches] == [2, 1]
    assert batches[0]['lower_exclusive'] is None
    assert batches[0]['upper_inclusive'] == ('a',)
    assert batches[1]['lower_exclusive'] == ('a',)
    assert batches[1]['upper_inclusive'] == ('é',)
    assert all("status='loading'" in b['sql'] and 'RETURNING 1' in b['sql'] for b in batches)


def test_composite_vector_keys_preserve_modes():
    batches = chunks('card_embeddings', [('c', 'square'), ('c', 'pad')],
                     ['card_id', 'mode', 'embedding'], 'parent', 'candidate', 'release', 1)
    assert batches[0]['upper_inclusive'] == ('c', 'pad')
    assert batches[1]['upper_inclusive'] == ('c', 'square')
    assert '("card_id" COLLATE "C","mode" COLLATE "C")' in batches[0]['sql']


def test_duplicate_keys_and_active_target_rejected():
    with pytest.raises(ValueError):
        chunks('cards', [('c',), ('c',)], ['id'], 'parent', 'candidate', 'release', 2)
    with pytest.raises(ValueError):
        chunks('cards', [('c',)], ['id'], 'parent', 'parent', 'release', 2)


def test_sql_literal_quotes_are_escaped_and_unsafe_identifiers_rejected():
    assert literal("Farfetch'd") == "'Farfetch''d'"
    for value in ['a;DROP TABLE cards', 'a.b', '']:
        with pytest.raises(ValueError):
            identifier(value)
    for value in ['a\x00b', 'a\\b']:
        with pytest.raises(ValueError):
            literal(value)
