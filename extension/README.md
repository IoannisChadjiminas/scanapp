# Scanapp Cardmarket helper (Chrome)

Your PC Chrome opens the Cardmarket product page after someone taps **Open on Cardmarket** in Scanapp. The extension reads the first three listings (NM/EX/…) and saves them to the local API.

It does not bypass Cloudflare. It uses the tab you already have (or opens one).

## Install

1. Chrome → `chrome://extensions` → Developer mode → **Load unpacked**
2. Choose the `extension` folder in this repo
3. After load, click **Reload** on the extension card

**Hetzner (remote users):** point the helper at the public site.

1. On `chrome://extensions`, find **Scanapp Cardmarket helper**
2. Click **service worker** (or **Inspect views: service worker**)
3. In the Console tab, paste and Enter:

```js
chrome.storage.local.set({ apiBase: "https://staging-scan.auctaro.com" })
```

4. Close DevTools, click **Reload** on the extension, then click the helper icon once

**Local Docker:** skip that, or set `apiBase` back to `http://127.0.0.1:8000`.

## Use

1. Scan a card in Scanapp (phone or this PC)
2. Tap **Open on Cardmarket** — that queues a job
3. This Chrome profile picks up the job, loads the Singles page, writes prices
4. The scan result polls and shows the three listings

If Chrome has been idle, click the Scanapp helper icon in the toolbar to wake it.

Phone and PC must share the same API. For local Docker, the phone has to reach this machine’s `:8000` / `:8080`, not only `127.0.0.1` on the phone.
