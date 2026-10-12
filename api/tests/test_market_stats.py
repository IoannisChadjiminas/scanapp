from datetime import date, timedelta
from types import SimpleNamespace
import json

import pytest

from app.db import connect, init_catalog
from app.market_stats import capabilities, rebuild
from app.price_sources import import_guide
from app.routes.cards import CardSearchBody, search_cards, search_cards_body

DAY = date(2026, 11, 10)


def request(conn):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dbs=SimpleNamespace(catalog=conn))))


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / 'market.sqlite')
    init_catalog(conn)
    conn.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language,cardmarket_id,variants_json) VALUES ('a','a','Pikachu','base','Base','1','en',1,'{\"normal\":true}')")
    conn.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language,cardmarket_id,variants_json) VALUES ('h','h','Holo','base','Base','2','en',1,'{\"holo\":true}')")
    conn.commit()
    yield conn
    conn.close()


def load(conn, day, trend=10, holo=20, avg1=1, history=True, **extra):
    payload = {'createdAt': day.isoformat()+'T02:00:00Z', 'priceGuides': [
        {'idProduct':1, 'trend':trend, 'trend-holo':holo, 'low':trend*.7,
         'avg1':avg1, 'avg1-holo':avg1, 'avg7':10, 'avg7-holo':20,
         'avg30':10, 'avg30-holo':20, **extra}]}
    import_guide(conn, payload, conn if history else None)


def cards(conn, **params):
    return {card.id: card for card in search_cards(request(conn), **params).items}


def test_fill_forward_baselines_and_sales_count_observed_days_not_rows(conn):
    # Older seed is the latest row on/before the target day, not an exact-day join.
    load(conn, DAY-timedelta(days=35))
    for age in range(30, -1, -1):
        load(conn, DAY-timedelta(days=age), trend=12 if age == 0 else 10, holo=18 if age == 0 else 20)
    assert conn.execute('SELECT COUNT(*) FROM price_history_daily').fetchone()[0] == 2
    a, h = cards(conn)['a'].market, cards(conn)['h'].market
    assert a.change_7d == pytest.approx(.2) and a.change_30d == pytest.approx(.2)
    assert h.change_7d == pytest.approx(-.1) and h.change_30d == pytest.approx(-.1)
    assert a.sales_days_30 == 30 and h.sales_days_30 == 30
    assert capabilities(conn) == {'change_7d':True, 'change_30d':True, 'liquidity_30d':True}
    assert [c.id for c in search_cards(request(conn), sort='change_30d').items] == ['a','h']
    assert [c.id for c in search_cards(request(conn), preset='steady_climbers').items] == ['a']
    # File-based rule would exclude a (avg7 == avg30); mature history now admits it.
    assert [c.id for c in search_cards(request(conn), preset='trending_up').items] == ['a']


def test_missing_import_receipt_leaves_liquidity_unknown(conn):
    load(conn, DAY-timedelta(days=31))
    for age in range(29,-1,-1):
        if age != 10: load(conn, DAY-timedelta(days=age))
    assert cards(conn)['a'].market.sales_days_30 is None
    assert cards(conn)['a'].market.change_30d == 0
    assert capabilities(conn)['liquidity_30d'] is False
    assert search_cards(request(conn), preset='steady_climbers').items == []


def test_young_history_and_import_failure_never_reuse_stale_stats(conn):
    load(conn, DAY)
    assert cards(conn)['a'].market.change_7d is None
    assert cards(conn)['a'].market.sales_days_30 is None
    assert not any(capabilities(conn).values())
    # Previously computed stats for the same guide day are invalidated on reimport.
    conn.execute("UPDATE card_market_stats SET trend_7d_ago=1")
    conn.commit()
    load(conn, DAY, history=False)
    assert cards(conn)['a'].market.change_7d is None


def test_weekly_drop_excludes_steady_climber_and_sales_still_required(conn):
    for age in range(30,-1,-1):
        trend = 10 if age >= 20 else 8 if age >= 10 else 12
        load(conn, DAY-timedelta(days=age), trend=trend)
    assert search_cards(request(conn), preset='steady_climbers').items == []
    assert cards(conn)['a'].market.change_30d == pytest.approx(.2)


def test_below_average_history_rule_needs_liquidity(conn):
    for age in range(30,-1,-1):
        load(conn, DAY-timedelta(days=age), trend=8 if age == 0 else 10, avg1=1)
    market = cards(conn)['a'].market
    assert market.below_average is True
    assert [c.id for c in search_cards(request(conn), preset='below_average').items] == ['a']
    for age in range(30,-1,-1):
        load(conn, DAY-timedelta(days=age), trend=8 if age == 0 else 10, avg1=None)
    assert cards(conn)['a'].market.sales_days_30 == 0
    assert cards(conn)['a'].market.below_average is False


def test_removed_product_does_not_fill_forward_sales_after_it_returns(conn):
    load(conn, DAY-timedelta(days=30))
    # The history writer marks disappearances with null figures.
    from app.price_history import record_guide
    record_guide(conn, (DAY-timedelta(days=10)).isoformat(), [{'id_product':2, 'trend':1}])
    load(conn, DAY)
    assert cards(conn)['a'].market.sales_days_30 is None


def test_tcgdex_eur_fallback_and_no_usd_or_malformed_prices(conn):
    conn.execute("INSERT INTO tcgdex_prices(card_id, cardmarket_json, tcgplayer_json, fetched_at) VALUES('a',?, ?, '2026-11-10')", (json.dumps({'unit':'EUR','trend':5,'avg7':4,'avg30':6}), '{"normal":{"marketPrice":100}}'))
    conn.execute("INSERT INTO tcgdex_prices(card_id, cardmarket_json, fetched_at) VALUES('h',?, '2026-11-10')", (json.dumps({'unit':'USD','trend':100}),))
    conn.commit()
    result = cards(conn, min_price=2, max_price=10)
    assert set(result) == {'a'}
    assert result['a'].market.source == 'tcgdex' and result['a'].market.change_7d is None
    load(conn, DAY, trend=9)
    assert cards(conn)['a'].market.trend == 9 and cards(conn)['a'].market.source == 'cardmarket_file'
    conn.execute('DELETE FROM cardmarket_guide')
    conn.execute("UPDATE tcgdex_prices SET cardmarket_json='invalid' WHERE card_id='a'")
    assert search_cards(request(conn), min_price=2).items == []


def test_ownership_filters_before_paging_and_counts(conn):
    assert [c.id for c in search_cards(request(conn), ownership='hide_owned', owned_ids=['a'], limit=1).items] == ['h']
    assert search_cards(request(conn), ownership='only_owned', owned_ids=[]).total == 0
    body = CardSearchBody.model_validate({'ownership':'only_owned', 'owned_ids':['a'], 'set':['en:base']})
    assert search_cards_body(request(conn), body).total == 1
    assert search_cards_body(request(conn), CardSearchBody(card_ids=['h'])).items[0].id == 'h'
