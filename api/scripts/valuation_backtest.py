"""Read-only P0 audit. Run from api with PYTHONPATH=. python scripts/valuation_backtest.py.

Uses configured staging paths unless --catalog is supplied. PostgreSQL history
is opened directly with a read-only transaction; no app startup, DDL, imports,
paid scraper requests, or private collection reads are performed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse

from app.valuation_history import fair_ask, page_trend, positive

BUCKETS = (("3–7", 3, 8), ("8–14", 8, 15), ("15–30", 15, 31),
           ("31–60", 31, 61), ("61+", 61, math.inf))
CLAMPS = {"C_unclamped": None, "C_reject_0.25_4": None, "C_0.5_2": (0.5, 2), "C_0.75_1.5": (0.75, 1.5)}


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def band(value):
    return "<2" if value < 2 else "2–20" if value <= 20 else "20–100" if value <= 100 else ">100"


def percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    return ordered[low] + (ordered[math.ceil(index)] - ordered[low]) * (index - low)


def summarize(rows):
    result = {"pairs": len(rows), "sample_keys": len({r['key'] for r in rows}),
              "rejected_gaps": sum(r.get("gap_rejected", False) for r in rows)}
    methods = ["A_frozen", "B_trend", *CLAMPS]
    for method in methods:
        errors = [r[method] for r in rows if method in r]
        result[method] = {"n": len(errors), "median_ape_pct": percentile(errors, .5) if errors else None,
                          "p90_ape_pct": percentile(errors, .9) if errors else None}
    return result


def backtest(reads, later_trend):
    grouped = defaultdict(list)
    invalid = 0
    for read in reads:
        when = stamp(read.get("observed_at"))
        if not when or not positive(read.get("fair_ask")):
            invalid += 1
            continue
        grouped[read["sample_key"]].append({**read, "when": when})
    all_rows, common = [], []
    for key, observations in grouped.items():
        observations.sort(key=lambda r: r["when"])
        for index, earlier in enumerate(observations):
            for later in observations[index + 1:]:
                age = (later["when"] - earlier["when"]).total_seconds() / 86400
                bucket = next((name for name, low, high in BUCKETS if low <= age < high), None)
                if bucket is None:
                    continue
                params = parse_qs(urlparse(key).query)
                # Unknown language/condition is not silently pooled with English NM.
                actual = later["fair_ask"]
                row = {"key": key, "age": bucket, "language": params.get("language", ["unspecified"])[0],
                       "condition": params.get("minCondition", ["unspecified"])[0], "band": band(actual),
                       "finish": "reverse" if any(v.upper() == "Y" for v in params.get("isReverseHolo", [])) else "plain",
                       "A_frozen": abs(earlier["fair_ask"] / actual - 1) * 100}
                trend = later_trend(later)
                if positive(trend):
                    row["B_trend"] = abs(trend / actual - 1) * 100
                    earlier_file_trend = later_trend(earlier)
                    if positive(earlier_file_trend):
                        gap = earlier["fair_ask"] / earlier_file_trend
                        row["C_unclamped"] = abs(trend * gap / actual - 1) * 100
                        row["gap_rejected"] = not .25 <= gap <= 4
                        for name, bounds in CLAMPS.items():
                            if name == "C_unclamped":
                                continue
                            # Match the app policy: rejected gaps fall back to
                            # the current trend, keeping the comparison cohort.
                            adjusted = 1 if row["gap_rejected"] else (
                                min(bounds[1], max(bounds[0], gap)) if bounds else gap)
                            row[name] = abs(trend * adjusted / actual - 1) * 100
                all_rows.append(row)
                if all(method in row for method in ["A_frozen", "B_trend", "C_unclamped"]):
                    common.append(row)
    strata = {}
    for dimension in ("age", "language", "condition", "finish", "band"):
        strata[dimension] = {value: summarize([r for r in common if r[dimension] == value])
                             for value in sorted({r[dimension] for r in common})}
    # Include every required age bucket even when there are no eligible pairs.
    strata["age"] = {name: summarize([r for r in common if r["age"] == name]) for name, _, _ in BUCKETS}
    joint = defaultdict(list)
    for row in common:
        joint[(row['age'], row['language'], row['condition'], row['finish'], row['band'])].append(row)
    strata['age_language_condition_finish_band'] = [
        dict(zip(('age', 'language', 'condition', 'finish', 'band'), key), **summarize(rows))
        for key, rows in sorted(joint.items())]
    return {"eligible_keys": len(grouped), "invalid_or_unpriced_reads": invalid,
            "all_pairs": summarize(all_rows), "common_cohort": summarize(common), "strata": strata,
            "recommendations": {"status": "requires_review" if common else "insufficient_history",
                                "listing_max_age_s": None, "gap_max_age_s": None, "clamp": None},
            "methodology": "All ordered pairs >=3 days; fractional elapsed days; 60+ means >60 complete days. "
                "C uses price-file trends at both read dates, never page-header trends. "
                "Strata use the same A/B/C cohort. Guarded methods fall back to B outside [0.25,4]. "
                "Price bands use later fair ask. Pairs overlap and are not independent. "
                "Errors are absolute prediction/actual minus one; p90 uses linear interpolation."}


def audit(catalog, history=None):
    catalog.row_factory = sqlite3.Row
    tables = {r[0] for r in catalog.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    snapshots = list(catalog.execute("SELECT * FROM cardmarket_snapshots"))
    reads = {}
    gaps = defaultdict(list)
    for row in snapshots:
        prices = json.loads(row["prices_json"])
        read = {"sample_key": row["sample_key"], "observed_at": row["observed_at"] or row["fetched_at"],
                "fair_ask": fair_ask(prices), "page_trend": page_trend(prices)}
        reads[(read["sample_key"], read["observed_at"])] = read
        if positive(read['fair_ask']) and positive(read['page_trend']):
            params = parse_qs(urlparse(read['sample_key']).query)
            language = params.get('language', ['unspecified'])[0]
            finish = 'reverse' if any(v.upper() == 'Y' for v in params.get('isReverseHolo', [])) else 'plain'
            gaps[(language, finish)].append(read['fair_ask'] / read['page_trend'])
    if "valuation_listing_history" in tables:
        for row in catalog.execute("SELECT * FROM valuation_listing_history"):
            reads[(row["sample_key"], row["observed_at"])] = dict(row)
    products = {r["cardmarket_url"]: r["cardmarket_id"] for r in catalog.execute(
        "SELECT cardmarket_url, cardmarket_id FROM cards WHERE cardmarket_id IS NOT NULL")}
    imported = set()
    history_rows = defaultdict(list)
    counts = {}
    target = history or catalog
    for name in ("price_history_daily", "price_sales_daily", "price_guide_import_days"):
        if history is None and name not in tables:
            counts[name] = None
        else:
            counts[name] = target.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
    if counts["price_guide_import_days"]:
        imported = {str(r["day"])[:10] for r in target.execute("SELECT day FROM price_guide_import_days")}
    # Only fetch guide history for products represented in reads.
    ids = set(products.get(key.split("?", 1)[0]) for key, _ in reads) - {None}
    if counts["price_history_daily"] and ids:
        placeholder = "%s" if history is not None else "?"
        sql = "SELECT id_product, day, trend, trend_holo FROM price_history_daily WHERE id_product IN (" + ",".join([placeholder] * len(ids)) + ") ORDER BY day"
        for row in target.execute(sql, tuple(ids)):
            history_rows[row["id_product"]].append(dict(row))

    def later_trend(read):
        day = read["observed_at"][:10]
        # A trend captured at read time is valid only for that price-file day.
        if str(read.get("guide_date") or "")[:10] == day and positive(read.get("guide_trend")):
            return read["guide_trend"]
        # Fill forward changed rows only on a day whose import succeeded.
        if day not in imported:
            return None
        key = read["sample_key"]
        rows = history_rows[products.get(key.split("?", 1)[0])]
        prior = [r for r in rows if str(r["day"])[:10] <= day]
        if not prior:
            return None
        reverse = any(v.upper() == "Y" for v in parse_qs(urlparse(key).query).get("isReverseHolo", []))
        return prior[-1]["trend_holo" if reverse else "trend"]

    parity = defaultdict(list)
    for read in reads.values():
        trend = later_trend(read)
        if positive(trend) and positive(read.get("page_trend")):
            reverse = "reverse" if "isReverseHolo=Y" in read["sample_key"] else "plain"
            parity[reverse].append(abs(read["page_trend"] / trend - 1) * 100)
    return {"snapshot_count": len(snapshots), "read_count_including_history": len(reads),
            "snapshot_gap_diagnostics_not_a_backtest": [
                {"language": language, "finish": finish, "n": len(values),
                 "median_gap": percentile(values, .5), "p10_gap": percentile(values, .1),
                 "p90_gap": percentile(values, .9),
                 "outside_0.5_2": sum(not .5 <= gap <= 2 for gap in values),
                 "outside_0.25_4": sum(not .25 <= gap <= 4 for gap in values)}
                for (language, finish), values in sorted(gaps.items())],
            "history_counts": counts, "guide_import_days": sorted(imported),
            "guide_meta": [dict(r) for r in catalog.execute("SELECT guide_date,row_count,imported_at FROM cardmarket_guide_meta")],
            "page_file_same_day_parity": {finish: {"n": len(values), "median_difference_pct": percentile(values,.5),
                                                    "p90_difference_pct": percentile(values,.9)} for finish,values in parity.items()},
            "backtest": backtest(list(reads.values()), later_trend)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--configured-history", action="store_true", help="Read configured PlanetScale history, with no schema helpers")
    args = parser.parse_args()
    settings = None
    if args.catalog is None or args.configured_history:
        from app.config import get_settings
        settings = get_settings()
    path = args.catalog or settings.catalog_sqlite
    catalog = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    catalog.execute("PRAGMA query_only=ON")
    history = None
    try:
        if args.configured_history:
            import certifi
            import psycopg
            from psycopg.rows import dict_row
            url = settings.portfolio_database_url.get_secret_value().strip()
            if not url:
                raise SystemExit("No portfolio database configured")
            history = psycopg.connect(url, port=6432, sslmode="verify-full", sslrootcert=certifi.where(),
                                       connect_timeout=15, row_factory=dict_row)
            history.execute("SET TRANSACTION READ ONLY")
            history.execute("SET LOCAL statement_timeout = '30s'")
        print(json.dumps(audit(catalog, history), indent=2))
    finally:
        if history is not None:
            history.rollback()
            history.close()
        catalog.close()


if __name__ == "__main__":
    main()
