# Japanese set recovery: plan to finish (2026-11-06)

Goal: every Japanese card in the TCG Collector checklist is in the staging catalogue with an image, vectors (or a recorded reason for none) and a verified Cardmarket link. Staging only; production is a separate decision.

## Where things stand

| | Value |
|---|---|
| Catalogue (newest schema) | `pokesingle_completion_20261028_neo2057`, 16,319 Japanese cards, 16,318 with a Cardmarket link, 313 without vectors (mostly printing alternatives by design) |
| Recovery run | `data/catalogue-gaps/ja-set-recovery-20261029-v3/` (local only) |
| Recovery code | `codex/ja-set-recovery-local-scraper` @ `915ec1c`, not merged |
| Checklist groups | 336: 281 absent sets (10,683 listed cards) and 55 partial sets (5,234 listed, 3,674 already in the catalogue) |
| Checklist rows | 15,261 |
| Rows with an image file | 14,439 (14,297 associated, 142 with several official candidates) |
| Rows without an image | 822 across 145 groups (queue: `review/targeted-image-recovery-queue-20261031.csv`) |
| Cardmarket | 13,875 products listed from 276 routes. Per row: 13,656 one candidate, 224 several, 1,356 none. All unverified |
| Verified mappings / vectors | 0 / two pilot folders only |

**Image sizes (sampled per source, shortest side):** official 750–868, Pooka 750, TCG Collector ~590, source-linked 600, TCG Stats ~320, PokeDataVault ~287, the 5,129 `images/ja-ref-*` reference scans 274. About 6,900 rows have only an image under 500 px. All of them pass the catalogue gate used so far (shortest side ≥ 180, blur ≥ 40); none pass the 500 × 700 bar the recovery notes use.

## Decisions (owner accepted all four recommendations on 2026-11-06)

## Decisions as originally posed

1. **Minimum image size for vectors.** Recommended: keep the existing catalogue gate (≥ 180 px, blur ≥ 40), always use the largest exact image a row has, and list sub-500 rows for later upgrade. Using 500 × 700 would leave about 6,900 rows without vectors.
2. **Publish in waves or once.** Recommended: build vectors and run the look-alike pass once across all rows, but publish in about four era waves (see step 7). The single JASETS candidate on 2026-10-17 had to be rolled back twice and was hard to bisect.
3. **Card names.** The checklist rows carry English names only. Recommended: Japanese names from the official Pokémon Card site where it supplied the image, otherwise the English name as `view_title` and the Japanese name left for a later pass.
4. **Rows with no exact image after the time box (step 4).** Recommended: add them to the catalogue without an image (`has_image = 0`, no vectors) so they get a page and price, and keep them in the queue.

## Steps

### 1. Baseline (half a day)

- Confirm which schema staging serves. `scan.pokesingle.com` did not resolve on 2026-11-06; check DNS and `/api/v1/health` first. If staging is not on `neo2057`, re-run the audit against the served schema.
- Merge or rebase `codex/ja-set-recovery-local-scraper` onto `staging` so the recovery code lives with the catalogue tools.
- Build one ledger, `recovery-ledger.jsonl`, with one line per checklist row: group, printed number, names, chosen image, image source and size, Cardmarket candidates, status, reason. Every later step updates this file only. Fill the empty `printing-inventory.jsonl`, `existing-matches.jsonl` and `new-or-incomplete-printings.jsonl` from it.

### 2. Remove rows already in the catalogue (1 day)

- For the 55 partial groups, match each row to an existing `ja:` card on set code + printed number, with name agreement (the gate-4 rule from the 2026-10-16 handoff).
- Matched rows become `existing-matches.jsonl`. They are not new cards. Only an image or link improvement may come from them, and only as a separate small candidate.
- Unmatched rows are new cards. Expected: about 11,500–11,600 new cards (10,683 absent + roughly 1,560 partial gaps, minus duplicates).
- Also check absent groups for cards that exist under another set id (reprints filed elsewhere) by set code + number + name against all 16,319 rows. Hold anything ambiguous.

### 3. Image choice and quality gate (2 days)

- For each new row, pick one image in this order: official site, Pooka, TCG Collector, source-linked, other shops, TCG Stats, PokeDataVault, `images/ja-ref-*` reference scans. Take the first that passes the gate.
- Run `gate_images.py` (size, blur, exact duplicate by SHA-256, name agreement). Read every "differs" item by hand.
- Resolve the 142 rows in `review/official-candidate-variant-review-20261031.csv`. Choose only when the card face (number, stamp, artwork) settles it. Otherwise hold the row with a reason.
- Never give two cards the same image file.
- Output: `image-chosen.jsonl` and a contact sheet per group for a quick visual check.

### 4. The 822 missing images, time-boxed (3–4 days, in parallel with steps 5–6)

- Priority queues first: 86 Misc Promos, 40 Sun & Moon promos, 21 Sword & Shield promos. Use the Hareruya2, CardRush and Toretoku catalogs already found. Associate only when event, year, placement and printed number agree.
- Then the 140 `exact_scan_not_found` rows (identity known). Search by Japanese name + set code + printed number.
- Then the 34 `low_resolution_only` rows: keep the small exact scan if it passes the ≥ 180 gate.
- The 589 `identity_unresolved` rows (mostly event and placement promos): spend at most one pass. Whatever is left ships without an image (decision 4) and stays in the queue with its reason.
- Close the time box and record the counts, even if rows are still open.

### 5. Cardmarket links and product ids (3 days, owner's Chrome)

- **One candidate (13,656 rows):** link only when the route's set, the printed number and the name agree, and the URL is not already on another card (catalogue or this batch). Take the product id from the listing row, the same way as the `en-id-list` work of 2026-10-19.
- **Several candidates (224 rows):** decide from the product page picture. V1/V2 by print run stays one card; read the page before choosing a product id.
- **No candidate (1,356 rows, 402 without an observed route):** finish the 60 groups in `docs/experiments/japanese-remaining-60-route-research-20261029.md` using `collect_shared_listings.py`. Rows still without a product stay unlinked with a reason.
- Cloudflare checks are cleared by the owner only. The collector waits and never clicks.
- Output: `verified-mappings.jsonl` and `held-mappings.jsonl`.

### 6. Vectors and look-alikes (1 day of compute)

- Use the tooling from the last whole-set wave, `data/catalogue-gaps/tcgdex-empty-sets-20261017/build_vectors.py`, with `pick_novec.py` from `japanese-wave2-20261015/`.
- Build pad, square and artwork vectors for every imaged new row. At the vintage wave's pace (about 1,445 cards in 40 minutes) this is about 5–6 hours.
- Run the look-alike pass once over all new rows against the served index and each other at cosine ≥ 0.95. If an existing card is in a group, the new card becomes a printing alternative. Otherwise the earliest printing keeps vectors. Japanese and English twins are not grouped.
- Expect a large share of printing alternatives: deck, half-deck and gift-box sets mostly reprint artwork that is already indexed.
- Report the counts: scannable, printing alternative, display-only, no image.

### 7. Candidates and staging, in waves (about 1 day per wave)

Suggested waves, each a new inactive candidate copied from the one before it:

| Wave | Content |
|---|---|
| A | Partial-set gaps (about 1,560), closest to what is already indexed |
| B | Modern absent sets: Mega Evolution, Scarlet & Violet, Sword & Shield, Sun & Moon |
| C | XY, Black & White, LEGEND, Platinum, Diamond & Pearl |
| D | PCG, ADV, e-Card, VS, Web, vintage promos |

For each wave:

1. `prepare_<wave>_candidate.py` writes `01-create-schema.sql` and `02-seed-and-apply.sql` (ending in the in-database guard), the feature folder, the artwork bundle and the vectors.
2. Upload with checksums, apply with `run_files_tx.py`, check with `verify_<wave>.py`.
3. Switch staging using the release env file only (`docs/planetscale-staging.md`).
4. Run gates 10–14 from the 2026-10-16 handoff: health, the 28-photo regression panel, the earlier eBay panels, real photos for the new wave, and no restart or OOM.
5. Record the wave in `events.jsonl` and `PROCESS-AND-PENDING.md` before the next wave.

**Memory check:** staging has 3 GiB, and scans peak at about 2.1 GiB with 43,695 vectors per mode. Adding up to roughly 11,500 cards can raise that. Measure peak memory after wave B and stop if it goes over 2.6 GiB.

### 8. After staging keeps the last wave

- Export a new phone index for the kept catalogue (`api/scripts/on_phone_index/`) and publish it through ACTIVE.
- Images: these come from shops and archives, not TCGdex. They are served from the staging reference-image volume like the earlier Japanese waves, and they are not mirrored to the R2 bucket (`docs/card-image-cdn.md`). Keep each file's source attribution in the ledger.
- Production promotion is a separate owner decision (handoff section 5, item 6).

## Rough timeline

About 2–3 weeks of working days. Steps 1–3 and 5 decide most of the result. Step 4 is time-boxed so the 822 rows cannot block the other 14,439.

## Done means

- Every checklist row is a catalogue card, an existing match, or held with a written reason.
- Every new card with an image is scannable or a printing alternative, and the reason is recorded.
- Every new card has a verified Cardmarket link and product id, or a held reason.
- Each wave passed gates 7–14 and is recorded with a rollback path.

## Progress log

### 2026-11-06: steps 1–3 run locally

- **Branch:** `claude/ja-recovery-finish` = `staging` + `codex/ja-set-recovery-local-scraper`. Not pushed.
- **Step 2, `api/scripts/ja_set_recovery/match_existing.py`:** of 15,261 checklist rows, **3,555 are already in the catalogue** (3,553 one number match, 2 ambiguous; all in the 55 partial sets) and **11,706 are new** (10,432 in absent sets, 1,274 in partial sets). Matches are set code + printed number only, because catalogue names are Japanese and checklist names are English. Written to `existing-matches.jsonl` and `new-or-incomplete-printings.jsonl`. 13 registry groups have no checklist rows at all; they still need a checklist read.
- **Step 3, `api/scripts/ja_set_recovery/choose_images.py`** (catalogue gate: short side ≥ 180, blur ≥ 40; largest passing image wins). Of the 11,706 new rows:

| Result | Rows |
|---|---|
| Image chosen | 10,258 (of which 2,693 are under 500 px: `upgrade_later`) |
| Same file as another row, held | 395 (reprinted trainers/energies across decks; 325 numbered, 70 unnumbered) |
| No image file | 786 |
| Files exist but fail the gate | 267 (86 are in `ja-ref-899`, WCP) |

  Sources of the chosen images: official 4,127, Pooka 3,052, reference scans 1,198, PokeDataVault 1,058, TCG Stats 498, TCG Collector 234, other 91. Output: `image-chosen.jsonl`, `image-chosen-summary.json`.
- The 142 multi-candidate official rows and the variant check are not decided yet: they need the card face looked at, not just a size test.

### Not done, and why

Steps 4–7 cannot be finished from this session without the owner:

- **Step 4/5:** image searches on shop sites and every Cardmarket page read go through the owner's Chrome, with Cloudflare checks cleared by hand.
- **Step 6:** vectors are built in the amd64 container with the DINO model and the live index; `build_vectors.py` expects `/repo` and `/work` mounts and the served vectors directory.
- **Step 7:** writing candidate schemas and switching staging needs the PlanetScale admin role and `auctaro-staging` access. Staging hostnames did not resolve from here.

### 2026-11-06 (later): step 5 done, steps 6 records and vectors started

- **Cardmarket pages, `match_cardmarket.py`:** the listing pages were already collected (276 routes + 29 shared pools). A new card is linked only when exactly one product agrees on printed number and English name (level/era tags such as `Lv.42`, `[GL]`, `Team Plasma` ignored). 8,761 matched. 116 of those pages are already on a catalogue card (some look wrong: zh-tw and en cards pointing at Japanese products; list in `catalogue-url-collisions-20261106.txt`), so those rows are held. **Linked: 8,645. Held: 3,061** (1,958 no product with that number, 430 unnumbered without a name match, 202 number matches but name differs, 132 several products agree, 126 url claimed by several rows, 116 page already on a catalogue card, 97 unnumbered name not unique).
- **Product ids, `read_product_ids.py`:** read from Cardmarket list view in the owner's Chrome (no Cloudflare stops). The list view shows at most 10 pages (300 rows), so the four biggest promo sets were read again in descending order. 26 ids are already on English XY promo cards (`en:xyp-*`, which carry Japanese XY-P product ids) and are held (`catalogue-id-collisions.json`). **Linked cards with a product id: 8,619 of 8,645.**
- **Card records, `prepare_cards.py`:** `cards.json` has all 11,706 new cards: id `ja:<set>-<number>`, English name, image, Cardmarket url and id. Partial sets keep their catalogue code; absent sets use their checklist code when unique, otherwise `jr-<name>` (132 sets). Unnumbered rows are `u01`, `u02`… One id repeats (`ja:SP-123`: the Lance's Charizard / Pikachu VMAX conflict) and is held. 10,258 have an image, 8,085 have both image and Cardmarket page.
- **Vectors, `build_vectors.py`:** built locally with `dinov2_small.onnx` from the staging data snapshot and the API's pinned numpy/pillow/onnxruntime. Re-embedding two cards of the 2026-10-17 wave here gave cosine 1.0 against that wave's stored vectors. Then `decide_lookalikes.py` applies the 0.95 rule against the local copy of the served pad index (`data/android-embedding-research-20261023/catalogue/vectors/pad`, 43,695 vectors).
