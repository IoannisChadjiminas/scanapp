"""Read-only breakdown of legacy snapshot fair-ask/page-trend gaps.

Run from api: PYTHONPATH=. python scripts/valuation_gap_diagnostics.py
This deliberately does not measure the revised price-file gap or accuracy.
"""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import get_settings
from app.valuation_history import (
    DAILY, GUIDE_LABELS, REFERENCE_SOURCES, fair_ask, page_trend, positive, reliable,
)


def diagnose(connection):
    connection.row_factory = sqlite3.Row
    outliers, japanese = [], []
    groups = defaultdict(list)
    total = 0
    for row in connection.execute("SELECT * FROM cardmarket_snapshots"):
        prices = json.loads(row["prices_json"])
        ask, trend = fair_ask(prices), page_trend(prices)
        if not positive(ask) or not positive(trend):
            continue
        total += 1
        gap = ask / trend
        offers = [p for p in prices
                  if p.get("currency", "EUR") == "EUR" and positive(p.get("amount"))
                  and p.get("label") not in GUIDE_LABELS
                  and not DAILY.fullmatch(str(p.get("label") or ""))
                  and p.get("source") not in REFERENCE_SOURCES]
        count = len(offers)
        band = "<2" if ask < 2 else "2–20" if ask <= 20 else "20–100" if ask <= 100 else ">100"
        params = parse_qs(urlparse(row["sample_key"]).query)
        language = params.get("language", ["unspecified"])[0]
        reverse = any(v.upper() == "Y" for v in params.get("isReverseHolo", []))
        item = {
            "fair_ask": ask, "page_trend": trend, "page_gap": gap,
            "band": band, "offer_count": count,
            "reliable_count": sum(reliable(str(p.get("label") or "")) for p in offers),
            "language": language, "finish": "reverse" if reverse else "plain",
            "sample_key": row["sample_key"],
            "observed_at": row["observed_at"] or row["fetched_at"],
        }
        if not .5 <= gap <= 2:
            outliers.append(item)
            bucket = "3+" if count >= 3 else str(count)
            groups[(language, band, bucket)].append(item)
        if language == "7" and gap < .25:
            japanese.append(item)
    review = sorted(japanese, key=lambda item: item["page_gap"])[:10]
    for item in review:
        product = item["sample_key"].split("?", 1)[0]
        rows = connection.execute(
            "SELECT id,name,cardmarket_id,language FROM cards WHERE cardmarket_url=?", (product,)
        ).fetchall()
        item["catalogue_matches"] = [dict(row) for row in rows]
        item["review_status"] = "pending_manual_cardmarket_check"
    return {
        "definition": "Legacy page-gap diagnostic for the original 140 outliers; not the revised "
                      "price-file gap and not predictive accuracy. Listing counts exclude headers "
                      "and chart averages. Bands use fair ask in EUR.",
        "eligible_reads": total,
        "outliers_outside_0_5_2": len(outliers),
        "by_language_price_band_and_listing_count": [
            {"language": key[0], "band": key[1], "offer_count_bucket": key[2],
             "n": len(items), "below_0_25": sum(i["page_gap"] < .25 for i in items),
             "above_4": sum(i["page_gap"] > 4 for i in items)}
            for key, items in sorted(groups.items())
        ],
        "japanese_below_0_25_count": len(japanese),
        "japanese_manual_review": review,
    }


def main():
    path = Path(get_settings().catalog_sqlite).resolve()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        print(json.dumps(diagnose(connection), indent=2, ensure_ascii=False))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
