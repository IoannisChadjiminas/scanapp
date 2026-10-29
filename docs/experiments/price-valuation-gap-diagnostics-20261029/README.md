# Gap diagnostics — staging, 29 October 2026

These are the original **fair ask / page-header trend** gaps, requested to
investigate the earlier 140 outliers. They do not measure the revised
fair ask / price-file trend gap and are not predictive accuracy results.
The read-only staging query used existing `cardmarket_snapshots`; no scraper,
PC helper, paid reads or database writes were started.

Of 451 eligible reads, 140 fall outside [0.5, 2]. Price bands use the fair ask:

| Fair ask (EUR) | Outliers |
| --- | ---: |
| Below 2 | 83 |
| 2–20 | 21 |
| 20–100 | 16 |
| Above 100 | 20 |

| Listing rows | Outliers |
| --- | ---: |
| 1 | 7 |
| 2 | 2 |
| 3 or more | 131 |

Listing counts exclude guide headers and chart averages. A row count does not
prove correct language/finish/product mapping or seller independence. The JSON
contains the full language × band × count breakdown and the ten lowest Japanese
gaps selected for manual review (12 Japanese reads are below 0.25).

## Manual review status

**Pending.** Cardmarket returned a security verification page in the manual
Haunter tab; automated page opens were also unavailable. None of the ten reads
is certified correct or incorrect. Their URLs, amounts, timestamps and pending
status are recorded in `staging-gap-diagnostics.json`.

The local SQLite `cards` table returned no catalogue matches for these URLs.
The deployed catalogue is loaded from the cloud into application memory; the
empty local lookup is not evidence of a mapping bug. Confirm product identity,
Japanese language, finish, seller/listing filters and amounts against the live
pages before treating the diagnostic gate for P3a as complete.

## Evaluator correction

`valuation_backtest.py` now evaluates method C as earlier fair ask × (later
price-file trend / earlier price-file trend). It never substitutes the earlier
page-header trend. Missing earlier file trends exclude C pairs. The [0.25, 4]
guard rejects an outlying gap and falls back to B rather than clamping it;
unclamped C remains available. Guarded/clamped comparisons retain the same
cohort through fallback so rejection cannot improve accuracy by dropping cases.

Fifteen valuation-history tests pass, including deliberately different page and
file trends, missing earlier file trends, and rejected-gap fallback. Temporal
calibration still needs repeated observations at least three days apart. No
expiry or guard threshold has been fitted from this snapshot report. Historical
file lookup uses local catalogue URL/product mappings; a cloud-backed catalogue
with no local mappings can omit older uncaptured-guide pairs, so inspect cohort
coverage before interpreting a future report.

Run the diagnostic in the API environment with:

```sh
PYTHONPATH=. python scripts/valuation_gap_diagnostics.py
```

This branch changes read-only tooling and reporting. It does not deploy API
changes. Include the already merged history PR #93 in the next authorized
production deployment, following the rollout plan's history-write checks.
