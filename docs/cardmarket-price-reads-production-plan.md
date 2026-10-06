# Cardmarket price reads: production plan

Goal: a user who opens or scans a card sees a price as soon as one exists, sees a clear state while a new one is read, and never waits on a scraper that has stopped answering. The scraper must recover on its own from a hung browser, and two scraper containers must share the work without fighting over one browser or one proxy address.

Scope: the scraper service (`scraper/`), the scanapp API (`api/app/`), and the PokeSingle app (`~/StudioProjects/PokeSingle/lib/`). The existing behaviour is described in [daily-portfolio-prices.md](./daily-portfolio-prices.md). This plan changes what is listed here and keeps the rest.

## The case this prevents

On 4 Oct 2026 the staging scraper `scanapp-scanapp-z1mwj4-scraper-1` stopped serving pages and did not recover:

- One request opened a browser and never returned. Its Chrome and `uc_driver` processes were left `<defunct>`.
- The request thread still held the only browser slot (`_slots`, `MAX_BROWSERS=1`). Every later `/scrape` waited 30 seconds for that slot and returned `503 Busy`.
- `/health` kept answering `{"ok": true}`, so the Docker health check passed and nothing restarted the container.
- The API recorded 158 of those 503 replies as used paid pages, 500 KB each (about 77 MB), although none of them reached Cardmarket. The Dokploy environment set the daily cap to 1000 pages and 1000 MB at the time, so the cap did not stop them.
- Users who escalated a card waited for a result that never came.

A second problem started on 5 Oct 2026 at 19:39 UTC. The EN-007 catalogue activation recreated the API container with `docker compose`, using the copied compose files in `/etc/scanapp-staging/rollback-speed030-20261004-v2`. That directory has no `.env`, so every `${VAR:-default}` in `compose.dokploy.yaml` fell back to its default instead of the Dokploy value:

| Variable | Dokploy `.env` | Running API |
|---|---|---|
| `SCRAPER_ENABLED` | `true` | `false` |
| `SCRAPER_API_KEY` | set | empty (the scraper still has its key) |
| `PORTFOLIO_DATABASE_URL` | set | empty |
| `REVIEW_TOKEN` | set | empty |
| `ENABLE_MATCHED` | `false` | `true` |
| `SCRAPER_DAILY_PAGES` / `SCRAPER_DAILY_MB` | 1000 / 1000 | 50 / 50 |
| `SCRAPER_SESSION_HOURLY` / `SCRAPER_IP_HOURLY` | 1000 / 1000 | 10 / 20 |
| `SCRAPER_URL_COOLDOWN_S` | 60 | 1800 |

`activation.json` lists only the four catalogue variables as its `environment_delta`. Every catalogue activation must start from the Dokploy `.env` (`docker compose --env-file /etc/dokploy/compose/scanapp-scanapp-z1mwj4/code/.env …`) and must compare the full container environment before and after.

## Where the current code can hang or waste

| # | Where | What goes wrong |
|---|---|---|
| 1 | `scraper/main.py` `scrape()` | `_slots.release()` runs only in that request thread's `finally`. A thread blocked inside SeleniumBase or ChromeDriver never reaches it. Python cannot interrupt a thread from outside |
| 2 | `scraper/browser.py` `run_attempt()` | The watchdog kills Chrome at the deadline, but it cannot unblock the request thread. A hang in `SB.__enter__` or `__exit__` stays hung |
| 3 | `scraper/browser.py` `acquire_browser()` | `_held.quit()` for an expired or replaced window runs before `run_attempt()` starts, outside any deadline |
| 4 | `scraper/main.py` `health()` | Always `ok: true`. It does not know whether the browser is stuck. Plain Docker (not Swarm) does not restart a container that is only *unhealthy* anyway |
| 5 | `compose.dokploy.yaml` `init: true` | tini reaps orphans only. Chrome processes that are children of the live uvicorn process stay `<defunct>` until Python waits on them |
| 6 | `api/app/cardmarket_scraper.py` `_handle()` | A 503 reply is reconciled as a used page: `reconcile_attempt(outcome="http", actual_bytes=None)` keeps the 500 KB estimate |
| 7 | Staging environment | The cap check in `reserve_attempt()` works: on an empty database it stops at exactly 50. The 158 rows on 2026-10-04 passed because the Dokploy cap was 1000. A cap that high does not protect the budget |
| 8 | `api/app/cardmarket_scraper.py` `_scrape()` | Every 503, including `Busy`, calls `StickySession.note(outcome="rate_limited")`. That mints a new proxy session, so the next successful read opens a new window and pays a new Cloudflare check (about 818 KB) |
| 9 | `api/app/cardmarket_scraper.py` `_release()` | A busy job goes back to the queue with a 5-second delay and no overall deadline. The cooldown is global for the whole scraper |
| 10 | `api/app/cardmarket_daily.py` `scrape_product()` | The nightly job calls `/scrape` directly, next to the paid worker. With one slot they compete, and a live read can receive `Busy` because the nightly job is running |
| 11 | PokeSingle `core/config.dart` | `pricePollInterval` is 3 s and `pricePollLimit` is 60 s. A paid read can take up to 90 s plus queue time, so the panel can stop polling before the result arrives |

## Baseline

Measured from `cardmarket_scrapes` on staging, 24 Sep to 4 Oct 2026, paid tier only:

| Outcome | Count | p50 | p90 | Max |
|---|---:|---:|---:|---:|
| `offers` | 59 | 10.6 s | 20.1 s | 59.2 s |
| `timeout` | 13 | 26.7 s | 91.2 s | 91.5 s |
| `unreachable` | 3 | 120.1 s | 120.1 s | 120.1 s |
| `challenge_unsolved` | 1 | 91.5 s | 91.5 s | 91.5 s |
| `http` (503 Busy) | 194 | 30.0 s | 30.1 s | 92.8 s |

59 of 76 real attempts returned offers (78%). Each 503 cost the user 30 seconds and returned nothing.

Staging host: 3.8 GB RAM, 2 vCPU, about 800 MB available, 1.8 GB of swap in use. The API uses 1.26 GB of its 2 GB limit. The scraper is limited to 1.5 GiB.

## What the user sees

This is the contract the rest of the plan serves.

| Moment | Card has a stored price | Card has no stored price |
|---|---|---|
| Screen opens | The stored price, at any age, with "fresh" or "stale" and the observed time. No spinner over it | A skeleton with "Checking Cardmarket…" |
| Reading in the background | A thin progress bar under the price ("Updating…") | Same skeleton. If a server read is queued: "In line" |
| Phone gets a Cloudflare check | Today's rule stays. The sheet opens and the user can tap | Same, plus see open decision 1 |
| 20 s without a result | Nothing changes. The stored price stays | "Taking longer than usual. It will appear here when it arrives." The screen stays usable |
| Result arrives while the screen is open | Price updates in place, label becomes "fresh" | Price appears |
| Final failure (job failed or expired) | Stored price stays, with a small "Couldn't refresh · Retry" | "Price unavailable right now · Retry". If the card was tried recently: "Tried a moment ago, try again later" |
| User left the screen | Result is stored and shown on the next open | Same |

No state waits forever. Every waiting state ends either in a price or in a final message with a retry action.

Targets, measured after phase 3:

| Measure | Target |
|---|---|
| Time to first price on screen when a stored price exists | p95 under 1 s |
| Paid read on a window that already returned offers | p95 under 20 s |
| Paid read that needs a new window and a Cloudflare check | p95 under 45 s |
| Time an interactive job waits before a lane starts it | p95 under 5 s |
| Longest a browser slot can stay busy | `SCRAPER_ATTEMPT_SECONDS` + 10 s |
| Recovery after a hung browser | Under 30 s, without a person |
| 503 replies charged to the budget | 0 |

## Architecture

```text
PokeSingle app
  │  GET /cardmarket/prices, /prices/batch, SSE /prices/events
  │  POST /cardmarket/escalations, /challenge-fallback
  ▼
scanapp API
  ├─ cardmarket_jobs queue (SQLite)       priority, deadline_at
  ├─ LanePool                              one Lane per scraper URL
  │    ├─ lane a: dispatcher thread, StickySession, cooldown, breaker
  │    └─ lane b: dispatcher thread, StickySession, cooldown, breaker
  └─ nightly job                           leases a lane, does not call /scrape on its own
        │
        ▼  POST /scrape, GET /status (private network, SCRAPER_API_KEY)
scraper-a container                 scraper-b container
  supervisor (FastAPI, no Selenium)    supervisor
  └─ browser worker process            └─ browser worker process
       └─ Chrome (own process group)        └─ Chrome
            │ sticky DataImpulse sessid a        │ sticky sessid b
            ▼                                    ▼
                         Cardmarket
```

One container is one lane: one browser, one sticky proxy address, one request at a time. More throughput means more lanes, not more browsers in one container.

## Part 1: the scraper cannot get stuck

### Supervisor and browser worker

Split `scraper/main.py` into two processes.

**Supervisor** (the FastAPI app). It never imports SeleniumBase and never makes a call that can block on Chrome. It owns the lane state, the deadline, and the worker's life.

**Browser worker** (new `scraper/worker.py`). It holds `ChromeSession`, `acquire_browser()` and `run_attempt()` from `browser.py`, unchanged in behaviour. It reads one command at a time from a pipe and writes one result.

Start the worker with `subprocess.Popen([sys.executable, "-m", "worker"], start_new_session=True, stdin=PIPE, stdout=PIPE)`, or `multiprocessing.get_context("spawn")` with `os.setsid()` in the child. Either way the worker and every Chrome and `uc_driver` it starts share one process group, and the supervisor can kill that whole group with one signal.

Protocol: one JSON line each way.

```json
{"op": "scrape", "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/...", "session_id": "…", "deadline_s": 90}
{"op": "warm", "session_id": "…"}
{"op": "quit"}
```

The result is today's `run_attempt()` dict (`outcome`, `rows`, `header`, `chart`, `bytes`, `elapsed_ms`, `url`) plus `reused`, `cleared` and `stage`.

### Lane states

The supervisor keeps one state, changed only by its own code:

| State | Meaning | `/scrape` reply |
|---|---|---|
| `starting` | Worker process starting, Chrome not yet open | 503 `Starting`, `Retry-After` = expected start seconds |
| `idle` | Worker alive, no request | Accepts |
| `busy` | One request running | 503 `Busy`, `Retry-After: 5`, immediately (no 30-second wait) |
| `restarting` | Worker being killed or replaced | 503 `Restarting`, `Retry-After` = expected start seconds |
| `cooling` | Cardmarket returned `rate_limited` on this lane's address | 503 `Rate limited`, `Retry-After` = seconds left |

`_slots` and its 30-second `acquire` go away. There is at most one request in flight per container, and the API dispatcher never sends a second one.

### Deadline enforced from outside

For each request the supervisor writes the command, then waits on the pipe for `SCRAPER_ATTEMPT_SECONDS + SCRAPER_KILL_GRACE_S` (90 + 10 by default). If no result arrives:

1. `os.killpg(pgid, SIGTERM)`, wait 2 seconds, then `os.killpg(pgid, SIGKILL)`.
2. `worker.wait()` so the worker is reaped. Chrome and `uc_driver` die with the group. tini reaps anything that was reparented.
3. Reply **200** with `{"outcome": "timeout", "killed": true, "stage": "<last stage the worker reported>", "bytes": <last measured or null>}`. A killed attempt is a timeout, not a server error.
4. Set the state to `restarting` and start a new worker in the background. The lane is `idle` again when the new worker reports ready.

The worker reports `stage` changes (`browser_start`, `navigation`, `challenge`, `parse`, `quit`) as progress lines on the same pipe, so a kill can say where it hung.

The same deadline covers the old-window `quit()` in `acquire_browser()` (row 3 above), because that call now runs inside the worker.

### Warm browser, recycled on a schedule

- When a worker starts, it opens Chrome for the lane's current sticky session without navigating. This costs no proxy traffic and removes Chrome start time from the next request.
- The worker is replaced, while idle, when any of these is true:
  - the window is within `DAILY_SESSION_ROTATE_BEFORE_S` (120 s) of `SCRAPER_BROWSER_LIFETIME_S` (1800 s, the DataImpulse sticky window)
  - its process group uses more than `SCRAPER_WORKER_MAX_RSS_MB` (1100), measured with `psutil` over the group
  - it has served `SCRAPER_WORKER_MAX_PAGES` (200) pages
- A replacement started on schedule keeps the same `session_id` if the sticky window is still valid, so the clearance cookie is not lost. A replacement after a kill keeps the id too. Only `challenge_unsolved`, `rate_limited`, or an expired window mint a new id, and the API decides that (part 2).

### Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness only: the supervisor answers. Used by the Docker health check. Stays cheap and never touches the worker |
| `GET /status` | `{"lane", "state", "session_id", "cleared", "pages", "window_age_s", "busy_for_s", "restarts", "last_restart_reason", "cooldown_until", "last_outcome", "last_ok_at", "attempt_seconds"}`. Used by the API dispatcher every 5 seconds |
| `POST /scrape` | Body and result unchanged, plus `lane`, `stage`, `killed` |
| `POST /warm` | `{"session_id"}`. Opens Chrome for that session without navigating. Used when a lane has been idle with an expired window |

### Backstop

The supervisor exits the process (`os._exit(1)`) when any of these is true, and `restart: unless-stopped` brings the container back:

- the worker failed to start 3 times in a row
- `busy_for_s` is over twice the attempt deadline. That would mean a supervisor bug, because the kill should already have happened

Every restart and every kill is logged as one line with `lane`, `reason`, `stage`, `busy_for_s` and `restarts`.

## Part 2: the API protects the budget and the user

These changes apply with one lane and are needed before a second lane is added.

### Charge only real attempts

- Add state `released` to `cardmarket_scrapes`. `usage_today()` already counts only `reserved` and `used`.
- New `release_attempt(conn, reservation_id, reason)`. Call it for 503 `Busy`, `Starting`, `Restarting`, and for a connection error before the request was accepted.
- `rate_limited` stays `used`: Cardmarket served that page.
- `timeout` with `killed: true` stays `used`, with the measured `bytes` when the worker reported them, else the reserve.
- Keep a test that the reservation after the cap in one UTC day raises.

### Keep the sticky session on a busy reply

In `cardmarket_scraper.py` `_scrape()`, only `outcome == "rate_limited"` (from the result body or a 503 with detail `Rate limited`) and `challenge_unsolved` mint a new session id. `Busy`, `Starting` and `Restarting` keep the id.

### Job priority and deadline

Add two columns to `cardmarket_jobs` (migration in `api/app/db.py`, next to `tier`):

| Column | Values |
|---|---|
| `priority` | `0` interactive (escalation, challenge fallback), `10` prefetch, `20` nightly |
| `deadline_at` | For interactive jobs: created time + `CARDMARKET_INTERACTIVE_START_S` (30). Null for others |

`claim_proxy_job()` orders by `priority, created_at, rowid`. It settles a pending interactive job whose `deadline_at` has passed as `failed`, reason `expired`, without reserving budget. The price stays whatever was stored.

`enqueue_job()` raises an existing job's priority when an interactive request arrives for the same `sample_key`. It already upgrades `tier` the same way.

`PriceResponse` adds `deadline_at` and `queue_position` so the app knows how long to wait and what to show.

### Circuit breaker per lane

Three `timeout`, `killed` or `unreachable` results in a row open the lane's breaker for 30 seconds, doubling up to 5 minutes. When the breaker is open, the lane takes no jobs. After the wait, the lane takes one job: success closes the breaker, failure doubles the wait. With all lanes open, `scraper_ready` is false and `scraper_block_reason()` returns `no-lane`. The app then shows the final state instead of queueing.

### Cooldown per lane

`rate_limited` cools only the lane that received it, for `SCRAPER_RATE_LIMIT_S` (900). Its address is the one Cardmarket limited. If two lanes are rate limited within 10 minutes, pause all lanes for `SCRAPER_RATE_LIMIT_S` and log an alert, because the limit is then probably not per address.

### Budget share for the nightly job

New `SCRAPER_INTERACTIVE_RESERVE_PAGES` (default 20% of `SCRAPER_DAILY_PAGES`). The nightly job stops with `capped` when the pages left today are at or under that reserve. Live reads can use the whole cap.

## Part 3: orchestrating two or more scraper containers

### Why not a load balancer or compose replicas

- A sticky `session_id` only means something on the container whose browser holds that window. Round robin would send the next product to a browser without the clearance cookie.
- A balancer does not know which container is busy, cooling, restarting, or has a cleared window.
- A rate limit applies to one exit address. The caller has to stop using that lane only.

So the API calls named lanes directly, and it is the only caller.

### Configuration

- `SCRAPER_URLS=http://scraper-a:8000,http://scraper-b:8000` on the API. When it is unset, `SCRAPER_URL` is one lane, which is today's behaviour.
- In `compose.dokploy.yaml`, `scraper-a` and `scraper-b` share one definition through a YAML anchor, with `SCRAPER_LANE=a` and `SCRAPER_LANE=b`. Same image, same `SCRAPER_API_KEY`, same DataImpulse account, same `PROXY_COUNTRY`.
- Each lane mints its own `sessid`, so each lane has its own exit address. Never send one `session_id` to two lanes.

### LanePool in the API

New `api/app/cardmarket_lanes.py`. It replaces the single `ScraperWorker` thread and its `_ping()`.

```python
@dataclass
class Lane:
    name: str
    url: str
    sticky: StickySession
    state: str = "unknown"
    cleared: bool = False
    window_age_s: float = 0.0
    cooldown_until: float = 0.0
    breaker_until: float = 0.0
    failures: int = 0
    leased_by: str | None = None
```

- A status thread reads `GET /status` from every lane every 5 seconds and updates `state`, `cleared`, `window_age_s` and `cooldown_until`.
- **One dispatcher thread per lane.** Each loop: if the lane is not `idle`, or is cooling, broken or leased, wait 1 second. Otherwise claim the next job with `claim_proxy_job()`, reserve budget, call this lane's `/scrape` with this lane's `session_id`, then complete, fail, or release the job as `_handle()` does today. The claim runs in `immediate_transaction`, so two lanes never take the same job. `reserve_attempt()` already refuses a second in-flight read of the same `sample_key`.
- **Lane choice for interactive work.** When more than one lane is free, the job should go to a lane whose window has already returned offers and has time left. Implement this by having a dispatcher on a cold lane skip claiming for 2 seconds when another free lane is `cleared`. That keeps the selection rule in one place without a central scheduler.
- **Status to the app.** `scraper_ready` is true when at least one lane is `idle` and ready, or `busy` with a deadline that will free it. `queue_position` comes from pending interactive jobs ahead of this one.

### The nightly job leases a lane

`cardmarket_daily.run_pass()` keeps its pacing (`DailyPace`: gaps, session rotation, retries) but stops calling `settings.scraper_url` directly:

1. Before each product it calls `pool.lease("daily", timeout=…)`. A lease is granted only when the lane is idle, no interactive job is pending, and, with two or more lanes, at least one other lane stays free for interactive work.
2. It calls `/scrape` on the leased lane with its own `daily-…` session id, and releases the lease right after the reply, before its gap sleep. An interactive job can take that lane during the gap.
3. When the lease is refused, it waits and asks again. It does not count that as a failure.

With one lane (staging today), the nightly job only runs between interactive jobs.

### Hedged reads (optional, off by default)

`SCRAPER_HEDGE_AFTER_S` (unset = off). When an interactive job for a card with no stored price has been running on one lane for that long, and another lane is idle and `cleared`, send the same URL there too. The first result completes the job. The second still writes the snapshot through the same `sample_key`, so it is not lost, but it does cost one page. Turn this on only when the daily budget is larger than demand.

### Hosting

A second 1.5 GiB scraper does not fit on the current staging host (about 800 MB available, swap already in use). Decision: a dedicated scraper host, Hetzner Cloud fsn1, x86, 8 GB RAM and 4 vCPU, running two to four lanes, reached from the API over a private network. Lanes need no shared disk. Setup, network, firewall and deploy are in [scraper-host.md](./scraper-host.md), with `compose.scraper-host.yaml` and `scripts/scraper-host/`.

Until part 3 is merged, the new host can already take the single lane: `SCRAPER_URL` in `compose.dokploy.yaml` is read from the environment.

Each Chrome needs about one vCPU while it solves a Cloudflare check. The photo runs measured four and seven windows working at once, and fifteen failing. Grow 1 → 2 → 4 and measure the `offers` rate at each step.

## Part 4: the app

Files are under `~/StudioProjects/PokeSingle/lib/`.

1. **Stored price first.** `features/catalogue/price_panel.dart` shows `_snapshot` prices whenever they exist, at any `freshness`. The skeleton is shown only when there are no prices. While a read runs, use the existing `LinearProgressIndicator` under the price instead of replacing it.
2. **Wait as long as the server's deadline.** Replace the fixed `AppConfig.pricePollLimit` (60 s) with the job's `deadline_at` plus `SCRAPER_ATTEMPT_SECONDS`. Prefer the SSE stream `cardmarket/prices/events` (`data/api_client.dart`). Fall back to 3-second polling only when the stream fails.
3. **States and copy.** Map the server fields to the states in "What the user sees": `queue_position` → "In line", `claimed` → "Reading", phone `verification` → existing sheet, `failed` / `expired` → final message with Retry, `429 This card was tried recently` → "Tried a moment ago".
4. **Retry.** The Retry action calls `POST /cardmarket/escalations` when `scraper_ready` is true. Otherwise it re-runs the phone reader.
5. **Same rules everywhere.** `features/scan/scan_price_follow.dart`, `features/home/home_refresh.dart` and `features/scan/batch_strip.dart` use the same state mapping, through one shared helper next to `cardsToEscalate`.
6. **Client timing event.** Log `time_to_first_price_ms`, with `source` (stored, phone, server) and `had_stored_price`, to the existing analytics, so the targets above can be checked from real devices.

## Observability

Log lines (one per event, key=value), from the scraper and the API:

- lane state change: `lane`, `from`, `to`, `reason`
- worker kill and restart: `lane`, `reason`, `stage`, `busy_for_s`, `restarts`
- attempt: `lane`, `outcome`, `stage` timings, `reused`, `cleared`, `bytes`, `elapsed_ms`, `queue_wait_ms`
- job settle: `priority`, `outcome`, `queue_wait_ms`, `total_ms`
- budget: pages and MB used today, interactive reserve left

Alerts:

| Condition | Why |
|---|---|
| Oldest pending interactive job older than 60 s | Users are waiting |
| A lane restarted more than 3 times in 15 min | Browser or proxy keeps failing |
| No `offers` in 30 min while jobs are pending | The Oct 4 case |
| All lanes unavailable for 5 min | No server reads at all |
| Budget over 80% of the daily cap | Live reads will stop soon |
| Two lanes rate limited within 10 min | Possible account-level block |

## Delivery order

| Phase | Work | Estimate | Done when |
|---|---|---|---|
| 0 | Recreate the staging API from the Dokploy `.env` plus the EN-007 catalogue variables. Restart the staging scraper. Fix the activation procedure to use `--env-file` and diff the full environment. Add the "no offers in 30 min while jobs pending" alert | 2 h | The API environment matches Dokploy except the catalogue variables, the scraper serves pages again, and the alert fires in a test |
| 1 | Supervisor, browser worker, lane states, `/status`, deadline kill, warm start, recycling, backstop | 2–3 days | Fault tests below pass. A 48-hour staging soak has no manual restart |
| 2 | Budget release and cap fix, sticky session fix, `priority` and `deadline_at`, breaker, per-lane cooldown, nightly reserve | 2 days | API tests below pass. A forced hang costs no budget and the next job succeeds |
| 3 | `LanePool`, dispatcher per lane, nightly lease, `SCRAPER_URLS`, second lane on a host with room | 2–3 days | Two lanes serve interactive jobs in parallel. One lane killed mid-request does not delay the other |
| 4 | App: stored price first, deadline-based wait over SSE, states and copy, retry, timing event | 2–3 days | App tests below pass. Time to first price is measured on a device |
| 5 | Optional: hedged reads, decision 1 below, more lanes | after data from 3 and 4 | Targets are met with budget to spare |

Phases 1 and 2 can be built in parallel by two people. Phase 3 needs both.

## New settings

| Setting | Service | Default | What it does |
|---|---|---:|---|
| `SCRAPER_LANE` | scraper | `a` | Lane name in logs and `/status` |
| `SCRAPER_KILL_GRACE_S` | scraper | 10 | Extra wait after the attempt deadline before the worker is killed |
| `SCRAPER_WORKER_MAX_RSS_MB` | scraper | 1100 | Replace the worker while idle above this memory |
| `SCRAPER_WORKER_MAX_PAGES` | scraper | 200 | Replace the worker while idle after this many pages |
| `SCRAPER_URLS` | API | unset | Comma-separated lane URLs. Unset uses `SCRAPER_URL` as one lane |
| `CARDMARKET_INTERACTIVE_START_S` | API | 30 | An interactive job not started by then settles as `expired` |
| `SCRAPER_INTERACTIVE_RESERVE_PAGES` | API | 20% of cap | Pages the nightly job leaves for live reads |
| `SCRAPER_BREAKER_FAILURES` | API | 3 | Failures in a row that open a lane's breaker |
| `SCRAPER_BREAKER_MAX_S` | API | 300 | Longest breaker wait |
| `SCRAPER_HEDGE_AFTER_S` | API | unset | Hedged reads, off when unset |

`SCRAPER_ATTEMPT_SECONDS` is 90 on both staging containers, set by `compose.dokploy.yaml`. The code defaults differ: 70 in `api/app/config.py` and 25 in `browser.py`. The dispatcher should use the value each lane reports in `/status`, so a missing variable cannot make the API and the scraper disagree.

## Tests

Scraper (`scraper/test_supervisor.py`, with a fake worker that can hang on command):

- A worker that hangs in `browser_start`, `navigation` or `quit` is killed within the deadline plus grace. The reply is 200 `timeout` with `killed: true` and the hung stage. The next request succeeds on a new worker.
- After a kill, no process of the old group is left, `<defunct>` included.
- A second `/scrape` while one is running gets 503 `Busy` in under 1 second.
- `/health` answers in under 100 ms while the worker is hung.
- `/status` reports `restarting` during the restart and `idle` after it.
- Three failed worker starts in a row exit the process.
- A scheduled recycle keeps the `session_id` while the sticky window is valid.
- The worker is replaced while idle above `SCRAPER_WORKER_MAX_RSS_MB`, never during a request.

API:

- 503 `Busy`, `Starting` and `Restarting` release the reservation, and `usage_today()` does not count them.
- The reservation after `SCRAPER_DAILY_PAGES` in one UTC day raises.
- `Busy` keeps the sticky session. `rate_limited` and `challenge_unsolved` mint a new one.
- `claim_proxy_job()` returns priority 0 before priority 20, and settles an expired interactive job without a reservation.
- An interactive request for a pending nightly `sample_key` raises that job to priority 0.
- Three timeouts open the lane breaker. The half-open job closes it on success.
- `rate_limited` on lane a leaves lane b taking jobs. Two lanes rate limited within 10 minutes pause both.
- With two lanes, two interactive jobs run at the same time and never on the same lane. One `sample_key` is never read on two lanes unless hedging is on.
- The nightly job gets no lease while an interactive job is pending, and stops at the interactive reserve.
- Lane a killed mid-request: its job settles as `timeout`, lane b keeps serving, and lane a returns to `idle` without a restart of the API.

App:

- A stored stale price is visible on the first frame, and stays visible while a read runs.
- With no stored price, the panel reaches a final state by `deadline_at` plus the attempt time, never later.
- An SSE update replaces the price in place. A dropped stream falls back to polling.
- Retry after a recent attempt shows the "tried recently" message, not an error.

## Rollout and rollback

1. Ship phase 1 to staging with one lane. Force hangs with `kill -STOP` on the worker and with `docker kill` on Chrome. Soak for 48 hours.
2. Ship phase 2 to staging. Check that budget rows for the forced hangs are `released` or `used` as described.
3. Add the second lane on a host with room. `SCRAPER_URLS` with one URL is the rollback: it is today's single-lane path.
4. Ship the app change behind the server fields. An app that does not see `deadline_at` keeps today's 60-second polling.
5. Production only after staging meets the targets for 7 days.

## Open decisions

1. **Parallel server read when no price is stored.** Today a phone challenge never calls the server at the same time ([daily-portfolio-prices.md](./daily-portfolio-prices.md), Phone WebView). Starting a server read as soon as the challenge appears, only when the card has no stored price, would cut the wait for new cards by the length of the challenge sheet. It costs one page per such card. Recommendation: allow it once the budget has room, behind a server flag.
2. **Hosting for lanes two to four.** A dedicated scraper host, or a larger staging host.
3. **Daily caps.** The code defaults are 50 pages and 50 MB. The Dokploy environment sets 1000 and 1000, which did not stop the 4 Oct waste. The nightly job can do about 8,000 listings a night on one lane. Set the caps from expected portfolio size and live demand.
4. **Hedged reads.** Keep them off until the cap is well above demand.
