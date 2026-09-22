# PokeSingle — product & architecture brief

**For:** product designer and software architect  
**From:** engineering (current experiment: Scanapp)  
**Brand:** PokeSingle  
**Line:** Scan. Collect. Sell.  
**Domain:** pokesingle.com (primary). CardExact.com is a spare only, not the product name.

This is the brief for designing and architecting the real product. The repo today is a working **recognition experiment**, not the product UI.

How to build on the existing FastAPI stack: [pokesingle-architecture.md](./pokesingle-architecture.md).

---

## 1. What we are building

A **Pokémon singles** app for collectors in Europe.

A collector photographs a card. We identify the **exact print** (set, number, language — not just “Charizard”). We attach the **Cardmarket Singles product URL**. They add it to a collection, see value, and later sell that same single.

We are **not** a generic TCG database (PokeData) and **not** a multi-game portfolio first (Collectr). We are hobby-native: Pokémon, singles, camera, Cardmarket.

```
photo → exact print → Cardmarket single → collection → value → sell
```

---

## 2. Goals

### Product goals

1. **Identify the print**, not the Pokémon. English 151 Bulbasaur `#001` is not a Japanese promo of the same art.
2. **One answer.** Most-probable print, or honestly “not a match.” Do not dump a guess list as the default result.
3. **European marketplace native.** The object we care about is a Cardmarket Singles URL, priced in EUR (and later the user’s Cardmarket language/locale).
4. **Languages in the photo, not in a menu.** Auto-detect English / Japanese / Chinese (Simplified and Traditional). The user should not pick a language first.
5. **Feel like a collector brand**, not a data/SaaS tool. PokeSingle should be sayable, camera-first, and enjoyable to open every day.
6. Grow in this order: **Scan → Collect → Sell.** Sealed/ETBs can sit under the same brand. Other TCGs would be a **second brand**, not a tab inside PokeSingle.

### Business goals (direction)

- First users: Pokémon collectors who buy/sell singles on Cardmarket.
- Wedge: better identification than “close cousin” scanner apps, especially JP/CN and lookalike prints.
- Later: collection value, then a path to actually sell (not only “open Cardmarket in a browser”).

### Success (first shippable product)

A collector can, on a phone, in under ~15 seconds:

- photograph a card (or upload),
- get **one** print back (or a clear miss),
- see the Cardmarket single and cached EUR listings when we have them,
- confirm “this is my card.”

Accuracy on real phone photos (sleeves, messy desks, JP/CN) matters more than features.

---

## 3. Non-goals (for now, and some forever)

Do **not** design or architect for these as v1:

- Training our own vision model (published DINOv2 + RapidOCR weights only).
- Live Cardmarket HTML from the API host (it 403s; helper on a PC does that).
- MKM API (none wired).
- Multi-TCG inside PokeSingle.
- Social / binder-sharing as the first screen.
- On-device DINOv2 as the matcher (phone preprocess + upload; server ranks).
- Invented Cardmarket URLs. Stored, unique-linked, or Save only.

Deploy:

- Chrome helper on a PC, not on the API VPS.
- Catalogue builder is offline, not `docker compose up`.

---

## 4. Who it is for

| Person | What they need | What they hate |
|---|---|---|
| Casual collector | Point camera, know what it is, rough EUR value | Language pickers, “which Charizard?”, 8 lookalikes |
| Cardmarket seller | Exact single so they list the right product | Wrong print → wrong listing |
| JP/CN collector in Europe | Photo in Japanese/Chinese matches that print | English-only catalogues |
| Us (ops) | Review wrong scans, add missing extras, keep Cardmarket links honest | Silent wrong matches |

Default persona for design: **one person, phone in one hand, card in the other, wants to know the exact single.**

---

## 5. Differentiator (say this in every review)

Competitors (Collectr, PokeData, PokeScan, PokeScope, Cardfolio, PokeSnap) already scan and track.

**Ours:** the result is a **specific printing** plus a **specific Cardmarket Singles URL**, with English / Japanese / Chinese treated as different cards. Wrong print is a product failure even if the Pokémon name is right.

---

## 6. Product phases

Design and architecture should make Phase 1 beautiful and Phase 2–3 possible without a rewrite. Do not build Phase 3 UI now.

### Phase 0 — today (exists)

Working experiment branded “Scanapp”:

- Web: camera or upload, crop, scan, confirm/correct/reject.
- API: DINOv2 retrieval + RapidOCR rerank, EN/JA/ZH-CN/ZH-TW catalogue.
- Cardmarket: stored product URLs; Chrome helper on a PC fetches listing samples; public server does not GET Cardmarket HTML.
- Review store of scan photos for debugging.
- Catalogue builder is **offline / one-off**, not part of the live app.

### Phase 1 — PokeSingle Scan (first public product)

Replace the experiment shell with the PokeSingle brand and a **phone-first** scan flow.

Must have:

- Camera still capture (not a video framebuffer) and upload.
- **Required on-device ML preprocess** on every scan: card quad + warp, multilingual OCR, language (`en`/`ja`/`zh-cn`/`zh-tw`), collector number; send those hints on `POST /scans`.
- Result: **matched** | **not a match** | **uncertain** | **retake** (blur / no card).
- One primary card: name, set, number, language, catalogue image, Cardmarket CTA.
- Confirm / “not this” / scan again.
- Cached Cardmarket prices when the helper has sampled that URL.
- Account **or** a clear anonymous-to-account path (architect to propose; design should not assume a heavy signup wall before the first scan).

### Phase 2 — Collect

- Add confirmed scans to **My singles**.
- Quantity, condition (raw at least), language, notes.
- Home shows **owned cards**, each with a basis price and the move versus the latest Cardmarket sample (below).
- Search / filter own cards.
- Manual add when scan fails (search catalogue, pick print).

### Home cards — paid price, or price when added

Each owned card shows **one price**, and under it the **percent** move. Up arrow in green when it is higher, down arrow in red when it is lower. No arrow when there is no basis to compare. Quantity stays on the card; it does not change the shown unit price.

**Now** is the average of the three cheapest Near Mint asking prices in the latest Cardmarket sample (shipping excluded). Fewer than three still average. Until a sample exists, show the price we already have (what they paid, the add-time price, or the price guide) with no arrow.

Two bases. Never mix them on one card, and never call a market snapshot “what you paid.”

| User did | Basis (frozen) | Label | Change |
|---|---|---|---|
| Entered what they paid | That amount, in EUR | Paid | Now − paid |
| Skipped the paid price | Cardmarket price at the moment they added the card | Since added | Now − price when added |
| Neither paid nor a sample at add time | None | — | Show **now** only. No arrow. Do not invent a baseline. |

If we have no sample yet, the card shows the basis alone and no change.

The paid field is optional on add. Skipping it is normal: we store the market price we had then and move on. Editing “paid” later replaces the basis; it does not rewrite history of “since added” unless they clear paid and we still have the original add-time sample.

Collection total is the sum of each card’s **now** (or basis, if now is missing). Gain/loss is the sum of each card’s own change. A card with no basis does not contribute a fake gain.

### Phase 3 — Sell

- From a owned single: sell / list.
- v1 may still be “open the right Cardmarket product with the right print” plus our copy of offers.
- Later: our own listings, offers, messaging — only if we still own the **identity of the single**. Do not become a generic classifieds app.

### Later (optional)

- Sealed, ETBs, graded (PSA/CGC/BGS) as extra product types.
- Extra user photos of a print (we already support extra reference images in the catalogue).
- Other TCGs → **not PokeSingle**; spare name (e.g. CardExact) only if that company exists.

---

## 7. Design: UX principles

1. **Camera is the home screen.** Collection and sell are one tap away, not the first thing you see.
2. **One card on the result.** Secondary candidates only after “Not this” or an explicit uncertain state.
3. **Never fake confidence.** Uncertain and not-a-match are first-class screens, not a tiny grey label on a wrong Charizard.
4. **Language is inferred.** Optional lock (EN / JA / ZH) is advanced, not required.
5. **Cardmarket is the store.** We do not invent a second price bible. Show EUR samples, timestamp, and “open on Cardmarket.”
6. **Sleeve, desk, bad light are normal.** Guide the user to fill the frame; retake should feel helpful, not like an error code.
7. **Brand, not dashboard.** Avoid admin tables, snapshot hashes, and “indexed 23k cards” in the consumer UI. Coverage can live in settings/about.
8. **Scan. Collect. Sell.** Three beats in the product, the nav, and the marketing site.

### Result states (must be designed)

| Status | User sees | Primary action |
|---|---|---|
| `matched` | One print, big art, set + number + language, Cardmarket | Confirm / add to collection |
| `uncertain` | “We’re not sure” + 2–3 candidates, not a fake winner | Pick one or scan again |
| `no_match` | Honest miss, ask for a better photo or search | Retake / search catalogue |
| `retake` | Blur, no card detected, too dark | Retake with a tip |
| `failed` | Server/catalogue down | Try again, no fake card |

### Key screens to design (Phase 1–2)

- Splash / first-run (camera permission).
- Scan (live camera + shutter + gallery).
- Crop / confirm frame if quad-detect fails.
- Processing.
- Result (states above).
- Card sheet (print identity + Cardmarket offers).
- Catalogue search (fallback).
- Collection list + card detail (Phase 2).
- Settings: language lock (override ML), how prices work.
- Empty states for no collection / no network / helper prices stale.

### Platform

- **Primary client: Flutter iOS + Android** (decision: no code-share with the current Next.js UI).
- Web can remain a marketing site + maybe a later lite scan; do not block mobile on pixel-perfect web parity.
- Design system should work at phone width first; collection later needs simple lists, not desktop density.

### Visual direction (for design)

- Collector product: tactile, card-in-hand, not fintech charts.
- Hobby camera app, not a data terminal.
- Name **PokeSingle**. Catalogue art from existing `image_url` / CDN fields.

---

## 8. Architecture: current system

Do not throw this away. Phase 1 wraps and hardens it.

```
[Phone / browser]
    camera or upload, crop
        → POST /api/v1/scans
[FastAPI]
    detect/rectify card
    DINOv2 embedding
    cosine vs catalogue vectors
    RapidOCR + language + collector rerank
    one status + suggestions
        → optional Cardmarket job
[SQLite catalogue + vector snapshot]
    TCGdex metadata, EN/JA/ZH-CN/ZH-TW
    stored Cardmarket URLs (unique-link by name+number+set, or user Save)
[Chrome helper on a PC]
    claims jobs, opens Cardmarket product pages, stores listing samples
    never runs on the public VPS
[Catalogue builder, one-off]
    compose.catalogue.yaml — download TCGdex, embed, link URLs, pack tar
    live `docker compose up` never downloads the catalogue
```

**Hosting today:** local Docker; staging `https://staging-scan.auctaro.com` (Dokploy / Hetzner). Static web (Caddy) + API. Recognition is CPU ONNX.

**Cardmarket reality:** server-side GET of product HTML is Cloudflare 403. Product URLs live in our DB. Prices are **cached samples** from the helper, not live at scan time.

---

## 9. Architecture: target (what we want)

### Clients

- **Flutter app** — scan, collection, later sell. Talks to HTTPS API.
- Optional: keep a thin web scan for demos; not the product.

### Backend

- Keep **FastAPI** as the recognition + catalogue + Cardmarket-job API unless the architect has a strong reason to split.
- Auth: real user accounts for collection (Phase 2). Scan-without-account should stay possible.
- Recognition **on the server**. Flutter **always** runs on-device warp + OCR (language, collector, lines) and uploads those hints with the JPEG. DINOv2 stays on FastAPI.

### Data

- Catalogue and vectors: versioned artifacts, atomic activate (already the direction). App never builds embeddings.
- Users: owned singles, condition, scan history, confirmed print ids.
- Cardmarket: `cardmarket_url` on the print; snapshots of offers keyed by URL; helper queue.
- Scan photos: stored for review/eval (`datasets/review/`). Architect plans retention.

### Cardmarket

- Continue PC Chrome helper for offer samples (API host GET of Cardmarket returns 403).
- Public API only returns stored URLs + stored snapshots.
- Unique-link (name + collector + set overlap) may fill URLs; **never overwrite a verified Save.**
- 151-style gaps (`mew11` vs `001`) stay unmatched until a human Save. Design a “missing link” state; do not hide it.

### Scale (be honest)

- Catalogue is tens of thousands of prints × languages, not millions of users on day one.
- Bottleneck is **accuracy and Cardmarket identity**, not QPS.
- Do not introduce a matching microservice, GPU cluster, or event bus for v1.

### Suggested build slices (architect)

1. Harden scan API (auth-ready, rate limits already exist, stable result schema).
2. Flutter scan client against existing `/api/v1/scans`.
3. Users + collection tables; confirm-scan writes an owned single.
4. Cardmarket snapshot display in the app (read-only).
5. Helper/ops unchanged until sell requires more.

---

## 10. Constraints the architect must not “simplify away”

| Constraint | Why |
|---|---|
| No Cardmarket HTML from the API host | GET is 403; helper on a PC |
| Helper on a PC | Must share the user’s Cardmarket session cookies |
| Exact print, not Pokémon name | Core promise |
| EN + JA + ZH-CN + ZH-TW as separate rows | Visual match |
| Flutter ML preprocess on every scan | Language + collector + warp before DINOv2 |
| No MKM API | Not wired |
| PokeSingle stays Pokémon | Brand; other TCGs = other name |

---

## 11. What we need from each role

### Designer — please produce

- Brand directions for PokeSingle (logo, type, colour, how a card sits in the UI).
- Full scan flow (camera → required ML warp/OCR → wait → five result states).
- Card identity component (art, name, set, number, language, CM button, price samples).
- Collection IA (Phase 2) so Scan stays home.
- Empty / error / retake / no-match — not only the happy path.
- App icon + store screenshots: Scan. Collect. Sell.

Out of scope for the first design pass: marketplace checkout, social, binder 3D.

### Architect — please produce

- Target diagram: Flutter, API, catalogue volume, helper, staging/prod.
- Identity model: `print` (catalogue row) vs `owned single` vs `Cardmarket product URL` vs `price snapshot`.
- Auth and “first scan before signup.”
- How Flutter ML output maps onto `POST /scans` (`language`, `collector_hint`, `ocr_text`, `skip_detect`).
- What stays in this repo vs a new Flutter repo.
- Phase 1 / 2 / 3 sequence.

Out of scope: replacing DINOv2, GPU cluster.

---

## 12. Open questions (decide in the first workshop)

1. Must the first scan require an account?
2. Do we show EUR only, or follow Cardmarket locale?
3. Is “Sell” in v1 just “open Cardmarket,” or do we hold a waitlist?
4. How long do we keep scan photos for review?
5. Flutter-only, or keep web scan as a fallback?
6. Who runs the Chrome helper in production?

---

## 13. One-page summary

| | |
|---|---|
| **Product** | PokeSingle — Pokémon singles: scan, collect, sell |
| **Promise** | The exact print and its Cardmarket single |
| **First surface** | Phone camera |
| **Client** | Flutter (iOS + Android) |
| **Brain** | Existing FastAPI + DINOv2 + RapidOCR + SQLite catalogue |
| **Market** | Europe / Cardmarket, EUR, EN+JA+ZH prints |
| **Not** | Multi-TCG tracker, live Cardmarket from the API host |
| **Now** | Experiment works; needs brand, mobile, accounts, collection |
| **North star** | Photo of a card becomes an owned, listable single |

If design and architecture disagree, keep the north star: **wrong print = wrong product.**
