"""Prepare individually reviewed primary repairs; never write cloud or publish."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from catalogue_completion_inventory import numbered_title, normalized_collector

SCOPES = {
    'base4': ('en', 'Base Set 2', 'Base-Set-2', 'B2', '130', 'Base Set 2 numeral-2/Pokeball symbol'),
    'swsh8': ('en', 'Fusion Strike', 'Fusion-Strike', 'FST', '264', 'Fusion Strike three-loop set symbol'),
    'swsh7': ('en', 'Evolving Skies', 'Evolving-Skies', 'EVS', '203', 'Evolving Skies mountain set symbol'),
    'swsh5': ('en', 'Battle Styles', 'Battle-Styles', 'BST', '163', 'Battle Styles fist set symbol'),
    'swsh6': ('en', 'Chilling Reign', 'Chilling-Reign', 'CRE', '198', 'Chilling Reign crown set symbol'),
    'sv10': ('en', 'Destined Rivals', 'Destined-Rivals', 'DRI', '182', 'Destined Rivals DRI EN set code'),
    'pl2': ('en', 'Rising Rivals', 'Rising-Rivals', 'RR', '111', 'Rising Rivals rising-sun set symbol'),
    'me04': ('en', 'Chaos Rising', 'Chaos-Rising', 'CRI', '086', 'Chaos Rising CRI EN set code'),
    'bw5': ('en', 'Dark Explorers', 'Dark-Explorers', 'DEX', '108', 'Dark Explorers set emblem'),
    'bw7': ('en', 'Boundaries Crossed', 'Boundaries-Crossed', 'BCR', '149', 'Boundaries Crossed set emblem'),
    'cel25': ('en', 'Celebrations', 'Celebrations', 'CEL', '025', 'Celebrations set emblem and intrinsic Pikachu 25 logo'),
    'dp1': ('en', 'Diamond & Pearl', 'Diamond-Pearl', 'DP', '130', 'Diamond & Pearl set emblem'),
    'sm4': ('en', 'Crimson Invasion', 'Crimson-Invasion', 'CIN', '111', 'Crimson Invasion set emblem'),
    'sm5': ('en', 'Ultra Prism', 'Ultra-Prism', 'UPR', '156', 'Ultra Prism set emblem'),
    'sv03': ('en', 'Obsidian Flames', 'Obsidian-Flames', 'OBF', '197', 'Obsidian Flames OBF EN set code'),
    'sv08': ('en', 'Surging Sparks', 'Surging-Sparks', 'SSP', '191', 'Surging Sparks SSP EN set code'),
    'sv10.5b': ('en', 'Black Bolt', 'Black-Bolt', 'BLK', '086', 'Black Bolt BLK EN set code'),
    'swsh11': ('en', 'Lost Origin', 'Lost-Origin', 'LOR', '196', 'Lost Origin set emblem'),
    'xy10': ('en', 'Fates Collide', 'Fates-Collide', 'FCO', '124', 'Fates Collide set emblem'),
    'xy12': ('en', 'Evolutions', 'Evolutions', 'EVO', '108', 'Evolutions set emblem'),
    'xy2': ('en', 'Flashfire', 'Flashfire', 'FLF', '106', 'Flashfire set emblem'),
}

MODERN_PRINT_MARKS = {
    'swsh5': ('E', '2021'), 'swsh6': ('E', '2021'),
    'swsh7': ('E', '2021'), 'swsh8': ('E', '2021'),
    'sv10': ('I', '2025'),
    'me04': ('J', '2026'),
    'cel25': ('E', '2021'), 'sv03': ('G', '2023'),
    'sv08': ('H', '2024'), 'sv10.5b': ('I', '2025'), 'swsh11': ('F', '2022'),
}

LEGACY_PRINT_YEARS = {
    'pl2': '2009', 'bw5': '2012', 'bw7': '2012', 'dp1': '2007',
    'sm4': '2017', 'sm5': '2018', 'xy10': '2016', 'xy12': '2016', 'xy2': '2014',
}

def exact_listing_name(name, set_id):
    # Cardmarket brackets the GL identifier; retain the printing identifier.
    return name.replace(' [GL] ', ' GL ') if set_id == 'pl2' else name

def checked_repair(card, product, siblings, review, decision, feature):
    language, name, expansion, code, denominator, symbol = SCOPES[card['set_id']]
    assert card['language'] == language and card['set_name'] == name
    assert not card['cardmarket_url']
    assert decision['card_id'] == card['id'] and decision['primary_identity_approved'] is True
    assert decision['visible_name'] == card['name']
    assert decision['visible_language'] == language
    assert decision['visible_set_symbol'] == symbol
    visible_number, visible_denominator = decision['visible_collector_raw'].split('/')
    assert visible_denominator == denominator
    assert normalized_collector(visible_number) == normalized_collector(card['collector_number'])
    assert decision['unexpected_stamp_observed'] is False
    if 'reference_pair_matches' in decision:
        assert decision['reference_pair_matches'] is True
    if card['set_id'] in MODERN_PRINT_MARKS:
        regulation, copyright_year = MODERN_PRINT_MARKS[card['set_id']]
        assert json.loads(card['variants_json'])['firstEdition'] is False
        assert decision['visible_regulation_mark'] == regulation
        assert decision['visible_copyright_year'] == copyright_year
        assert decision['edition_stamp_observed'] is False
    if card['set_id'] in LEGACY_PRINT_YEARS:
        assert json.loads(card['variants_json'])['firstEdition'] is False
        assert decision['visible_regulation_mark'] is None
        assert decision['visible_copyright_year'] == LEGACY_PRINT_YEARS[card['set_id']]
        assert decision['edition_stamp_observed'] is False
    title = numbered_title(product['name'])
    assert title and exact_listing_name(title['name'], card['set_id']) == card['name'] and title['code'] == code
    assert normalized_collector(title['collector']) == normalized_collector(card['collector_number'])
    url = urlparse(product['url'])
    assert url.scheme == 'https' and url.hostname == 'www.cardmarket.com'
    assert url.path.startswith('/en/Pokemon/Products/Singles/' + expansion + '/')
    assert product['expansion'] == expansion and product['card_id'] == card['id'] and product['matched'] == 1
    assert decision['primary_url'] == product['url']
    matches = [p for p in siblings if p['expansion'] == expansion and
               (t := numbered_title(p['name'])) and exact_listing_name(t['name'], card['set_id']) == card['name'] and
               normalized_collector(t['collector']) == normalized_collector(card['collector_number'])]
    assert len(matches) == 1 and matches[0]['url'] == product['url'], 'Unreviewed sibling/finish product'
    assert review['url'] == product['url']
    assert review['metadata']['photo_key'] == decision['listing_photo_key']
    assert feature['source_sha256'] == decision['original_sha256']
    assert feature['image_path'] == card['image_path'] and feature['available']
    after = deepcopy(card)
    after.update(cardmarket_url=product['url'], cardmarket_verified=1,
                 cardmarket_provenance='cached-listing-and-deployed-reference:' + expansion,
                 cardmarket_verified_at=decision['reviewed_at'])
    helper = dict(card_id=card['id'], cardmarket_url=product['url'], cardmarket_id=card['cardmarket_id'],
                  provenance=after['cardmarket_provenance'], verified_at=decision['reviewed_at'])
    assert helper['cardmarket_url'] == after['cardmarket_url']
    return after, helper

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('export','selection','decisions','feature_manifest','live_readback','output'):
        parser.add_argument('--'+key.replace('_','-'), type=Path, required=True)
    args=parser.parse_args();args.output.mkdir(exist_ok=False)
    tables={}
    for line in gzip.open(args.export,'rt'):
        r=json.loads(line)
        if 'row' in r:tables.setdefault(r['table'],[]).append(r['row'])
    cards={c['id']:c for c in tables['cards']};products={p['url']:p for p in tables['cardmarket_products']}
    reviews={r['url']:r for r in tables['cardmarket_review']};helpers={r['card_id']:r['metadata'] for r in tables['cardmarket_url_helpers']}
    features=json.loads(args.feature_manifest.read_text())['records']
    live=json.loads(args.live_readback.read_text())['rows'];live_by={r['id']:r for r in live}
    selection=json.loads(args.selection.read_text());decisions={r['card_id']:r for r in map(json.loads,args.decisions.read_text().splitlines())}
    assert len(selection)==len(decisions)==len(live_by)==len(live)
    ledgers=[]
    for selected in selection:
        card=cards[selected['card']['id']];decision=decisions[card['id']]
        product=products[decision['primary_url']];review=reviews[product['url']];fresh=live_by[card['id']]
        assert fresh['cardmarket_url'] is None and fresh['helper_metadata'] is None
        assert fresh['product_owner']==card['id'] and fresh['product_url']==product['url']
        assert fresh['expansion']==product['expansion'] and fresh['matched']==1
        assert str(fresh['cardmarket_id'])==str(card['cardmarket_id'])
        assert selected['card']==card
        for label in ('original','listing'):
            assert hashlib.sha256(Path(selected[label+'_local_file']).read_bytes()).hexdigest()==decision[label+'_sha256']
        after,helper=checked_repair(card,product,tables['cardmarket_products'],review,decision,features[card['id']])
        ledgers.append(dict(card_id=card['id'],card_before=card,card_after=after,
            helper_before=helpers.get(card['id']),helper_after=helper,product_before=product,
            product_unchanged=True,source_sha256=decision['original_sha256'],listing_sha256=decision['listing_sha256'],
            live_access_verified=False,published=False))
    (args.output/'correction-ledger.json').write_text(json.dumps(ledgers,indent=2,ensure_ascii=False))
    (args.output/'cardmarket-maps-delta.json').write_text(json.dumps({r['card_id']:r['helper_after'] for r in ledgers},indent=2))
    report=dict(records=len(ledgers),primary_helper_mirrors_passed=True,products_unchanged=True,
                references_and_vectors_unchanged=True,publication_ready=False,published=False,
                live_access_checks=0,remaining=['Full candidate integration and coherent readback','Staging/review publication gates','Fresh live URL checks remain pending'])
    (args.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
