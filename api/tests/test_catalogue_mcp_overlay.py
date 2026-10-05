from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_catalogue_mcp_overlay import snapshot_sql,manifest_sql

def change(cid='en:s-1',mode='pad'):
    b=dict(card_id=cid,mode=mode,snapshot_id='old',source_vector_sha256='sha')
    return dict(before=b,after=dict(b,snapshot_id='new'))

def test_snapshot_rebinding_checks_actual_embedding_and_immutable_parent():
    q=snapshot_sql([change(),change('en:s-2')])
    assert 't.embedding=p.embedding' in q and 't.source_vector_sha256=p.source_vector_sha256' in q
    assert "status='loading'" in q and "snapshot_id='new'" in q
    assert "'en:s-1','en:s-2'" in q

@pytest.mark.parametrize('mutation',['mode','hash','duplicate'])
def test_snapshot_scope_cannot_silently_change_vectors(mutation):
    rows=[change()]
    if mutation=='mode':rows.append(change('en:s-2','square'))
    elif mutation=='hash':rows[0]['after']['source_vector_sha256']='changed'
    else:rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError):snapshot_sql(rows)

def manifest():
    b=dict(source_key='vector-manifest:pad',metadata=dict(indexed_ids=['z','a'],indexed_count=2))
    a=deepcopy(b);a['metadata'].update(indexed_ids=['z','a','new'],indexed_count=3)
    return dict(before=b,after=a)

def test_manifest_keeps_actual_matrix_order_and_checks_parent_json():
    q=manifest_sql(manifest())
    assert "t.metadata->'indexed_ids'" in q and 't.metadata=p.metadata' in q
    assert "status='loading'" in q

@pytest.mark.parametrize('ids',[['a','z','new'],['z','new'],['z','a','a']])
def test_manifest_reordering_loss_or_duplicate_is_rejected(ids):
    c=manifest();c['after']['metadata']['indexed_ids']=ids
    with pytest.raises(ValueError):manifest_sql(c)
