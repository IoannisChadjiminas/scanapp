from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.db import connect, init_catalog
from app.routes.cards import search_cards, search_sets
from test_card_search import _request


@pytest.fixture
def catalog(tmp_path):
    conn = connect(tmp_path / 'filters.sqlite')
    init_catalog(conn)
    today = date.today().isoformat()
    for lang, set_id, name, released in [('en', 'old', 'Old', '2020-01-01'), ('en', 'new', 'New', today), ('ja', 'new', 'Japanese', today)]:
        conn.execute("INSERT INTO set_releases(language, set_id, release_date, fetched_at) VALUES (?, ?, ?, '2026-10-11')", (lang, set_id, released))
    # reverse holo chosen, normal chosen, normal fallback to holo, missing prices,
    # downward momentum, under-trend listing; equal-price ties are intentional.
    entries = [
        ('a', 'en', 'old', '{"reverse":true}', 1, 10, 1, 12, 10, 20, 16, 24, 19),
        ('b', 'en', 'new', '{"normal":true,"holo":true}', 2, 10, 5, 12, 9.5, 30, 20, 25, 20),
        ('c', 'ja', 'new', '{"normal":true}', 3, None, None, None, None, 10, 7, 8, 10),
        ('d', 'en', 'old', '{}', None, None, None, None, None, None, None, None, None),
        ('e', 'en', 'old', '{"normal":true,"reverse":true}', 4, 8, 7, 8, 10, None, None, None, None),
    ]
    for card_id, lang, set_id, variants, product, trend, low, avg7, avg30, th, lh, a7h, a30h in entries:
        conn.execute('''INSERT INTO cards(id, provider_id, name, set_id, set_name, collector_number, language, rarity, category, variants_json, cardmarket_id)
            VALUES (?, ?, 'Pikachu', ?, ?, '1', ?, ' Rare ', 'Pokemon', ?, ?)''', (card_id, card_id, set_id, set_id, lang, variants, product))
        conn.execute("INSERT INTO cards_fts(id,name,set_name,collector_number) VALUES (?, 'Pikachu', ?, '1')", (card_id, set_id))
        if product:
            conn.execute('''INSERT INTO cardmarket_guide(id_product, trend, low, avg1, avg7, avg30, trend_holo, low_holo, avg1_holo, avg7_holo, avg30_holo, guide_date)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, 2, ?, ?, ?)''', (product, trend, low, avg7, avg30, th, lh, a7h, a30h, today))
    conn.commit()
    yield conn
    conn.close()


def search(catalog, **kwargs):
    return search_cards(_request(catalog), **kwargs)


def ids(response):
    return [card.id for card in response.items]


def test_price_holo_choice_and_missing(catalog):
    result = search(catalog, min_price=10, max_price=20, sort='price_asc')
    assert ids(result) == ['b', 'c', 'a'] and result.total == 3
    assert [(c.market.basis, c.market.trend) for c in result.items] == [('normal', 10), ('holo', 10), ('holo', 20)]
    assert ids(search(catalog, sort='price_desc')) == ['a', 'b', 'c', 'e', 'd']
    assert next(c for c in search(catalog).items if c.id == "d").market is None


def test_holo_rare_is_priced_from_the_plain_columns(catalog):
    # A holo-only card (an ex or holo rare) has no reverse holo; Cardmarket's
    # -holo figures are reverse holo sales and must not replace its trend.
    catalog.execute("UPDATE cards SET variants_json='{\"holo\":true,\"normal\":false,\"reverse\":false}' WHERE id='a'")
    catalog.commit()
    card = next(c for c in search(catalog).items if c.id == 'a')
    assert (card.market.basis, card.market.trend, card.market.low) == ('normal', 10, 1)


def test_sets_and_language_and_fts(catalog):
    assert ids(search(catalog, sets=['en:new'])) == ['b']
    assert ids(search(catalog, sets=['new'], language='ja')) == ['c']
    assert search(catalog, q='pika', min_price=10).total == 3
    assert search(catalog, sets=['en:new', 'ja:new']).total == 2
    sets = search_sets(_request(catalog), language='en')
    assert [s['set_id'] for s in sets] == ['new', 'old']
    assert [s['cards'] for s in sets] == [1, 3]


@pytest.mark.parametrize('sort,expected', [('price_asc', ['e','b','c','a','d']), ('momentum', ['a','b','c','e','d']), ('discount', ['e','c','a','b','d']), ('under_trend', ['b','c','a','e','d'])])
def test_sorts_and_stable_paging(catalog, sort, expected):
    assert ids(search(catalog, sort=sort)) == expected
    pages = [search(catalog, sort=sort, limit=2, offset=i) for i in [0,2,4]]
    assert [card.id for page in pages for card in page.items] == expected
    assert {page.total for page in pages} == {5}


@pytest.mark.parametrize('preset,expected', [('trending_up', ['a','b']), ('below_average', ['e']), ('under_trend', ['b','c','a']), ('new_set', ['b','c']), ('biggest_drops', ['c','e'])])
def test_presets(catalog, preset, expected):
    assert ids(search(catalog, preset=preset)) == expected
    assert search(catalog, preset=preset, min_price=100).total == 0


def test_additional_filters(catalog):
    assert ids(search(catalog, momentum_min=.1, sold_recently=True, sort='momentum')) == ['a','b']
    assert search(catalog, momentum_max=-.1).total == 2
    assert search(catalog, rarity=['rare'], category='pokemon', finish='normal').total == 3
    assert ids(search(catalog, finish='reverse')) == ['a', 'e']
    assert ids(search(catalog, released_before=date(2021,1,1), sort='number')) == ['a','d','e']
    assert search(catalog, released_after=date.today()-timedelta(days=90)).total == 2
    assert ids(search(catalog, sort='unknown')) == ids(search(catalog))
    with pytest.raises(HTTPException): search(catalog, min_price=2,max_price=1)
    with pytest.raises(HTTPException): search(catalog, finish='bad')


def test_http_params_and_validation(catalog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.routes.cards import router

    app = FastAPI()
    app.state.dbs = SimpleNamespace(catalog=catalog)
    app.include_router(router)
    with TestClient(app) as client:
        result = client.get('/cards?set=en:new&set=ja:new&sort=price_asc')
        assert result.status_code == 200
        assert result.json()['total'] == 2
        assert result.json()['items'][0]['market']['trend'] == 10
        assert client.get('/cards?min_price=-1').status_code == 422
        assert client.get('/cards?min_price=nan').status_code == 422
        assert client.get('/cards?released_after=2026-02-30').status_code == 422
        assert client.get('/search-options').json()['rarities'] == [{'value': 'rare', 'label': 'Rare'}]


def test_attached_snapshot_join_and_sets_cache(catalog):
    request = _request(catalog)
    search_sets(request)
    catalog.execute("ATTACH DATABASE ':memory:' AS cloud")
    catalog.execute('CREATE TABLE cloud.cards AS SELECT * FROM main.cards')
    catalog.execute('CREATE TEMP VIEW cards AS SELECT * FROM cloud.cards')
    assert ids(search_cards(request, min_price=10, sort='price_asc')) == ['b', 'c', 'a']
    catalog.execute("INSERT INTO cloud.cards SELECT * FROM main.cards WHERE id='b'")
    assert search_sets(request)[0]['cards'] == 2


def test_presets_require_floor_and_complete_metrics(catalog):
    catalog.execute('UPDATE cardmarket_guide SET trend=1, avg7=2, avg30=0.5 WHERE id_product=2')
    assert ids(search(catalog, preset='trending_up')) == ['a']
    catalog.execute('UPDATE cardmarket_guide SET avg7_holo=NULL, avg7=NULL WHERE id_product=1')
    assert search(catalog, preset='trending_up').total == 0
    catalog.execute("UPDATE cards SET rarity='None' WHERE id='b'")
    assert next(card for card in search(catalog).items if card.id == 'b').rarity == ''


def test_chase_top_ten_per_set_before_other_filters_and_paging(catalog):
    for lang in ('en', 'ja'):
        for index in range(12):
            card_id = f'{lang}:chase-{index:02d}'
            name = 'Outsideonly' if index == 11 else 'Chase card'
            product = 100 + index + (100 if lang == 'ja' else 0)
            catalog.execute("INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language, variants_json, cardmarket_id) VALUES (?, ?, ?, 'chase', 'Chase expansion', ?, ?, '{\"normal\":true}', ?)", (card_id, card_id, name, str(index), lang, product))
            catalog.execute("INSERT INTO cards_fts (id, name, set_name, collector_number) VALUES (?, ?, 'Chase expansion', ?)", (card_id, name, str(index)))
            # Fresh sets need no seven-/thirty-day history to have chase cards.
            catalog.execute("INSERT INTO cardmarket_guide (id_product, trend, guide_date) VALUES (?, ?, ?)", (product, 200 - index, date.today().isoformat()))
    catalog.execute("INSERT INTO set_releases (language, set_id, release_date, fetched_at) VALUES ('en', 'chase', '2020-01-01', 'x')")
    catalog.commit()
    expected = [f'en:chase-{i:02d}' for i in range(10)]
    found = search(catalog, preset='new_set', sets=['en:chase'])
    assert ids(found) == expected and found.total == 10
    assert all(card.market.avg7 is None for card in found.items)
    pages = [search(catalog, preset='new_set', sets=['en:chase'], limit=4, offset=i) for i in (0, 4, 8)]
    assert [item for page in pages for item in ids(page)] == expected
    assert {page.total for page in pages} == {10}
    # Japanese sets without a release date also work when explicitly selected.
    assert search(catalog, preset='new_set', sets=['chase'], language='ja').total == 10
    assert search(catalog, preset='new_set', sets=['en:chase', 'ja:chase']).total == 20
    assert search(catalog, preset='new_set', q='ja:chase').total == 10
    # Text, price and ownership only narrow the original top ten.
    assert search(catalog, preset='new_set', sets=['en:chase'], q='outsideonly').total == 0
    assert search(catalog, preset='new_set', sets=['en:chase'], max_price=189).total == 0
    assert search(catalog, preset='new_set', sets=['en:chase'], ownership='only_owned', owned_ids=['en:chase-11']).total == 0
    assert ids(search(catalog, preset='new_set', sets=['en:chase'], ownership='only_owned', owned_ids=['en:chase-02'])) == ['en:chase-02']
    assert ids(search(catalog, preset='new_set', language='en')) == ['b']
    # Stable identity breaks equal-price ties, including across page boundaries.
    catalog.execute('UPDATE cardmarket_guide SET trend=200 WHERE id_product BETWEEN 100 AND 111')
    assert ids(search(catalog, preset='new_set', sets=['en:chase'])) == expected
