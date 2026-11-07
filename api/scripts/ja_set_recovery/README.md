# Local Japanese set recovery collector

Run on the owner's Apple Silicon Mac, using visible Chrome and a dedicated
persistent profile. No staging scraper, proxy or staging credentials are used.

## Start

From the `scanapp` repository root:

```bash
./scripts/setup-local-scraper.sh
.venv-scraper/bin/python api/scripts/ja_set_recovery/local_scraper.py
```

The listener binds only to `127.0.0.1:8000`. Its private bearer key is stored
mode `0600` in the ignored run directory. Chrome uses
`~/Library/Application Support/PokeSingle/CardmarketScraperProfile`, separate
from personal Chrome. Check `/health` for readiness and `/status` for lane state.
Use Python 3.13 in `.venv-scraper`; the pinned dependencies do not build on 3.14.
`local_scraper.py --check-browser` checks Chrome on `about:blank` without contacting Cardmarket.

## Collect all mapped sets in one resumable queue

The run registry contains all 336 target groups. Create/extend
`data/catalogue-gaps/ja-set-recovery-20261029-v3/listing-seeds.json` with **observed,
verified set URLs**, one entry per group, in registry priority order:

```json
[
  {
    "group_id": "ja-ref-67",
    "url": "https://www.cardmarket.com/en/Pokemon/Expansions/MEGA-Starter-Set-Mega-Gengar-ex",
    "source": "Observed expansion link; record source evidence path here"
  }
]
```

Do not infer set slugs from names or reuse ambiguous set codes. The collector
accepts expansion landing pages, `/Products/Singles/SET` listings, and numeric
`/Products/Singles?idExpansion=ID&site=N` listings. Expansion pages return their
observed singles-list link; the collector follows it and all observed pagination
links, maintaining the set and filters. No request to individual offer pages is
needed to enumerate singles.

In a second terminal:

```bash
.venv-scraper/bin/python api/scripts/ja_set_recovery/collect_listings.py \
  --manifest data/catalogue-gaps/ja-set-recovery-20261029-v3/listing-seeds.json \
  --max-pages 20
```

Repeat the same command to resume. `--max-pages` is a checkpoint budget, not a
release boundary. Use a larger budget for the full mapped queue. One process
lock protects the ledger, one local browser lane serializes requests, and the
server waits at least one second between listing navigations. A timeout, wrong
page or other failure stops the run with the current page pending; a rate limit
waits for the server's `Retry-After` and resumes that page. It never marks an
incomplete group complete. HTTP failures preserve previous checkpoints; do not
rotate sessions to avoid a cooldown.

Outputs in the ignored run directory:

- `listing-progress.json`: pending URLs, completed page evidence, unique products per group.
- `source-pages/GROUP/*.json`: timestamped parser results with content hashes.
- `cardmarket-products.jsonl`: deduplicated product URLs, names, group and source evidence.
- `listing-report.json`: listed groups, products, and every group without an observed set URL.

Cardmarket can serve the same listing and product routes under several
interface locales. The collector canonicalizes observed listing URLs to `/en/`
while preserving their filters, and canonicalizes product URLs to `/en/` so
each product is stored once per group. It prefers the English product name when
available. Page evidence retains the original locale URLs.

These are acquisition records. They are not verified catalogue mappings and do
not update images, vectors, databases or phone-index selectors. A group marked
`complete` here means all discovered listing pages were visited; reconcile its
products against the authoritative checklist before declaring card coverage.
A collector restart reuses completed page evidence rather than fetching it again.
Do not run a second collector/client while a batch is active.

## Collect shared review pools after the mapped queue

The 29-row `shared-listing-review-queue.json` is intentionally not a
`collect_listings.py` manifest: a URL can relate to several audit groups, and
that relationship does not establish exact card membership. After every
mapped seed group has completed, run the deduplicated pool collector:

```bash
.venv-scraper/bin/python api/scripts/ja_set_recovery/collect_shared_listings.py \
  --queue data/catalogue-gaps/ja-set-recovery-20261029-v3/shared-listing-review-queue.json \
  --max-pages 10000
```

It reuses exact URL pages from `listing-progress.json` and fetches uncached
pool URLs once, following observed pagination. It refuses to run while the
mapped queue is incomplete or paused, and shares the same process lock and
local Chrome lane. Observed listing and pagination URLs are normalized to
`/en/` while preserving filters; previously cached translated pages are
refetched in English before their names are kept. Outputs are `shared-listings-progress.json`,
`shared-listings-report.json`, and `shared-listings-products.jsonl`; product
rows retain source identity and candidate group IDs with
`membership_verified: false`. These are review evidence, not group mappings.
The batch now stays alive at a challenge and checks the same visible tab every
second. After the owner clears the challenge, it confirms the page and
continues automatically. Use `--no-wait-for-owner` only when you want the
collector to exit at the challenge instead.

## Cloudflare: owner action only

On any human-verification challenge the collector keeps the same visible tab
open and waits for owner action. **It does not click, solve, reload or bypass the
challenge.** Complete the checkbox manually there. The running batch checks that
same tab, set and filters every second; once the page shows catalogue
content, it reads the cleared HTML and continues without navigating away. If the
collector exited earlier, rerun the same command with `--confirm` after manually
clearing the tab. If the server/browser was lost, do not claim the old session
was confirmed; explicitly review/reset that paused job before restarting it.

For an individual diagnostic request, `local_client.py listing GROUP URL
--session-id SESSION` saves one response. `local_client.py confirm URL
--session-id SESSION` confirms a manual challenge; it does not update the batch
ledger, so use the batch's `--confirm` for paused batches.

## Validation on 29 October 2026

Live local Chrome returned 23 products each from MBG and MBD, by following their
expansion pages to singles listings: 44 numbered products and two basic Energy
products. Exact Gengar `mBG003` and Diancie `mBD005` URLs were present. A numeric
Eevee Heroes listing returned 30 products and an observed next-page link.
The current manifest contains 276 observed collection routes after checking the
800-entry Cardmarket master index. Another 59 groups have held shared/combined/pool
candidates, and Creatures Deck has no confirmed route. See
`docs/experiments/japanese-set-routing-update-20261029.md` and the run's
`seed-discovery-review.json`; route discovery is separate from card completeness.

`discover_seeds.py` reproducibly matches the frozen index and writes a proposal
and review queue; `--apply` preserves/backups existing seeds. The review queue is
not directly consumable by the one-group collector. Use the routing update for
its required many-group adapter and the acquisition order.

Focused regression command:

```bash
.venv-scraper/bin/python -m pytest scraper api/scripts/ja_set_recovery/test_collect_listings.py api/scripts/ja_set_recovery/test_discover_seeds.py -q
```
