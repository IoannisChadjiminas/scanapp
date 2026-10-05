# Daily portfolio prices

Once a day, refresh the price of each product that is on someone's portfolio. Each card is the same request the scraper already serves. There is no second scraper and no listing-page price.

## Same scrape as one request

`POST /scrape` in `scraper/main.py` stays the only page load. The daily job sends the same body:

```json
{ "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/...", "session_id": "daily-..." }
```

`url` is a product URL. `cardmarket_product()` already rejects anything else. The filtered URL is the one a live read would send, built with `sample_key()` in `api/app/cardmarket.py` (`language`, `minCondition`, `isReverseHolo`, `isSigned`, `isFirstEd`, `sellerCountry`).

The response is the same `run_attempt()` result, parsed by `parse_cardmarket_html()`:

- `outcome`: `offers`, `empty`, `wrong_product`, `challenge_unsolved`, `rate_limited`, or `timeout`
- `rows`: the offer table
- `header`: the price summary already returned with those rows

The daily job stores that with the existing snapshot write (`cardmarket_snapshots`, keyed by `sample_key`). It does not download the product photo. `image` may still be the address already sitting in the HTML. The image file stays blocked, as it is today.

## What runs once a day

Add a scheduler in the scanapp API, `api/app/cardmarket_daily.py`, started from the FastAPI lifespan next to the existing proxy worker. It is a client of the Docker scraper, not another Chrome service.

`DAILY_PRICES_ENABLED` on the API service turns the night job on. Default is false, in `compose.dokploy.yaml` and in `api/app/config.py`. The lifespan schedules the task only when this is true and `SCRAPER_ENABLED` is true. Setting it false stops the night run and leaves live paid reads alone: a phone that dismissed a check can still escalate. The pacing values (`DAILY_GAP_MIN_S`, `DAILY_GAP_MAX_S`, `DAILY_GAP_STEP_S`, `DAILY_SESSION_PAGES`, `DAILY_SESSION_ROTATE_BEFORE_S`, `DAILY_BROWSERS`) sit on that same API environment list.

Each night:

1. Read the distinct portfolio product URLs from PlanetScale database `pokesingle-product`. The catalogue database stays read-only. `PORTFOLIO_DATABASE_URL` is set in the Dokploy environment for the API service and passed through `compose.dokploy.yaml`. One URL held by many users is one scrape. A product on nobody's portfolio is not scraped. Prices stay in the local snapshot table.
2. Skip a `sample_key` whose snapshot is already from today.
3. Reserve the attempt against the existing daily page and bandwidth caps before calling `/scrape`. Stop when the cap is full. Prefer holdings that were opened most recently.
4. Call `/scrape` one URL at a time while `DAILY_BROWSERS` is 1. A higher count is a later change, described under throughput.
5. Pace and rotate the sticky session from configuration, not from fixed 15-second and 30-minute constants. See below.
6. On `rate_limited` (HTTP 503), stop. The scraper is already in cooldown. Resume after `Retry-After` with a new `session_id` and the gap at its maximum.
7. On `challenge_unsolved`, retry that URL once with a new `session_id`. If it fails again, leave the last stored price and go on.
8. Do not run this while a photo scrape is using the same proxy account.

## Session spacing

The scraper already reads these from the environment. The daily job uses them. It does not replace them with literals.

| Setting | Default | Where | What it does |
|---|---:|---|---|
| `SCRAPER_PAGE_GAP_S` | 0 | `scraper/main.py` `wait_for_page_gap()` | Pause the scraper itself inserts. A live request starts when the browser is free. The night job does its own pacing |
| `SCRAPER_BROWSER_LIFETIME_S` | 1800 | `scraper/browser.py` `acquire_browser()` | How long the open Chrome is kept. DataImpulse keeps one `sessid` for about 30 minutes, so this stays at or under that |
| `SCRAPER_RATE_LIMIT_S` | 900 | `scraper/main.py` | Cooldown after `rate_limited` |
| `SCRAPER_ATTEMPT_SECONDS` | 25 | `scraper/browser.py` | Deadline for one page, including the Cloudflare click |

The daily job adds its own settings in `api/app/cardmarket_daily.py` and in the API service environment:

| Setting | Default | What it does |
|---|---:|---|
| `DAILY_GAP_MIN_S` | 2 | Gap after a clean `offers` or `empty` |
| `DAILY_GAP_MAX_S` | 60 | Gap after a challenge or a block |
| `DAILY_GAP_STEP_S` | 5 | How far the gap moves on each outcome |
| `DAILY_SESSION_PAGES` | 30 | Pages on one `session_id`, then a new id |
| `DAILY_SESSION_ROTATE_BEFORE_S` | 120 | New `session_id` this long before `SCRAPER_BROWSER_LIFETIME_S` |

`proxy_server(session_id)` pins one sticky address. `acquire_browser()` reuses that Chrome until the lifetime expires, and the next product is `cdp.get` in the same window. A new `session_id` is a new address and a new Cloudflare check, so the job keeps the id until one of these is true:

- `DAILY_SESSION_PAGES` products have been loaded on it
- the window is within `DAILY_SESSION_ROTATE_BEFORE_S` of `SCRAPER_BROWSER_LIFETIME_S`
- the outcome is `rate_limited` or a second `challenge_unsolved`

The gap starts at `DAILY_GAP_MIN_S`. The job sleeps only the part the scraper will not already wait: `max(0, gap - SCRAPER_PAGE_GAP_S)`, so the two pauses do not stack.

- `offers` or `empty`: `gap = max(DAILY_GAP_MIN_S, gap - DAILY_GAP_STEP_S)`
- `challenge_unsolved`, or a page that had to reload the check: `gap = min(DAILY_GAP_MAX_S, gap + DAILY_GAP_STEP_S)`. Two of these in a row also mint a new `session_id`.
- `rate_limited`: `gap = DAILY_GAP_MAX_S`, then a new `session_id` after the cooldown

A clean stretch therefore sits on the minimum gap and one address. A check or a block slows the next pages and, when it repeats, leaves that address.

A card added during the day still uses the live path: cache, phone, then one paid request if the phone is challenged. The night job only refreshes what is already held.

## Throughput

At the 2-second floor, one listing is that pause plus the page itself. A cleared page has been landing in about 5–10 seconds, so one browser finishes a listing in about 10 seconds. That is about 360 listings an hour and about 8,000 in a day. A portfolio of a few thousand distinct URLs fits in one night. 70,000 distinct URLs would take about 9 days on one browser, so a full catalogue refresh is not a one-night job at this setting. A challenge moves the pause up by 5 seconds at a time, and a block sets it to 60. The old 15-second constant is not a measured minimum. The page load already separates one request from the next.

`DAILY_BROWSERS` defaults to 1. It lives on the daily job, in the API service environment. Leave the scraper's `MAX_BROWSERS` at 1 until the daily job is actually run in parallel.

Raising `MAX_BROWSERS` alone does not open more windows. `acquire_browser()` in `scraper/browser.py` keeps a single `_held` Chrome and ignores a new proxy until that window expires, and `wait_for_page_gap()` is one clock for every request. A `DAILY_BROWSERS` above 1 needs both of these first:

- one held window per sticky `session_id`, each on its own exit address
- a page gap counted per session, so one browser's pause does not freeze the others

The photo runs are the size check. Fifteen windows on separate addresses left several that never opened a page. Four and seven finished. Growth goes 1, then a measured 4, and stops at 7 until a run shows a higher count still returns `offers`. Each extra window is its own sticky address and its own first Cloudflare check.

## Restart

The scheduler starts from the API lifespan in `api/app/main.py`, next to `ScraperWorker.start()`. It is `asyncio.create_task(...)` before `yield`, and the task is cancelled in the `finally` block. The lifespan returns as soon as the task is scheduled. The loop only posts to the Docker scraper, so it does not hold a browser inside the API process.

A deploy or a crash stops the loop mid-list. The next start reads snapshots again and skips every `sample_key` already written today, so a finished URL is not fetched twice. URLs with no snapshot today are the remainder.

## Measured traffic, 30 Sep–2 Oct 2026

DataImpulse residential usage for this window, summed from the export (`Traffic in Bytes`). Failed `NO_HOST_CONNECTION` rows add requests but no bytes.

| Host group | Requests | Traffic | Share |
|---|---:|---:|---:|
| Cloudflare challenge (`challenges.cloudflare.com` and the other `*.challenges.cloudflare.com` hosts, plus `csp-reporting`, insights, and radar) | 2,158 | 558.84 MB | 63.8% |
| Cardmarket (`www`, `static`, `product-images.s3`) | 1,736 | 290.90 MB | 33.2% |
| Google and other background hosts | 2,546 | 26.60 MB | 3.0% |
| Total | 6,440 | 876.35 MB | 100% |

The hosts that dominate:

- `challenges.cloudflare.com`: 554.09 MB across 694 requests, about 818 KB each.
- `www.cardmarket.com`: 200.55 MB across 690 requests, about 298 KB each.
- `static.cardmarket.com`: 86.49 MB across 1,010 requests, about 88 KB each.
- `product-images.s3.cardmarket.com`: 3.86 MB across 36 requests. Image bytes still leaked.
- `mtalk.google.com`: 12.33 MB across 1,516 requests. Chrome's own background traffic, not the offer table.

690 Cardmarket document requests carried 876.35 MB of proxy traffic with them, about 1.27 MB per page. At $1 per GB that sample is about $0.86.

Dropping the challenge download and `static.cardmarket.com` does not, by itself, reach 120 KB per page. This file still shows 298 KB on `www.cardmarket.com` for each of those 690 requests. That response is the document: the offer table, the inline price state, and the scripts Cardmarket writes into the HTML. `PRICE_BLOCKED` can drop the extra hosts. It cannot shrink this document. Plan with 298 KB per cleared page. A later export can show a lower `www` size only if some of those 298 KB were subresources served from the same host, which this file does not separate.

At 298 KB and $1 per GB:

- about 3,400 listings per 1 GB
- about 38,000 listings per 11 GB (€10 at about €0.92 per GB)
- about 20.4 GB for 70,000 listings, about $21

The 120 KB figure (about 8,500 listings per GB, about $8 for 70,000) stays a target for that second export, not a number this file supports. The change that moves the bill is still the same: stop repeating the 818 KB challenge, and stop loading `static.cardmarket.com`.

## What the browser downloads

`BLOCKED` in `scraper/browser.py` already drops images, video, fonts, and a few trackers. This export shows that was not enough. `static.cardmarket.com` still transferred 86 MB, product images still transferred 4 MB, and Chrome still talked to Google.

`chrome_launch_options()` currently passes only `--no-sandbox` and `--disable-dev-shm-usage`. Add these to that same `chromium_arg` list, so Chrome never opens the sockets:

- `--disable-background-networking`
- `--disable-sync`
- `--disable-client-side-phishing-detection`
- `--disable-default-apps`
- `--no-first-run`
- `--disable-component-update`

`mtalk.google.com` was 12.33 MB across 1,516 requests in this export. A CDP block drops the body after Chrome has already asked the proxy for the connection. These flags stop the background clients from starting. The Google host patterns stay in `PRICE_BLOCKED` as well, for any request that still leaves the browser.

Prices do not need stylesheets, but the first Cloudflare check does: `uc_gui_click_captcha` clicks the box on screen, and a page with no stylesheet can move that box.

Split the list in `browser.py`:

- `CHALLENGE_BLOCKED` is today's `BLOCKED`. Use it for a fresh window, until that window has returned `offers` once. `challenges.cloudflare.com` stays allowed on that first check only. That host is 63.8% of this bill when it runs on every page.
- `PRICE_BLOCKED` is `CHALLENGE_BLOCKED` plus `*.css`, `*.ico`, `*static.cardmarket.com*`, `*product-images.s3.cardmarket.com*`, `*challenges.cloudflare.com*`, `*cloudflareinsights*`, `*csp-reporting.cloudflare.com*`, `*radar.cloudflare.com*`, `*mtalk.google.com*`, `*android.clients.google.com*`, `*accounts.google.com*`, `*googleapis.com*`, `*googletagmanager*`, `*google-analytics*`, `*googlesyndication*`, and the tracker hosts already used by the photo runs (`*hotjar*`, `*sentry.io*`, `*segment.com*`, `*segment.io*`, `*onetrust*`, `*cookielaw*`, `*nr-data.net*`, `*newrelic.com*`, `*clarity.ms*`, `*adservice*`).

`run_attempt()` already calls `block_extra_resources()` after navigation. Change that call:

- The held window has not returned `offers` yet: block with `CHALLENGE_BLOCKED`.
- The held window has returned `offers` (`session.reused` and a clearance flag on `ChromeSession`): block with `PRICE_BLOCKED` before the next `cdp.get`. One sticky `session_id` is what keeps the next product off `challenges.cloudflare.com`.
- A later page probes as `challenge`: set the list back to `CHALLENGE_BLOCKED`, reload that URL once, click, and after `offers` put `PRICE_BLOCKED` back.

Never block the document. `probe()` decides the page from the offer rows (`.article-row`, `tr.article`) and the empty-state text. That is the useful part. `parse_cardmarket_html()` then reads the same HTML the single request reads. Scripts stay allowed on the challenge page so the check can finish. After clearance, `PRICE_BLOCKED` may block script hosts that are not the document.

## Single scrape

The night job only calls `POST /scrape`. The download changes belong in that path, in `scraper/browser.py` and `scraper/main.py`. A live price and a night price then load the same way.

Three changes:

1. Launch flags and the two block lists, as written above. A fresh window uses `CHALLENGE_BLOCKED` so the checkbox can be clicked. After that window has returned `offers` once, the next product uses `PRICE_BLOCKED`.
2. `block_extra_resources()` runs after `open()`. On a reused window `cdp.get` has already started the document, so `static.cardmarket.com`, the image host, and `challenges.cloudflare.com` can transfer before the block is set. Set the list, then navigate.
3. The paid worker in `api/app/cardmarket_scraper.py` sends `session_id: str(uuid.uuid4())` on every call. `acquire_browser()` keeps one Chrome and the proxy it was opened with for `SCRAPER_BROWSER_LIFETIME_S`, and the new id is ignored. A second product already stays on that address. A retry after `challenge_unsolved` or `rate_limited` also stays on it, until the 30 minutes end. `/scrape` returns `reused`. The worker keeps the same `session_id` while `reused` is true. It sends a new id only after `challenge_unsolved`, after `rate_limited`, or when the window was replaced. A new id closes the held window and opens the new proxy. The response body otherwise stays `rows`, `header`, and the image address.

The 2-to-60-second gap and the 30-page rotation stay on the night job. A live request does not take that pause. It starts when the browser is free.

## Phone WebView

With `cardmarket_webview_enabled` on, which is the default, a price the user is looking at comes from the phone. `InAppCardmarketReader` loads the product page in the WebView on that phone's address and cookie store. It posts the HTML to `POST /cardmarket/parse`. The API does not fetch the URL. `remember_phone_offers()` writes the same `cardmarket_snapshots` row as the paid browser, under the same `sample_key`, with parser `phone-offers-v1`. The paid browser writes `proxy-offers-v1`.

The background WebView opens for a visible card whose snapshot is older than `CARDMARKET_PRICE_FRESH_MINUTES` (15). A fresh row is shown as it is. One card load at a time, through the existing load lock.

The night job treats a phone row and a proxy row the same. Step 2 skips a `sample_key` already observed today, whichever parser wrote it. A card someone opened today is not fetched again that night. `write_snapshot()` keeps the newer `observed_at`, so a later phone read is kept and an older proxy result does not replace it. The same prices inside the fresh window do not move `observed_at`.

The phone stays on the user's address. Clearance was issued for that WebView, and a proxy would put the common read on the paid pool. The WebView never takes a proxy URL.

A challenge does not call the server at the same time. The sheet opens and the person can tap the checkbox. The challenge document is posted once to `POST /cardmarket/parse` so the server records that this session was challenged. That post does not enqueue a scrape. If they clear it, the phone reads the offers and the server is not called.

The server is called only after the phone gives up:

- They close the sheet (`challengeDismissed`), or the check times out (`challengeTimeout`). `cardsToEscalate` then calls `POST /cardmarket/escalations`.
- A second check inside `CARDMARKET_CHALLENGE_FALLBACK_MINUTES` (10) does not open the sheet again. The phone posts `POST /cardmarket/challenge-fallback`, and the same escalation runs.

With the WebView enabled and no recorded challenge, escalation stays refused.

A challenged phone stays on the same address for the tap. A new address is a new check, and the clearance cookie would then belong to the proxy address, so the next direct load sends a mismatched cookie. A network that cannot reach Cardmarket is still a server read: the Docker browser already has the proxy, and iOS WebKit does not take a per-view proxy. The phone's cookie does not clear the server Chrome, so sharing one sticky `session_id` between them does not help.

The phone page can drop the same extras the server drops. `InAppWebViewSettings.contentBlockers` is the list:

- Always: images, video, fonts, `product-images.s3.cardmarket.com`, and the tracker hosts. The offer rows are in the document. The image address in that document is enough.
- Until this WebView has returned offers once: leave stylesheets and `challenges.cloudflare.com` alone. The app taps the checkbox on screen. A script click restarts the check.
- After offers: block stylesheets and `static.cardmarket.com` as well. A later challenge title puts those two back for one reload.

The upload is `documentElement.outerHTML`, capped at 2 MB. Before the post, remove `style`, `svg`, and `img`, and remove `script` tags other than `chart-init-script`. The chart averages are read from that script. The offer table and the header stay. The server parser is unchanged.

## Tests

- A reused browser, after one `offers` result, sets the blocked list to `PRICE_BLOCKED` before the next navigation, including `static.cardmarket.com` and `challenges.cloudflare.com`.
- A challenge on a reused browser switches back to `CHALLENGE_BLOCKED` for one reload.
- A usage export after a reused run shows the next product pages without a matching `challenges.cloudflare.com` download.
- The daily job sends a product URL and stores `rows` and `header` through the existing snapshot path.
- Two portfolios holding one URL produce one `/scrape` call.
- A snapshot dated today is not scraped again.
- `rate_limited` stops the run, sets the gap to `DAILY_GAP_MAX_S`, and the resume uses a new `session_id`. `challenge_unsolved` retries once with a new `session_id`.
- Two clean `offers` results bring the gap back to `DAILY_GAP_MIN_S`. One challenge raises it by `DAILY_GAP_STEP_S` and does not pass `DAILY_GAP_MAX_S`.
- The `session_id` changes at `DAILY_SESSION_PAGES` and again `DAILY_SESSION_ROTATE_BEFORE_S` before the browser lifetime, not on every URL.
- On a reused window the block list is set before `cdp.get`. `/scrape` returns `reused`. The paid worker keeps its `session_id` while `reused` is true, and a new id is what closes the held window.
- `chrome_launch_options()` includes the six background-network flags above.
- `DAILY_BROWSERS` defaults to 1. A value above 1 is rejected unless the scraper holds one window per `session_id` and counts the page gap per session.
- A process restart skips a `sample_key` whose snapshot is already dated today and continues with the rest. The lifespan schedules the loop with `asyncio.create_task` and still reaches `yield`.
- A phone parse and a proxy scrape of one `sample_key` share one snapshot. The night job skips it when either source wrote it today. The newer `observed_at` is the one kept.
- The WebView blocks images, fonts, and trackers on the first load, and blocks stylesheets only after that view has returned offers. The posted HTML still contains the offer table and `chart-init-script`.
- An escalation with the WebView enabled and no recent challenge is refused. The WebView is not given a proxy URL.
- `DAILY_PRICES_ENABLED` defaults to false. The lifespan does not schedule the night job while it is false, and a live escalation still runs when `SCRAPER_ENABLED` is true.
- A challenge sheet does not enqueue a scrape. Dismissing it, or a timeout, does. A second check inside the fallback window enqueues without opening the sheet again.
