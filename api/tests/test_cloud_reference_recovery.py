import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('cloud_reference_builder',
    Path(__file__).resolve().parents[1]/'scripts/build_cloud_reference_recovery.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def test_manifest_delta_only_sends_changes_and_new_ids():
    old=dict(indexed_ids=['a','b'],indexed_count=2,catalogue_version='old',stable='keep')
    new=dict(old,indexed_ids=['a','b','c'],indexed_count=3,catalogue_version='new')
    assert builder.manifest_delta(old,new)==(dict(indexed_count=3,catalogue_version='new'),['c'])
    assert old['indexed_ids']==['a','b']


@pytest.mark.parametrize('ids',[['a'],['b','a','c'],['a','b','a'],['a','b']])
def test_manifest_delta_rejects_removal_reordering_duplicates_or_empty_append(ids):
    with pytest.raises(ValueError):builder.manifest_delta({'indexed_ids':['a','b']},{'indexed_ids':ids})


def test_row_digest_is_order_independent_and_distinguishes_null_empty_and_numeric():
    original=[dict(id='a',value=None),dict(id='b',value='')]
    digest=builder.row_digest(original,['id','value'])
    assert digest==builder.row_digest(original[::-1],['id','value'])
    assert digest!=builder.row_digest([dict(id='a',value=''),dict(id='b',value='')],['id','value'])
    assert builder.literal("a'b")=="'a''b'"
