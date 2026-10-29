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

**Current-page checks completed on 29 October 2026.** Cardmarket's initial
security page cleared without solving a challenge. All ten exact saved URLs
were then opened in the visible browser. Their headings match the expected
products/expansions, and the reviewed low offers are Japanese NM/MT.

| Product | Current page From EUR | Current page trend EUR | First three offer prices EUR |
| --- | ---: | ---: | --- |
| Haunter sv2a 093 | 0.02 | 3.31 | 0.02, 0.02, 0.02 |
| Goldeen sv2a 118 | 0.02 | 0.53 | 0.02, 0.02, 0.02 |
| Magikarp sv2a 129 | 0.02 | 0.32 | 0.02, 0.02, 0.02 |
| Gholdengo ex sv3a 050 | 0.10 | 2.84 | 0.10, 0.10, 0.10 |
| Oddish sm10 002 | 0.09 | 3.59 | 0.09, 0.10, 0.15 |
| Greninja ex m6a 015 | 0.02 | 0.27 | 0.02, 0.02, 0.10 |
| Pikachu m6a 018 | 0.04 | 0.59 | 0.04, 0.30, 0.30 |
| Lurantis ex m5 004 | 0.02 | 0.21 | 0.02, 0.02, 0.05 |
| Nidoqueen m6 043 | 0.02 | 0.06 | 0.02, 0.02, 0.02 |
| Pidgeotto XY2 062 | 0.49 | 0.44 | 0.49, 0.50, 0.90 |

**From above means Cardmarket's current lowest offer**, not the app's saved
fair ask. No fair ask was recomputed from these three-offer samples. Saved
observations and their timestamps remain unchanged. Pidgeotto's saved 0.05
fair ask is not reproduced by today's offers; this alone does not prove a
historical parser error. Pikachu has one 0.04 offer followed by 0.30 offers,
which illustrates why lowest listing and fair ask cannot be interchanged.

Finish checks found qualifications: Oddish's Only Reverse switch is unchecked;
Haunter has a later seller comment mentioning pokeball reverse and links to
separate additional versions; Pidgeotto's first three offers are First Edition.
No reverse-only parameter was supplied in any of the ten saved sample URLs.
Do not certify these pages as a homogeneous finish series solely from their
URL or heading. The JSON records these per-product notes.

The large page-trend/listing gaps are visible on the marketplace itself for
several correctly named Japanese products. This rules out the assumption that
every small legacy gap necessarily means a wrong product URL. It does **not**
certify the cloud catalogue ID/finish used for the price-file denominator or
reconstruct the original seller rows. That mapping should be verified while
preparing P3a before carrying a saved price-file gap forward.

The local SQLite `cards` table returned no catalogue matches for these URLs.
The deployed catalogue is loaded from the cloud into application memory; the
empty local lookup is not evidence of a mapping bug.

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
