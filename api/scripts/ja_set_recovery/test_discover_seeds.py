import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from discover_seeds import discover


def test_aliases_use_observed_urls_and_shared_scopes_stay_out_of_seeds():
    registry = [
        {'group_id':'ja-ref-618','code':'20th','name':'20th Anniversary Starter Pack'},
        {'group_id':'ja-ref-774','code':'BKc','name':'Cobalion Battle Strength Deck'},
        {'group_id':'ja-ref-1038','code':'','name':'Pokémon-e Starter Deck'},
        {'group_id':'other','code':'','name':'Unknown Set'}]
    expansions = [{'name':name,'url':'https://www.cardmarket.com/en/Pokemon/Expansions/'+slug}
                  for name,slug in [('BREAK Starter Pack','Observed-BREAK'),('Battle Strength Decks','Battle-Strength-Decks'),('Base Expansion Pack','Base-Expansion-Pack')]]
    seeds, review = discover(registry, [], expansions, 'fixture')
    assert len(seeds)==1
    assert seeds[0]['url'].endswith('/Observed-BREAK')
    assert [r['state'] for r in review] == ['new_collection_route','shared_listing_needs_partition',
                                         'broad_pool_needs_card_match','not_matched_in_master_index']


def test_ambiguous_title_is_not_promoted_and_existing_seeds_are_preserved():
    registry=[{'group_id':'new','code':'','name':'Same Set'}, {'group_id':'old','code':'','name':'Existing'}]
    original={'group_id':'old','url':'observed-original','source':'old source'}
    seeds, review=discover(registry,[original],[{'name':'Same Set','url':'one'},{'name':'Same Set','url':'two'}],'fixture')
    assert seeds == [original]
    assert review[0]['state']=='ambiguous_title'
