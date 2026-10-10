from app import price_history
from app.cardmarket import write_snapshot
from app.db import connect, init_catalog
from app.price_sources import GUIDE_COLUMNS, import_guide

URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"


def _guide(date, *entries):
    return {"createdAt": f"{date}T02:51:56+0200", "priceGuides": list(entries)}


def _conn(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def test_fields_match_the_price_file_columns():
    assert price_history.HISTORY_FIELDS == tuple(name.replace("-", "_") for name in GUIDE_COLUMNS)


def test_each_day_is_kept_and_unchanged_days_are_skipped(tmp_path):
    conn = _conn(tmp_path)
    import_guide(conn, _guide("2026-10-08", {"idProduct": 1, "trend": 4.0}, {"idProduct": 2, "trend": 1.0}), conn)
    import_guide(conn, _guide("2026-10-09", {"idProduct": 1, "trend": 4.0}, {"idProduct": 2, "trend": 1.5}), conn)
    import_guide(conn, _guide("2026-10-10", {"idProduct": 1, "trend": 4.5}, {"idProduct": 2, "trend": 1.5}), conn)
    assert [r["day"] for r in price_history.guide_history(conn, 1)] == ["2026-10-08", "2026-10-10"]
    assert [(r["day"], r["trend"]) for r in price_history.guide_history(conn, 2)] == [
        ("2026-10-08", 1.0),
        ("2026-10-09", 1.5),
    ]


def test_importing_the_same_day_twice_changes_nothing(tmp_path):
    conn = _conn(tmp_path)
    file = _guide("2026-10-08", {"idProduct": 1, "trend": 4.0})
    import_guide(conn, file, conn)
    import_guide(conn, file, conn)
    assert len(price_history.guide_history(conn, 1)) == 1


def test_a_failing_history_connection_does_not_stop_the_import(tmp_path):
    conn = _conn(tmp_path)
    broken = connect(tmp_path / "other.sqlite")
    broken.close()
    assert import_guide(conn, _guide("2026-10-08", {"idProduct": 1, "trend": 4.0}), broken) == 1
    assert conn.execute("SELECT COUNT(*) FROM cardmarket_guide").fetchone()[0] == 1


def test_the_sold_price_chart_is_kept_and_new_days_are_added(tmp_path):
    conn = _conn(tmp_path)
    price_history.bind(conn)
    try:
        offers = [{"label": "Near Mint", "amount": 5.0, "currency": "EUR"}]
        chart = [
            {"label": "Avg 08.10.2026", "amount": 4.0, "currency": "EUR"},
            {"label": "Avg 07.10.2026", "amount": 3.5, "currency": "EUR"},
        ]
        write_snapshot(conn, URL, offers + chart)
        write_snapshot(
            conn, URL, offers + [{"label": "Avg 09.10.2026", "amount": 4.2, "currency": "EUR"}] + chart[:1]
        )
        rows = conn.execute("SELECT day, price FROM price_sales_daily ORDER BY day").fetchall()
        assert [(r["day"], r["price"]) for r in rows] == [
            ("2026-10-07", 3.5),
            ("2026-10-08", 4.0),
            ("2026-10-09", 4.2),
        ]
    finally:
        price_history.bind(None)


def test_a_read_without_a_chart_stores_no_sales(tmp_path):
    conn = _conn(tmp_path)
    price_history.bind(conn)
    try:
        write_snapshot(conn, URL, [{"label": "Near Mint", "amount": 5.0, "currency": "EUR"}])
        assert conn.execute("SELECT COUNT(*) FROM price_sales_daily").fetchone()[0] == 0
    finally:
        price_history.bind(None)
