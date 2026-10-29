from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from app.cardmarket import write_snapshot
from app.db import connect, init_catalog
from app.valuation_history import fair_ask, page_trend

URL = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu?language=1&minCondition=2'
spec = importlib.util.spec_from_file_location('valuation_backtest', Path(__file__).parents[1] / 'scripts/valuation_backtest.py')
backtest_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backtest_module)


def offer(amount, label='Seller · 100 sales', **extra):
    return dict(label=label, amount=amount, currency='EUR', **extra)


def test_fair_ask_matches_app_selection():
    quotes = [offer(1, 'Trend'), offer(.1, 'From'), offer(.1, 'Avg 01.10.2026'),
              offer(.1, 'Reference', source='cardmarket_file'), offer(.2, 'Seller · 1 sales'),
              offer(4), offer(5, 'Seller · Professional'), offer(6, 'Seller · 1,2k sales'), offer(99)]
    assert fair_ask(quotes) == 5
    assert fair_ask([offer(1, 'Private'), offer(2, 'Private')]) == 1
    assert fair_ask([dict(label='Private', amount=1, currency='USD'), offer(4)]) == 4
    assert fair_ask([offer(float('nan')), offer(True), offer(0), offer(1, 'Trend')]) is None
    assert page_trend(quotes) == 1


def test_history_deduplicates_and_joins_snapshot_transaction(tmp_path):
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    quotes = [offer(20), offer(16, 'Trend')]
    for _ in range(2):
        write_snapshot(conn, URL, quotes, observed_at='2026-10-01T00:00:00Z')
    write_snapshot(conn, URL, [offer(22.5), offer(18, 'Trend')], observed_at='2026-10-11T00:00:00Z')
    write_snapshot(conn, URL, quotes, observed_at='2026-09-01T00:00:00Z')
    assert conn.execute('SELECT COUNT(*) FROM valuation_listing_history').fetchone()[0] == 2
    write_snapshot(conn, URL, [], observed_at='2026-10-12T00:00:00Z', allow_empty=True)
    assert conn.execute('SELECT COUNT(*) FROM valuation_listing_history').fetchone()[0] == 2
    write_snapshot(conn, URL, quotes, observed_at='2026-10-13T00:00:00Z', commit=False)
    conn.rollback()
    assert conn.execute('SELECT COUNT(*) FROM valuation_listing_history').fetchone()[0] == 2
    assert conn.execute('SELECT observed_at FROM cardmarket_snapshots').fetchone()[0] == '2026-10-11T00:00:00Z'


def test_backtest_known_market_move_and_common_cohort():
    reads = [dict(sample_key=URL, observed_at='2026-10-01T00:00:00Z', fair_ask=20, page_trend=999),
             dict(sample_key=URL, observed_at='2026-10-11T00:00:00Z', fair_ask=22.5, page_trend=18)]
    result = backtest_module.backtest(reads, lambda read: 16 if '10-01' in read['observed_at'] else 18)
    cohort = result['common_cohort']
    assert cohort['A_frozen']['median_ape_pct'] == pytest.approx(11.111111)
    assert cohort['B_trend']['median_ape_pct'] == pytest.approx(20)
    assert cohort['C_unclamped']['p90_ape_pct'] == 0
    assert result['strata']['age']['8–14']['pairs'] == 1
    missing = backtest_module.backtest(reads, lambda read: None)
    assert missing['all_pairs']['A_frozen']['n'] == 1
    assert missing['common_cohort']['pairs'] == 0
    assert missing['recommendations']['status'] == 'insufficient_history'


@pytest.mark.parametrize(('days', 'bucket'), [(3, '3–7'), (7.9, '3–7'), (8, '8–14'),
    (15, '15–30'), (31, '31–60'), (60.9, '31–60'), (61, '61+')])
def test_age_buckets(days, bucket):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    reads = [dict(sample_key=URL, observed_at=start.isoformat(), fair_ask=1, page_trend=1),
             dict(sample_key=URL, observed_at=(start + timedelta(days=days)).isoformat(), fair_ask=1)]
    assert backtest_module.backtest(reads, lambda r: 1)['strata']['age'][bucket]['pairs'] == 1


def test_clamp_rejection_and_percentile():
    reads = [dict(sample_key=URL, observed_at='2026-10-01T00:00:00Z', fair_ask=2.6, page_trend=1),
             dict(sample_key=URL, observed_at='2026-10-11T00:00:00Z', fair_ask=2)]
    cohort = backtest_module.backtest(reads, lambda r: 1)['common_cohort']
    assert cohort['C_0.5_2']['median_ape_pct'] == 0
    reads[0]['fair_ask'] = .1
    cohort = backtest_module.backtest(reads, lambda r: 1)['common_cohort']
    assert cohort['C_unclamped']['n'] == 1
    assert cohort['C_0.5_2']['n'] == 1
    assert cohort['C_0.5_2'] == cohort['B_trend']
    assert cohort['C_reject_0.25_4'] == cohort['B_trend']
    assert cohort['rejected_gaps'] == 1
    assert backtest_module.percentile([0, 10], .9) == 9


def test_audit_read_only_and_no_lookahead(tmp_path):
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    write_snapshot(conn, URL, [offer(20), offer(16, 'Trend')], observed_at='2026-10-01T00:00:00Z')
    write_snapshot(conn, URL, [offer(22.5)], observed_at='2026-10-11T00:00:00Z')
    conn.execute('PRAGMA query_only=ON')
    result = backtest_module.audit(conn)
    assert result['backtest']['all_pairs']['pairs'] == 1
    assert result['backtest']['common_cohort']['pairs'] == 0


def test_predeployment_snapshot_preserved_without_a_fabricated_guide(tmp_path):
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    write_snapshot(conn, URL, [offer(20), offer(16, 'Trend')], observed_at='2026-10-01T00:00:00Z')
    conn.execute('DELETE FROM valuation_listing_history')
    conn.commit()
    write_snapshot(conn, URL, [offer(22.5)], observed_at='2026-10-11T00:00:00Z')
    rows = conn.execute('SELECT * FROM valuation_listing_history ORDER BY observed_at').fetchall()
    assert len(rows) == 2
    assert rows[0]['fair_ask'] == 20
    assert rows[0]['guide_trend'] is None
    assert rows[0]['guide_date'] is None


def test_read_captures_reverse_guide_and_audit_fills_only_imported_days(tmp_path):
    from app.price_sources import import_guide
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    base = URL.split('?')[0]
    conn.execute('''INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number,
                   language, cardmarket_id, cardmarket_url) VALUES (?,?,?,?,?,?,?,?,?)''',
                 ('en:1', '1', 'Pikachu', 'base1', 'Base Set', '58', 'en', 100, base))
    for day in ('01', '11'):
        import_guide(conn, {'createdAt': f'2026-10-{day}T01:00:00+0000',
                           'priceGuides': [{'idProduct': 100, 'trend': 10, 'trend-holo': 20}]}, conn)
    reverse = URL + '&isReverseHolo=Y'
    write_snapshot(conn, reverse, [offer(25), offer(20, 'Trend')], observed_at='2026-10-01T02:00:00Z')
    write_snapshot(conn, reverse, [offer(25), offer(20, 'Trend')], observed_at='2026-10-11T02:00:00Z')
    row = conn.execute('SELECT guide_trend, guide_date FROM valuation_listing_history ORDER BY observed_at DESC').fetchone()
    assert row['guide_trend'] == 20
    assert row['guide_date'].startswith('2026-10-11')
    # No contemporaneous guide captured for Oct 1: recorded history must fill it.
    conn.execute('UPDATE valuation_listing_history SET guide_date=NULL,guide_trend=NULL')
    result = backtest_module.audit(conn)
    assert result['backtest']['common_cohort']['C_unclamped']['median_ape_pct'] == 0
    assert result['page_file_same_day_parity']['reverse']['n'] == 2
    conn.execute("DELETE FROM price_guide_import_days WHERE day='2026-10-11'")
    assert backtest_module.audit(conn)['backtest']['common_cohort']['pairs'] == 0


def test_method_c_never_uses_a_page_trend_when_earlier_file_is_missing():
    reads = [dict(sample_key=URL, observed_at='2026-10-01T00:00:00Z', fair_ask=20, page_trend=16),
             dict(sample_key=URL, observed_at='2026-10-11T00:00:00Z', fair_ask=22.5, page_trend=18)]
    result = backtest_module.backtest(reads, lambda r: None if '10-01' in r['observed_at'] else 18)
    assert result['all_pairs']['A_frozen']['n'] == 1
    assert result['all_pairs']['B_trend']['n'] == 1
    assert result['all_pairs']['C_unclamped']['n'] == 0
    assert result['common_cohort']['pairs'] == 0
