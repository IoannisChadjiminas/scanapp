"""Numeric observations for valuation backtests, in the local catalogue DB.

No users or seller labels are retained. Each accepted priced observation joins
the snapshot transaction. An observation timestamp identifies a read: retries
cannot manufacture extra samples. Empty reads never become zero-euro prices.
"""

import math
import re

SCHEMA = """
CREATE TABLE IF NOT EXISTS valuation_listing_history (
    sample_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    fair_ask REAL,
    page_trend REAL,
    guide_trend REAL,
    guide_date TEXT,
    parser_version TEXT,
    PRIMARY KEY (sample_key, observed_at)
)
"""

GUIDE_LABELS = {"From", "Trend", "7-day", "30-day", "Available"}
REFERENCE_SOURCES = {"cardmarket_file", "tcgdex", "tcgplayer"}
SELLER_STATUSES = {"Professional", "Power Seller", "Professional Power Seller"}
SALES = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([kKmM])?\s+sales$")
DAILY = re.compile(r"^Avg \d{2}\.\d{2}\.\d{4}$")


def positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def reliable(label):
    for token in label.split("·"):
        token = token.strip()
        if token in SELLER_STATUSES:
            return True
        match = SALES.fullmatch(token)
        if match:
            scale = {"k": 1000, "m": 1000000}.get((match[2] or "").lower(), 1)
            if float(match[1].replace(",", ".")) * scale >= 100:
                return True
    return False


def fair_ask(prices):
    """Mirror Flutter marketBrief: qualified cheapest three within 2x, else low."""
    offers, qualified = [], []
    for quote in prices:
        label, amount = str(quote.get("label") or ""), quote.get("amount")
        if (quote.get("currency", "EUR") != "EUR" or not positive(amount)
                or label in GUIDE_LABELS or DAILY.fullmatch(label)
                or quote.get("source") in REFERENCE_SOURCES):
            continue
        offers.append(amount)
        if reliable(label):
            qualified.append(amount)
    qualified.sort()
    selected = [v for v in qualified if v <= qualified[0] * 2][:3]
    return sum(selected) / len(selected) if selected else min(offers, default=None)


def page_trend(prices):
    return next((q["amount"] for q in prices if q.get("label") == "Trend"
                 and q.get("currency", "EUR") == "EUR" and positive(q.get("amount"))), None)


def record_read(conn, key, stamp, prices, parser_version=None, *, capture_guide=True):
    from app.price_sources import guide_trend_for_url

    trend, date = guide_trend_for_url(conn, key) if capture_guide else (None, None)
    conn.execute(
        """INSERT INTO valuation_listing_history
           (sample_key, observed_at, fair_ask, page_trend, guide_trend, guide_date, parser_version)
           VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
        (key, stamp, fair_ask(prices), page_trend(prices), trend, date, parser_version),
    )
