# PokeSingle — architecture & design on the existing backend

**For:** designer and architect  
**Companion:** [pokesingle-brief.md](./pokesingle-brief.md)  
**Rule:** FastAPI recognition stays. Flutter does not replace DINOv2. Flutter **does** run an on-device ML preprocess on every scan (not optional) so the server receives a rectified card plus language and collector evidence.

---

## 1. Stance

The repo already solves **which print is this?** The client’s job is to feed that stack a card-shaped, sharp image and every signal that narrows the catalogue.

| Layer | Status | Role |
|---|---|---|
| FastAPI `/api/v1` | Built | Ranker: DINOv2 + RapidOCR |
| Catalogue + vectors | Built (offline builder) | Print identity |
| RapidOCR + language on server | Built | Second OCR + rerank (safety net) |
| Cardmarket URLs + helper | Built | Stored Singles URL + cached EUR |
| Next.js UI | Experiment | Not the product client |
| Chrome helper on a PC | Built | Fetches Cardmarket HTML; API host cannot |

```
┌──────────────────────────────────────────────────────────────────┐
│  Flutter (required preprocess on every shutter)                  │
│  still JPEG → quad warp → ML Kit text → language + collector     │
│  POST /scans (warped image + hints)                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│  FastAPI                                                         │
│  if skip_detect: skip OpenCV   else: detect_and_rectify          │
│  constrain catalogue by client language when present             │
│  DINOv2 top-k → RapidOCR + collector rerank (merge client OCR)   │
└──────────────┬───────────────────────────┬───────────────────────┘
               │                           │
        catalog.sqlite + ACTIVE     Chrome helper on PC
        vectors                     Cardmarket snapshots
```

Catalogue builder (`compose.catalogue.yaml`) is not in the app runtime.

---

## 2. Identity model

| Object | Today | Meaning |
|---|---|---|
| **Print** | `cards.id` e.g. `en:sv03.5-001` | language + set + collector + art |
| **Scan** | `POST /scans` | one photo, one `ScanStatus` |
| **Cardmarket product** | `cards.cardmarket_url` | Singles URL on that print |
| **Price snapshot** | helper tables | cached offers for that URL |

Phase 2: **User**, **Owned single** = user + print id + qty + condition + scan_id.

Collection keys off `cards.id`, never the Pokémon display name.

---

## 3. Existing API → UI

| UI | API |
|---|---|
| Boot | `GET /health` — block scan if `ready=false` |
| Gallery HEIC if needed | `POST /images/prepare` |
| Shutter | `POST /scans` |
| Confirm / not this / reject | `POST /scans/{id}/feedback` |
| This-device history | `GET /session/results` |
| Manual pick | `GET /cards?q=` |
| Art | `candidate.image_url` |
| Cardmarket | `candidate.cardmarket_url` |
| EUR | `GET /cardmarket/prices?url=` |
| Refresh offers | `POST /cardmarket/jobs` |

Do not ship `/review*` or `/cardmarket/helper/*` in the app.

### `POST /scans` — what Flutter always sends

Multipart, JPEG, long edge 1600–2000px, under 12 MB.

| Field | When |
|---|---|
| `image` | Warped card if quad succeeded; else cropped frame |
| `skip_detect` | `true` after a successful on-device warp |
| `crop_*` / `rotation` | Only if warp failed and user/manual crop is used |
| `language` | Detected code `en` \| `ja` \| `zh-cn` \| `zh-tw`, else `auto` |
| `collector_hint` | **Add this.** Best collector token (`151/165`, `001`, `SVP001`) |
| `ocr_text` | **Add this.** Newline-joined ML Kit lines (name, HP labels, set text) |
| `client_detect` | **Add this.** `warped` \| `crop` \| `full_frame` so we can measure accuracy |

`language` + `collector_hint` + `ocr_text` are first-class ranker inputs, same idea as server RapidOCR. Architect wires them into `resolve_search_languages` and `extract_collector_candidates` / `rerank` instead of ignoring them.

Server still runs RapidOCR on the uploaded crop. Client OCR is extra evidence, not a replacement.

**Statuses (design all five):** `matched` · `uncertain` · `no_match` · `retake` · `failed` (including HTTP 503 + `Retry-After`).

---

## 4. Information architecture

```
Scan (home)     Collect          Sell (later)
Camera+ML       My singles       Owned single → Cardmarket URL
Result          Print detail
Search
```

Scan is the default tab.

```
live preview (guide + sharpness gate)
  → takePicture() full still
  → REQUIRED ML preprocess (quad, warp, text, language, collector)
  → POST /scans
  → status screen
       matched    → one print → confirm
       uncertain  → 2–3 prints → pick
       no_match   → retake or GET /cards
       retake     → shutter
       failed     → retry
  → POST feedback
```

Result sheet: catalogue art, name, set, number, language, Cardmarket URL or “no URL”, cached EUR or “pending”, That’s it / Not this / Scan again. No scores on `matched`.

---

## 5. Flutter ML layer (required, every scan)

This is not a later enhancement. Slice A does not ship without it.

On-device models **do not** return a `card_id`. They return geometry and text that raise ranker precision (especially EN vs JA vs ZH and `001` vs another print of the same art).

### Pipeline (always run, degrade per step)

```
still JPEG
  1. Card quad
       iOS: Vision rectangle / contour
       Android: ML Kit document / object detector tuned to a card-sized quad
       → 4 corners or fail
  2. Warp to upright rectangle (same contract as detect_and_rectify)
  3. Quality gates on the warp (or on the crop if warp failed)
       min side, Laplacian variance — align with server thresholds
  4. ML Kit Text Recognition v2
       Latin + Japanese + Chinese (run all; do not make the user pick a model)
  5. Language from script + printed labels
       EN phrases: BASIC, Stage 1, Weakness, Retreat
       JA: ポケモン, たね, ワザ, にげる
       ZH-CN vs ZH-TW: 宝可梦/这个 vs 寶可夢/這個 (same split as api/app/recognition/language.py)
  6. Collector parse
       tokens like 001/165, 151/165, SVP 001, TG01 — same shape as rank.COLLECTOR_RE
  7. POST warped (or cropped) JPEG + language + collector_hint + ocr_text
```

If a step fails, **continue**:

| Failure | Upload | Fields |
|---|---|---|
| No quad | Manual/auto center crop of the guide | `skip_detect=false`, `client_detect=crop` |
| No text | Still upload warp | `language=auto`, empty hints; server RapidOCR |
| Language low confidence | `language=auto` | still send `ocr_text` and collector if any |
| Collector missing | omit `collector_hint` | language still sent |

The ML **module is always invoked**. Empty hints are allowed; skipping the module is not.

### Signals that increase accuracy (priority)

1. **Rectified card** — largest gain; DINOv2 matches catalogue scans, not desks.
2. **Language** — restricts vectors to `en` / `ja` / `zh-cn` / `zh-tw` (backend already supports `language=` and `card_languages` mask).
3. **Collector number** — rerank already boosts OCR-consistent numbers; client digits help when RapidOCR misses JP/CN.
4. **Raw OCR lines** — name similarity in `rerank`; client often sees larger type than the server JPEG.

Not in v1: on-device DINOv2, set-symbol CNN, foil classifier, barcode, face, image labeling as ID.

### Live camera (before shutter)

Required UX, cheap, not ML Kit:

- Card-ratio overlay, card ≥ ~70% of guide.
- Preview sharpness; shutter disabled while blurry.
- Rear camera, AF/AE lock on the card, **`takePicture()` still** (not a video framebuffer).

After still: run §5 pipeline, then upload. Do not upload the preview frame.

### Server

- Keep `detect_and_rectify` when `skip_detect=false`.
- When client sends `language` ≠ `auto`, use it as `reason=user` search mask (already in `resolve_search_languages`).
- Merge `collector_hint` / `ocr_text` into OCR evidence before `rerank`.
- Still return `retake` if the image is tiny or blurry.

---

## 6. Backend additions

Phase 1 needs the three form fields above (`collector_hint`, `ocr_text`, `client_detect`). Everything else can wait.

| When | Change |
|---|---|
| Phase 1 | Accept and consume client OCR/language/collector on `POST /scans` |
| Mobile auth | Bearer device token mapped to current session |
| Phase 2 | `users`, `owned_singles`, `POST/GET /collection` |
| Prices | poll `GET /cardmarket/prices` on the card sheet |

No GraphQL, extra matching service, Redis vectors, or GPU for v1. Honour `scan_wait_limit` and 503.

---

## 7. Auth

Phase 1: cookie session or device token; scan without signup.  
Phase 2: account merge. Helper credentials never ship in the app.

---

## 8. Repo & deploy

```
scanapp/            FastAPI, catalogue builder, helper, experiment web
pokesingle_app/     Flutter: lib/scan/ml, lib/scan/camera, lib/api
```

| Env | API |
|---|---|
| Local | API on LAN/HTTPS |
| Staging | `https://staging-scan.auctaro.com/api/v1` |
| Prod | same pattern |

Helper stays on a PC against that API. Catalogue arrives via offload tarball, not from Flutter.

---

## 9. Status → UI

| `ScanStatus` | UI | CTA |
|---|---|---|
| `matched` | One print | That’s it |
| `uncertain` | 2–3 prints | Pick |
| `no_match` | Miss | Scan / Search |
| `retake` | Tip | Camera |
| `failed` | System | Retry |

Language chips: English / Japanese / 简体 / 繁體. Missing Cardmarket URL is a data gap on the print, not a scan failure.

---

## 10. Delivery

**Slice A — Flutter scan + required ML + existing API**

- Health, still capture, overlay, sharpness gate.
- Quad warp, ML Kit multilingual text, language + collector.
- `POST /scans` with hints; five result states; feedback; prices.
- Backend: persist/consume `collector_hint` and `ocr_text`.

Exit: phone scan is at least as accurate as web, and better on JP/CN and off-angle cards.

**Slice B — Collect** — owned singles keyed by print id.  
**Slice C — Sell** — Cardmarket URL from the owned print; later native listing is new API.

---

## 11. Technical risks

| Risk | Handling |
|---|---|
| Quad fails on sleeves / glare | Fall back to guide crop; `skip_detect=false` |
| ML Kit misses JP/CN | Send warp anyway; server RapidOCR; keep `language=auto` |
| Wrong language mask | Only set `language` above a confidence floor; else `auto` |
| Wrong collector | Low-confidence tokens omitted; ranker already treats OCR as soft |
| API 503 | Single in-flight scan; Retry-After |
| Cardmarket empty prices | Helper lag; UI “pending”, not 0 EUR |

---

## 12. Locked for v1

- FastAPI + DINOv2 + RapidOCR matcher.
- Flutter client with **required** on-device preprocess (warp + text + language + collector).
- Catalogue languages: `en`, `ja`, `zh-cn`, `zh-tw`.
- Cardmarket URLs from DB; prices from helper snapshots.
- Offline catalogue builder.

---

## 13. Next artefacts

**Designer:** camera with overlay + disabled shutter; processing; five results bound to `ScanResponse`; card sheet; collection list layout.

**Architect:** Flutter `lib/scan/ml` (Vision + ML Kit text, language map copied from `language.py`, collector regex copied from `rank.py`); extend `POST /scans`; API client; `owned_singles` sketch keyed by `cards.id`.
