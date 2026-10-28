# Ship the card index to every phone (plan, 2026-10-28)

Goal: every Android and iPhone user gets the phone's own card match and the provisional card ("checking"), not only the two test phones.

## Today

- The phone match needs four files in the app's support folder, `card_index/`: `card_index.f16.bin` (32 MB, 43,695 × 384 float16), `card_index.ids.txt` (0.5 MB), `card_index.meta.tsv` (1.6 MB: name, number, printed number, set total, language per row), `card_index.version.json`.
- Only the A55 and the iPhone 15 have them: copied by hand over USB. On every other phone the switches are on (PokeSingle main, `ON_PHONE_INDEX` / `PHONE_PROVISIONAL` and the iPhone ones), but no files means no index, so nothing changes for them. Nothing breaks.
- The files were built from the research copy of the catalogue vectors (`data/android-embedding-research-20261023/catalogue/vectors/pad`), not from the server's live snapshot. Staging's own `/data/vectors/pad` is only 1.7 MB, so the live vectors come from the recognition artifacts bundle (`api/app/recognition/artifacts.py`, `catalogue_version`). Step 0 settles this.

## Choice

Download from our own server on first use, versioned (chosen over putting the files in the app, +34 MB and a release per update, and over the stores' asset packs, which also need a release per update). New card sets reach phones without an app release.

## Rules

Each change behind its own switch, default off until its gate passes. Read-only on staging until a step says otherwise; the owner turns server switches on in Dokploy. Draft PRs. No photos or OCR text anywhere. Production unchanged until the owner decides.

## Steps

### 0. Build the phone index from the server's own vectors (server, offline)

A script under `api/scripts/on_phone_index/` that exports the phone index from the exact snapshot the server ranks with: the same ids in the same order, float16 vectors, the card details file from the same catalogue (with set totals), and `version.json` with `model_id` (2ddf6ec79e37), the server's `catalogue_version`, the ids' sha256 and each file's size and sha256.

**Gate:** row count and ids identical to the server's snapshot; top-20 on the stored phone vectors identical to the server's float32 search on at least 99% of scans and the stage 1 rule unchanged (the check from `check_compressed_index.py`).

### 1. Publish it (server)

Publication is manual: after each catalogue snapshot change, export and vet a matching candidate, copy it into a versioned folder and atomically update ACTIVE (see api/scripts/on_phone_index/README.md). Until then the manifest returns 503 and phones keep the previous index. Two read-only routes: `GET /api/v1/card-index/manifest` (version, model id, catalogue version, per-file name, bytes, sha256, url) and the files themselves, with ETag and long cache headers so Cloudflare serves repeat downloads. Switch: `CARD_INDEX_PUBLISH`.

### 2. Download on the phone (Android and iPhone, shared Dart)

On app start (and at most once a day): read the manifest; if the model id matches the phone's fingerprint model and the version differs from the one on the phone, download the files to a temporary folder (Wi-Fi only by default, resumable, in the background), check each sha256, then swap the folder in one step. Never delete a working index before the new one is checked. Log `card_index.download` (state, bytes, ms, version) through the existing diagnostics. Switch: `CARD_INDEX_DOWNLOAD`.

### 3. Version rules on the phone

- Use the index only when its `model_id` equals the phone's fingerprint model.
- An index older than the server's catalogue is still used (the server checks every scan, so the cost is missing new-set cards, not wrong cards), and the phone logs how old it is.
- The provisional rule is unchanged: name and number must name exactly one card in the top 20; a card from a set the phone doesn't have yet simply finds no match.

### 4. Test

On the A55 and the iPhone 15: remove the hand-copied files, let the app download them (and check the swap with a second, newer version). Then one 16-photo round per phone. **Gate:** the download finishes and the checksum holds on both phones, the provisional cards appear as in the hand-copied rounds, 0 provisional cards the server overturns, 0 wrong cards.

## Size and cost

About 34 MB per phone per catalogue version (float16; the int8 version is about half the size but was not checked as closely, so float16 stays). Download once per catalogue change, over Wi-Fi by default.

## Not in this plan

Matching from the best live frames before the shutter (the earlier plan's step 2), and making the index smaller.
