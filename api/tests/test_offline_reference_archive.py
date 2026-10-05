from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from offline_reference_archive import parse_set


def entry(number='95a', host='pkmncards.com'):
    return f'<a class="card-image-link" href="https://{host}/card/a/" title="Mr. Mime · Aquapolis (AQ) #{number}"><img class="card-image" src="https://pkmncards.com/wp-content/uploads/a.jpg"></a>'


def test_suffixes_remain_distinct_and_unknowns_are_not_approved():
    cards=parse_set(entry()+entry('95b'),'Aquapolis')
    assert [c['collector_raw'] for c in cards]==['95a','95b']
    assert all(c['language'] is None and c['finish'] is None and c['stamp'] is None
               and not c['exact_print_approved'] for c in cards)


def test_printed_symbol_collectors_remain_distinct_without_decoding_ids():
    cards=parse_set(entry('!')+entry('?'),'Aquapolis')
    assert [c['collector_raw'] for c in cards]==['!','?']
    assert all(not c['exact_print_approved'] for c in cards)


@pytest.mark.parametrize('number',['%3F','A/B','??',''])
def test_nonprinted_or_ambiguous_collectors_rejected(number):
    with pytest.raises(ValueError):parse_set(entry(number),'Aquapolis')


@pytest.mark.parametrize('html,set_name',[(entry(),'Skyridge'),(entry()+entry(),'Aquapolis'),
                                         (entry(host='bad.example'),'Aquapolis'),('', 'Aquapolis')])
def test_scope_collisions_and_unsafe_sources_rejected(html,set_name):
    with pytest.raises(ValueError):parse_set(html,set_name)
