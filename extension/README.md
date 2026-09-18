# Scanapp Cardmarket helper (Chrome)

The helper is a quiet background worker. Scanapp queues a product URL; this Chrome profile claims one job at a time, loads it in a dedicated inactive tab, and saves a sample of the first listings. Your normal Cardmarket tabs are left alone.

It does not bypass Cloudflare. Login or browser challenges pause collection and ask for attention in the popup.

## Install

1. Chrome → `chrome://extensions` → Developer mode → **Load unpacked**
2. Choose the `extension` folder in this repo
3. Click **Reload** after upgrades

Existing `apiBase` values are kept. New installs can pick **Local development** or **Staging** in the popup without opening DevTools.

## Helper credential

Write routes require a revocable credential.

On the local API:

```bash
./scripts/helper-token.sh
```

On staging (`auctaro-staging`):

```bash
./scripts/helper-token.sh staging
```

Paste the printed token once in the popup while that server is selected. Local Docker and Staging keep **separate** saved credentials in the extension (reload unpacked helper 0.2.13+). Leave the field blank when switching if that server is already saved. It is stored only in extension storage and is never sent to content scripts, URLs, or logs.

Rotate or revoke with `--helper-id` / `--revoke HELPER_ID` inside the same `python -m app.helper_credential` command.

## Popup

The toolbar icon opens a compact panel:

- **Connection:** connected, disconnected, or authentication required
- **Activity:** idle, fetching, saving, paused, or needs attention
- Current card and queued-job count from the server
- Last successful update and recent failures
- **Pause / Resume**, **Check connection**, **Open helper tab**

Pause survives Chrome restarts. It stops new claims immediately. A collected result can still upload; a page load is released at a safe checkpoint.

**Open helper tab** is the only control that brings the helper tab forward.

## Behaviour

- One helper tab, opened automatically in the **foreground** as soon as a scan queues a job (about one second, not Chrome’s 30-second alarm). Cloudflare blocks hidden tabs. You do not need to press Open on Cardmarket.
- One serialized worker; overlapping alarms, popup clicks, and page messages cannot claim two jobs
- State is persisted (settings, pause, current job, claim, unsaved result). Service worker timers are not trusted for recovery
- After a Chrome restart, tab IDs are discarded and ownership is established again
- Results are bound to the helper tab, document, extraction request, and product URL. Delayed messages from another card are dropped
- Redirects from `prices.pokemontcg.io` are tracked. Search, login, or a different product cannot complete the job
- Empty listings are stored only when the page explicitly has no articles
- Closing the helper tab does not stop the queue; the next alarm opens Cardmarket in the foreground again if a job is still claimed

Scheduling targets (Chrome may delay background work):

| Setting | Default |
|---|---|
| Concurrent jobs | 1 |
| Idle queue check | 30 seconds |
| Spacing between product navigations | 30 seconds |
| Page-loading deadline | 60 seconds |
| Server claim lifetime | 3 minutes, renewed during work |
| Transient-failure attempts | 3, with increasing delays |

## Upgrade from 0.1.x

1. Reload the unpacked extension
2. Provision a helper credential and paste it in the popup
3. Confirm the Scanapp server (local or staging)
4. Click **Check connection**

The old four-second poller and focus-stealing product tabs are gone.

## Troubleshooting

- **Authentication required:** paste a fresh token from `python -m app.helper_credential`
- **Tab opens late / not at all:** reload the unpacked extension (0.2.7+). Chrome otherwise only wakes the helper every 30 seconds.
- **Site stuck on Fetching offers:** reload the unpacked extension (0.2.8+). The helper now reads the Cardmarket tab directly. Keep that tab in front until prices appear.
- **Helper tab closed / navigated away:** click **Open helper tab**, then **Resume**
- **Cardmarket needs attention:** solve login or the browser challenge in the helper tab, then **Resume**
- Phone and PC must share the same API. If you scan on `http://localhost:8080`, the helper server must be **Local Docker**, not Staging.

## Tests

```bash
node --test extension/tests/*.test.js
```

Automated tests use fixtures and a mocked API. Manual checks against live Cardmarket pages: ordinary listings, a redirected `prices.pokemontcg.io` catalogue link, and sleep/resume recovery.
