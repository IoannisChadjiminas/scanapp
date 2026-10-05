from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_catalogue_overlay_plan import insert_sql, update_sql, value_sql, vector_sql


def test_utf8_and_sql_like_source_text_are_encoded_as_data():
    text = "Farfetch'd \\ 日本語');DROP TABLE cards;--"
    sql = value_sql(text)
    assert text.encode().hex() in sql
    assert 'DROP TABLE' not in sql
    assert value_sql(None, 'bigint') == 'NULL::bigint'
    assert value_sql({'printing': text}, 'jsonb').endswith('::jsonb')
    with pytest.raises(ValueError):
        value_sql(True, 'integer')


def test_update_checks_null_before_values_and_loading_manifest():
    changes = [{'before': {'id': 'en:x', 'cardmarket_url': None},
                'after': {'id': 'en:x', 'cardmarket_url': 'https://example.com/observed'}}]
    sql = update_sql('candidate', 'release', 'cards', changes, ['id'],
                     {'id': 'text', 'cardmarket_url': 'text'})
    assert '"cardmarket_url" IS NOT DISTINCT FROM v."before_cardmarket_url"' in sql
    assert 't."id" IS NOT DISTINCT FROM v."before_id"' in sql
    assert "status='loading'" in sql
    assert 'RETURNING 1' in sql and 'count(*) AS rows_changed' in sql
    assert 'SET "cardmarket_url"=' in sql
    assert 'SET "id"=' not in sql
    changes[0]['after']['id'] = 'en:other'
    with pytest.raises(ValueError, match='Key mutation'):
        update_sql('candidate', 'release', 'cards', changes, ['id'],
                   {'id': 'text', 'cardmarket_url': 'text'})


def test_vector_decimal_roundtrip_preserves_float32_bits():
    rng = np.random.default_rng(47)
    vector = rng.normal(size=384).astype(np.float32)
    vector /= np.linalg.norm(vector)
    vector[0] = np.float32(-0.0)
    vector /= np.linalg.norm(vector)
    sql = vector_sql(vector)
    decoded = np.asarray(sql.split('[', 1)[1].split(']', 1)[0].split(','), dtype=np.float32)
    assert decoded.tobytes() == vector.tobytes()
    for invalid in [np.zeros(384), np.ones(383), np.full(384, np.nan), np.ones(384)]:
        with pytest.raises(ValueError):
            vector_sql(invalid)


def test_insert_has_no_conflict_skip_or_active_validation():
    sql = insert_sql('candidate', 'release', 'reference_metadata',
                     [{'source_key': 'observed', 'metadata': {'published': False}}],
                     {'source_key': 'text', 'metadata': 'jsonb'})
    assert "status='loading'" in sql and 'RETURNING 1' in sql
    assert 'ON CONFLICT' not in sql and 'validated' not in sql
    with pytest.raises(ValueError, match='Column drift'):
        insert_sql('candidate', 'release', 'reference_metadata',
                   [{'source_key': 'a'}, {'different': 'b'}], {'source_key': 'text'})
