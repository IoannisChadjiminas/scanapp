# P0 valuation measurement — 29 October 2026

Complete findings are recorded in the Flutter sibling's
`docs/price-valuation-plan.md`, section **P0 execution report — 29 October
2026**. The original plan came from `origin/claude/fervent-hopper-jps8qi`.
No app code changed.

`staging-audit.json` contains the actual aggregate-only read-only report from
the staging pricing API and configured PlanetScale history sink: 474 latest
snapshots, no retained earlier reads, and zero guide/sales/import-day history
rows. There are zero eligible backtest pairs; no listing/gap lifetime can be
calibrated. Latest-read gap diagnostics are not forecast accuracy.

The history failure is `conn.executemany` on psycopg 3.3.6, which provides
batching on a cursor instead. The local repair is in `api/app/price_history.py`.
Real PostgreSQL coverage is in `api/tests/test_internal_portfolio_postgres.py`.

`api/app/valuation_history.py` adds numeric history for accepted listing reads
in the same transaction as the snapshot. Startup provisions its local SQLite
table. No users, holdings, seller labels or analytics events are stored.
Reads deduplicate by sample key/timestamp. On first overwrite, the previous
snapshot is retained without attaching today's guide to the old read.
No live deployment, backfill, restart or configuration change was performed.

After staging deployment, verify that guide/import-day history appears after
a normal nightly import and listing history appears after ordinary phone
reads. Leave the paid scraper off. From `api/`:

```sh
PYTHONPATH=. python scripts/valuation_backtest.py --configured-history
```

For a local fixture with guide history in the same SQLite file:

```sh
PYTHONPATH=. python scripts/valuation_backtest.py --catalog /absolute/path/catalog.sqlite
```

Both paths use read-only connections. PostgreSQL access bypasses app/schema
initializers. Output contains aggregates with no product URLs or inventory.
This audit was executed with module sources supplied over SSH stdin, without
copying code into the running container.

The evaluator compares all chronological pairs at least three days apart.
Common-cohort A/B/C errors are stratified by complete-day ages 3–7, 8–14,
15–30, 31–60, 61+, language, condition, finish, later-price band, and their
joint groups. Percentiles interpolate linearly. Overlapping pairs are not
independent. Unknown language/condition remains explicit. It compares raw,
[0.5, 2] and [0.75, 1.5] gaps, with guarded variants rejecting outside
[0.25, 4]. Recommendations stay unset for human assessment.

Validation: 150 focused SQLite/pricing/history/market-stat tests and 4 real
PostgreSQL integration tests passed. PostgreSQL used a disposable loopback
database ending in `_test`; no remote migrations ran.

Remaining: deploy the prepared capture/writer changes, verify writes, collect
repeat reads, confirm page/file trend and finish parity, then choose the
listing/gap crossovers and clamp from median/p90 errors and sample counts.
Two to four weeks can inform short windows; validating a 60-day lifetime
requires observations spanning that interval.
