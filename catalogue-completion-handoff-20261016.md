# Catalogue completion — handoff (2026-10-16)

This replaces the 2026-10-15 handoff (no longer in the repo root; its plan and the English work are summarised in `PROCESS-AND-PENDING.md`). It covers where the work stands, how each step is done, what is left, and the rules to keep.

**The run folder** holds the full history:

- Folder: `data/catalogue-completion/20261004-01/`.
- `PROCESS-AND-PENDING.md` is the narrative history.
- `events.jsonl` is one line per step, with evidence hashes.
- Read the last few sections of both before starting.

**Start here:**

1. Confirm what staging serves: `curl -s https://scan.pokesingle.com/api/v1/health` should show `PS-CATALOGUE-EN-JA-ID-20261018` and `ready: true`. If it shows something else, read the end of `events.jsonl` first.
2. Read sections 3 (rules), 4.8 (gates) and 4.9 (variants).
3. Create a 3-hour read/write PlanetScale role (section 8) and run the "Useful queries" gap count to confirm the numbers in section 2.
4. Pick the next item from section 5. The 16 sets are on staging, and 1,586 of those cards now have a Cardmarket link. English view titles are on the same catalogue. `ja:S5R-006`, `ja:S3a-030` and `ja:CP6-011` have images and features and no scan vectors. Investigate those three later.

## 1. Goal

Complete the scan catalogue on **staging** (never production) so that:

- every card has a reference image;
- every card that can be told apart visually has vectors (it is scannable);
- every card has a working Cardmarket link and price.

Each change ships as a new inactive PlanetScale candidate schema. It is checked, switched on staging, tested with real-photo panels, and kept only if nothing regresses.

## 2. Where things stand

| | Value |
|---|---|
| Staging serves | `PS-CATALOGUE-EN-JA-ID-20261018` (schema `pokesingle_completion_20261018_jaid`) |
| Feature dir / artwork dir | `reference-features/20261017-ja-sets` / `artwork/PS-CATALOGUE-EN-JA-SETH3-20261017` |
| Cards | 50,270 in total, of which 16,319 are Japanese |
| Vectors | 43,695 per mode (pad and square), plus 21,552 artwork regions. Health reports 44,021 indexed, of which 16,318 are Japanese, because that count is cards with an image |
| Japanese with an image | 16,318 of 16,319 (**1 left**, `ja:neo2-057`) |
| Japanese with a Cardmarket link | 16,291 of 16,319. 1,586 of the new cards are linked. 27 new cards and the Gengar extra are still without a page |
| Japanese with a Cardmarket product ID (price) | 12,266 (**2,440 left**) |
| English | All 109 gaps closed (see the 2026-10-15 sections of `PROCESS-AND-PENDING.md`) |
| Staging API memory | 3 GiB RAM + 1 GiB swap (PR IoannisChadjiminas/scanapp#47, merged 2026-10-16 06:08Z) |
| PlanetScale storage | 72 `pokesingle*` schemas, about 22 GB in total, including the inactive JASETS schema that was not kept. Each new candidate is a full copy and adds about 0.35–0.45 GB. Old schemas are kept on purpose (delete nothing); ask the owner before any clean-up |
| Staging disk | 75 GB disk, 34 GB free; the data volume is 13 GB. Each image wave adds 0.1–0.25 GB |
| Local disk (owner's Mac) | Run folder 149 GB; 251 GiB free |
| Production | Untouched |

### Candidate chain (newest last)

Each candidate is a full copy of its parent plus one change.

| Import ID | Schema | What it added |
|---|---|---|
| PS-CATALOGUE-EN-ENFIVE-MFBV-20261015 | …_enmfbv | English finished (MFB energies split into grey and blue) |
| PS-CATALOGUE-EN-JA-LINKS-20261015 | …_jalinks | 1,317 Japanese Cardmarket links |
| PS-CATALOGUE-EN-JA-IDS-20261015 | …_jaids | 756 Cardmarket product IDs (prices) |
| PS-CATALOGUE-EN-JA-W2-20261015 | …_jaw2 | 372 modern Japanese images (349 with vectors) |
| PS-CATALOGUE-EN-JA-PCG-20261015 | …_japcg | 722 PCG-era images (719 with vectors) |
| PS-CATALOGUE-EN-JA-VINTAGE-20261016 | pokesingle_completion_20261016_javin | 1,445 vintage images (1,442 with vectors) |
| PS-CATALOGUE-EN-JA-FIX-20261016 | pokesingle_completion_20261016_jafix | 275 official Japanese names; 34 Cardmarket links fixed (24 replaced, 10 cleared) |
| PS-CATALOGUE-EN-JA-NEO2-20261016 | pokesingle_completion_20261016_janeo2 | 15 neo2 images with vectors, 14 official names, 2 unrelated links cleared. `ja:neo2-057` still has no image |
| PS-CATALOGUE-EN-JA-LINKS2-20261016 | pokesingle_completion_20261016_jalinks2 | 279 Japanese Cardmarket links (173 exact, 9 number-only, 97 unique vintage names). Features and vectors unchanged |
| PS-CATALOGUE-EN-JA-CRAWL-20261016 | pokesingle_completion_20261016_jacrawl | 629 links from the MC, SV4a and Forbidden Light JP product lists (617 exact, 12 number-only). 644 products inserted. Features and vectors unchanged |
| PS-CATALOGUE-EN-JA-NEO4-20261016 | pokesingle_completion_20261016_janeo4 | One image and vectors for `ja:neo4-229`. Name set to わるいヘルガー from the scan. Collector number stays 229 |
| PS-CATALOGUE-EN-JA-MP-20261016 | pokesingle_completion_20261016_jamp | Images and vectors for `ja:M-P-101` through `ja:M-P-127`. Official scans; each face prints that number |
| PS-CATALOGUE-EN-JA-LINKS3-20261016 | pokesingle_completion_20261016_jalinks3 | Eight links where the product row already named the card and the URL was unused. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS4-20261016 | pokesingle_completion_20261016_jalinks4 | Five links where exactly one product title agrees with the card name. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS5-20261016 | pokesingle_completion_20261016_jalinks5 | Three vintage links where one product is the species and one card has exactly that Japanese name. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS6-20261016 | pokesingle_completion_20261016_jalinks6 | Nine misplaced pages moved onto the card named by the product code. Price ids unchanged. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS7-20261016 | pokesingle_completion_20261016_jalinks7 | One link, `ja:neo1-086` Ecogym, the only card and product of that name in the set. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS8-20261016 | pokesingle_completion_20261016_jalinks8 | 136 links where the installed scan's TCG Collector title equals exactly one unused product. `ja:neo4-097` Dark Porygon2 stays unlinked. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS9-20261016 | pokesingle_completion_20261016_jalinks9 | Four links whose stored product label agrees with the scan title: Mail from Bill, Nidoran [M] at WEB 002, blank-name Chansey, Dark Porygon2. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS10-20261016 | pokesingle_completion_20261016_jalinks10 | Twenty links from Cardmarket page pictures: nine gym pairs and the two Houndour cards. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS11-20261016 | pokesingle_completion_20261016_jalinks11 | Two Ruin Wall links. V1 is the tablet on `ja:neo2-054`. V2 shows an Aerodactyl and is on `ja:neo2-057`. No image was added. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS12-20261016 | pokesingle_completion_20261016_jalinks12 | Six live-page links: Hiroshima's Pikachu, Fukuoka's Pikachu, Riolu, Mega Zeraora ex, Boss's Orders - Ghetsis, and the Japanese Gyarados Star moved off `en:ex13-8`. Price ids unchanged. Features unchanged |
| PS-CATALOGUE-EN-JA-LINKS13-20261016 | pokesingle_completion_20261016_jalinks13 | Blaziken extra shares the `ja:S8b-217` page. Gengar extra loses price id 558478. Both extras leave the scan index. Artwork bundle unchanged |
| PS-CATALOGUE-EN-JA-LINKS14-20261016 | pokesingle_completion_20261016_jalinks14 | `ja:SV-P-272` linked to Energy Search (272). The page picture is エネルギー転送 272/SV-P. Price id 838366 stays. Features unchanged |
| PS-CATALOGUE-EN-JA-SETS-20261017 | pokesingle_completion_20261017_jasets | 1,613 cards from the 16 absent sets (1,334 with vectors, 279 printing alternatives). Not kept: two Charizard panel photos changed best match. Schema and files stay. Do not re-apply its seed SQL |
| PS-CATALOGUE-EN-JA-SETH-20261017 | pokesingle_completion_20261017_jaseth | Same cards, with `ja:S5R-006` and `ja:S3a-030` removed from the scan index. Not kept: `ebay-ja_PMCG1-021-1` moved to `ja:CP6-011`. Schema and files stay |
| PS-CATALOGUE-EN-JA-SETH3-20261017 | pokesingle_completion_20261017_jaseth3 | Same cards, with `ja:CP6-011` also removed from the scan index. Kept. Best card and status match JALINKS14 |
| PS-CATALOGUE-EN-JA-CM-20261017 | pokesingle_completion_20261017_jacm | 1,586 Cardmarket links for the 16 sets, where the set code, number and name agree. 25 title mismatches and 2 already-used urls stay unlinked. No product ids. Features and vectors unchanged |
| PS-CATALOGUE-EN-JA-VIEW-20261018 | pokesingle_completion_20261018_jaview | JACM plus English `view_title`. Matching `name` is unchanged. 16,313 of 16,319 Japanese cards have a view title. Six stored pages belong to a different card and were not copied |
| PS-CATALOGUE-EN-JA-ID-20261018 | pokesingle_completion_20261018_jaid | JAVIEW plus 4,016 product ids on cards that already had that page URL. Names, view titles, images and vectors are unchanged. This is what staging serves |

### Rollback

Every switch archived the previous release file under `/etc/scanapp-staging/catalogue-rollback/<name>/catalogue-release.env.before` on `auctaro-staging`.

| Archive folder | Previous candidate |
|---|---|
| `ja-links-20261015` | MFBV |
| `ja-ids-20261015` | JALINKS |
| `ja-w2-20261015` | JAIDS |
| `ja-pcg-20261015` | JAW2 |
| `ja-vintage-20261016` | JAPCG |
| `ja-fix-20261016` | JAVIN |
| `ja-neo2-20261016` | JAFIX (first neo2 switch, rolled back the same day) |
| `ja-neo2-keep-20261016` | JAFIX (the release to restore if this neo2 switch is rolled back) |
| `ja-links2-20261016` | JANEO2 |
| `ja-crawl-20261016` | JALINKS2 |
| `ja-neo4-20261016` | JACRRAWL |
| `ja-mp-20261016` | JANEO4 |
| `ja-links3-20261016` | JAMP |
| `ja-links4-20261016` | JALINKS3 |
| `ja-links5-20261016` | JALINKS4 |
| `ja-links6-20261016` | JALINKS5 |
| `ja-links7-20261016` | JALINKS6 |
| `ja-links8-20261016` | JALINKS7 |
| `ja-links9-20261016` | JALINKS8 |
| `ja-links10-20261016` | JALINKS9 |
| `ja-links11-20261017` | JALINKS10 |
| `ja-links12-20261017` | JALINKS11 |
| `ja-links13-20261017` | JALINKS12 |
| `ja-links14-20261017` | JALINKS13 |
| `ja-sets-20261017` | JALINKS14 (the release restored after JASETS was switched and rolled back) |
| `ja-seth-20261017` | JALINKS14 (the release restored after JASETH was switched and rolled back) |
| `ja-seth3-20261017` | JALINKS14 (the release to restore if this JASETH3 switch is rolled back) |
| `ja-cm-20261017` | JASETH3 (the release to restore if this link switch is rolled back) |
| `ja-view-20261018` | JACM (the release to restore if this view-title switch is rolled back) |
| `ja-id-20261018` | JAVIEW (the release to restore if this product-id switch is rolled back) |

The compose file before the memory change is in `api-mem-3g-20261016/`. Older archives for the English work (for example `en-mfbv-20261015`) are in the same folder.

To roll back, install the `.before` file as `/etc/scanapp-staging/catalogue-release.env` and restart the API (section 4.7).

## 3. Rules (do not break)

- **Staging only.** Production is out of scope until the owner decides.
- **Scanner unchanged.** Scanner thresholds, ranking, grading, models and preprocessing stay as they are.
- **Delete nothing.** No rows, files or rollback archives. New candidates and new artifact folders are added next to the old ones. Set wrong files aside in a separate folder instead of removing them.
- **No guessing.** Uncertain cards stay held with a written reason; a plausible guess is not evidence.
- **Image sources.** TCG Collector and official pokemon-card.com are the default Japanese image sources (owner-approved).
- **eBay photos.** Photos for tests only. Check every photo by eye against the reference before using it (`contact_sheet.py`), and set wrong ones aside with a reason.
- **Cardmarket matching.** Exact set and number matches may be applied without asking per set (owner-approved).
- **Cardmarket crawling.** Do not crawl Cardmarket listing pages from the owner's connection: Cloudflare blocked it on 2026-10-15.
- **Browsing.** Use the owner's Chrome (the Claude in Chrome tools) for TCG Collector and eBay: one page every 15 seconds, and stop immediately at any "Just a moment / Verify you are human" page.
- **PlanetScale roles.** The owner gave standing approval to create short-lived roles when needed. Use read/write for 2–3 h, admin for 1 h; admin is needed only for `CREATE SCHEMA`.
- **Logging.** Record every step in `events.jsonl` and `PROCESS-AND-PENDING.md`.
- **Provenance.** Every new image keeps its source: `cards.remote_image_url` is the source URL, and a `reference_metadata` row `catalogue-completion-source:<import>:<card_id>` records the file SHA-256, source kind and permission note. Keep doing this for any new source.

### Ask the owner before

- anything on production;
- a new image source, or downloads outside the approved sources (TCG Collector, pokemon-card.com, eBay test photos);
- any Cardmarket crawling;
- infrastructure changes (compose, memory, env beyond the four catalogue keys);
- deleting or cleaning up schemas, folders or archives;
- merging PRs (the owner merges);
- keeping a candidate whose top match or status changed for any test photo.

## 4. How a wave is done (the working recipe)

The Wave 2 scripts are the templates. Copy them into a new subfolder and change the constants:

- **Modern:** `data/catalogue-completion/20261004-01/japanese-wave2-20261015/`
- **PCG:** `…/pcg/`
- **Vintage:** `…/vintage/`
- **Name and link fixes:** `…/fixes/`

Everything runs in Docker with the API image (`scanapp-api:local-amd64`, `--platform linux/amd64`). It is built from `docker/api.Dockerfile`, and the tag in use was built on 2026-10-14. The Mac is arm64, so the image runs under emulation, which makes vector builds slow. Local runtime data: `data/catalogue-completion/20261004-01/local-first-validation-20261014/en109-49-runtime-data`. Model mount: `…/local-first-validation-20261014/staging-data-snapshot/models:/data/models:ro` (DINOv2 SHA-256 `2ddf6ec7…ce1146`).

The release env (`/etc/scanapp-staging/catalogue-release.env`, and the local copies `batch-preparation-20261014/english-109-local-batch-v1/en-<x>-candidate.env`) has exactly four keys: `PLANETSCALE_SCHEMA`, `PLANETSCALE_IMPORT_ID`, `REFERENCE_FEATURES_DIR` and `ARTWORK_BUNDLE_DIR`. Edit them per key, and don't print the files.

### Files each wave produces

| File | What it is |
|---|---|
| `tcgcollector-hits.tsv` | Rows read from the source pages (set, num, English name, image path) |
| `tcgc-images/`, `download.log` | Downloaded source images and HTTP codes |
| `mapped.json`, `mapped-held.json` | Accepted card ↔ image pairs, and held items with reasons |
| `cards-<wave>.json` | Full catalogue rows of the mapped cards (from the current candidate) |
| `gate-report.json` | Size, blur, hash and name check per image |
| `vectors-<wave>/items.json`, `summary.json` | Per-card vector hashes and nearest neighbours |
| `novec.json`, `novec-groups.json` | Printing alternatives and the look-alike groups behind them |
| `prepared-<x>-v1/` | `01`/`02` SQL, `prepared-report.json` (expected counts, file hashes) |
| `staging-upload/` | Tar, file list and checksums sent to staging |
| `ebay-photos/`, `ebay-photos-excluded/`, `panel-*.json`, `contact-*.jpg` | Test photos, set-aside photos with reasons, panel definition, visual check sheets |
| `<candidate>-<panel>-results.jsonl` | Panel results; compare each with the previous candidate's file of the same panel |

### Typical durations

| Step | Time |
|---|---|
| Reading source pages | 15 s per page (17 vintage sets ≈ 5 min) |
| Exporting rows and writing the TSV | About 10–20 min per 700 rows |
| Downloading images | About 0.6 s per image (1,470 ≈ 20 min) |
| Mapping and gate | 2–5 min |
| Vector build | About 1.7 s per card under emulation (722 ≈ 20 min, 1,445 ≈ 40 min) |
| Preparing the candidate | About 10 min (it reads all vectors from the database) |
| Uploading artifacts | 2–5 min |
| Writing SQL | About 20 s |
| Switch to ready | 2–10 min |
| All four test panels | About 10–15 min |

### Useful queries

Remaining Japanese gaps on a candidate schema (replace the schema name):

```sql
SELECT count(*) AS cards,
       sum(CASE WHEN has_image = 0 THEN 1 ELSE 0 END) AS no_image,
       sum(CASE WHEN coalesce(cardmarket_url, '') = '' THEN 1 ELSE 0 END) AS no_link,
       sum(CASE WHEN cardmarket_id IS NULL THEN 1 ELSE 0 END) AS no_price_id
FROM pokesingle_completion_20261016_jafix.cards WHERE language = 'ja';
```

What staging serves right now: `curl -s https://scan.pokesingle.com/api/v1/health` shows `catalogue_import_id`, `ready` and indexed counts per language.

### 4.1 Read TCG Collector set pages (owner's Chrome)

1. Find each set's page ID on `https://www.tcgcollector.com/sets/jp?displayAs=list`.
2. Store a JSON state `{map, queue, res, cur}` in `window.name`.
3. For each set: wait 15 s, then run the step script. It records every `img` whose alt ends in `(...)` and whose source contains `/content/images/` as [alt, path], then navigates to the next set.
4. Keep batches to about 6 pages, because longer batches time out.
5. To export, write the rows into a `<pre>` in the page body and read it with `get_page_text` in chunks of about 370 rows. The JavaScript tool blocks long or URL-like output.
6. Save the rows as a TSV with columns set, num, name and path (e.g. `tcgcollector-hits.tsv`).

Image URLs are `https://static.tcgcollector.com/content/images/<path>`, typically 320×452. A mistyped path returns 404, so transcription errors cannot slip in silently.

### 4.2 Download, map, gate

- **Download:** use curl with a browser User-Agent and the TCG Collector referer, sleeping 0.5 s between requests.
- **Map (modern and PCG):** `map_hits.py` maps exact set and number to the one image-less card.
- **Map (vintage):** `vintage/map_vintage.py` also requires name agreement: the card's Cardmarket slug, the Japanese Pokédex names (PokéAPI cache at `japanese-wave1-20261015/run2/pokeapi-cache.json`), or the glossary. Unnumbered sets are accepted only when their order is consistent.
- **Gate:** `gate_images.py` checks size (≥180), blur (≥40), exact duplicates, and TCG Collector name against the Cardmarket slug. Read every "differs" item; most turned out to be wrong old links or translation variants.

### 4.3 Vectors and look-alikes

- **Build:** `build_vectors_*.py` writes the images as JPEG to `/data/reference-images/ja-<date>-<wave>/` and builds pad, square and two artwork vectors plus the feature fragment. It also reports cosine closeness to the current index (`/data/vectors-<current>`). PCG took about 20 minutes and vintage about 40 minutes under amd64 emulation.
- **Look-alikes:** `pick_novec.py` groups same-artwork Japanese printings at cosine ≥ 0.95. When an existing card is in the group, every new card becomes a printing alternative (features, no vectors). Otherwise the earliest printing keeps vectors. Japanese/English twins are normal and are not grouped.

### 4.4 Candidate

`prepare_<x>_candidate.py` is read-only on PlanetScale. It writes:

- `01-create-schema.sql`;
- `02-seed-and-apply.sql`, which copies the parent, applies the changes and ends with an in-database guard that raises on any mismatch;
- the new feature folder (hard-linked from the parent, with a new `manifest.json`);
- the new artwork bundle;
- a local vectors folder.

Set the constants:

- `SRC`/`SRC_IMPORT` = the candidate staging serves now;
- `S`/`IMPORT` = the new one;
- `BASE_FEATURES`/`BASE_ART` = the current bundles.

### 4.5 Upload artifacts to staging

Tar the new files with `tar --no-xattrs`. `scp` the tar and its `sha256.txt` to `auctaro-staging`. Then, on the volume `/var/lib/docker/volumes/scanapp-scanapp-z1mwj4_scanapp-data/_data`:

1. Check the target folders do not exist.
2. `cp -al` the parent feature folder.
3. `rm` its `manifest.json` (it is a hard link, so this never writes through to the parent).
4. Extract the tar.
5. Run `sha256sum -c`, and confirm the parent manifest hash is unchanged.

### 4.6 Write and verify

1. Run the SQL with `run_files_tx.py` (one transaction per file, statement timeout 15 min) using the admin role. It and every `verify_<x>.py` are in `data/catalogue-completion/20261004-01/session-tools-20261016/`. Add `sslmode=verify-full&sslrootcert=/certs/cert.pem` to the URL with urllib, not by string append, because the role URL already has a query string, and mount `/etc/ssl/cert.pem`.
2. Run the loader-equivalent check (`verify_<x>.py`): digests, vector manifests and aggregates, artwork files, the feature store, aliases.
3. If the guard fails, the transaction rolls back, leaving only the empty schema from `01`. Fix the cause, regenerate, and run only `02`.

### 4.7 Switch staging and test

1. Copy the previous release env and change only `PLANETSCALE_SCHEMA` and `PLANETSCALE_IMPORT_ID` (plus the feature and artwork dirs only if they changed). Edit per key, never with a global replace (see the pitfalls).
2. On `auctaro-staging`:
   - archive the current `/etc/scanapp-staging/catalogue-release.env` to a new rollback folder;
   - `install` the new file;
   - in `/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code`, run `docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml up -d --no-deps api`.
3. Wait for `https://scan.pokesingle.com/api/v1/health` to show `ready: true` and the new import ID.
4. Run the panels with `local-first-validation-20261014/staging-directed-panel-20261014/run_staging_panel.py` (venv `data/catalogue-completion/local-review-venv`):

   | Panel | File |
   |---|---|
   | 28-photo regression | `batch-preparation-20261014/english-109-local-batch-v1/staging-light-check-v1/scan-list.json` |
   | JAW2 32 photos | `japanese-wave2-20261015/panel-jaw2-32.json` |
   | PCG 20 photos | `…/pcg/panel-pcg-20.json` |
   | Vintage 18 photos | `…/vintage/panel-vintage-18.json` |

5. Compare best match, status and alternatives with the previous candidate's results. Keep the candidate if best match and status are unchanged and no expected card gets worse; otherwise roll back.
6. If a run is cut by "connection reset" or 502, check the API container (restarts, OOM) before rerunning only the missing cases.

### 4.8 Gate checklist (every gate must pass, in this order)

| # | Gate | Where | Passes when | If it fails |
|---|---|---|---|---|
| 1 | Source page read cleanly | Chrome step script | No "Just a moment / Verify / Access denied" title; the page card count matches the catalogue count for the set (or the difference is explained) | Stop browsing; the owner ticks the check; resume at 15 s per page |
| 2 | Download integrity | download log | Every image HTTP 200 (a wrong path gives 404) | Re-read that set's page; never guess a path |
| 3 | One-to-one mapping | `map_hits.py` / `map_vintage.py` | Each image maps to exactly one card that has no image; no card gets two images | Hold the card with a reason in `mapped-held.json` |
| 4 | Name agreement | `map_vintage.py`, `gate_images.py` | The English source name agrees with the card's Cardmarket slug, the Japanese Pokédex name or the glossary. Unnumbered sets: at most 2% real conflicts | Hold the card or the set. Read every "differs" item by hand; wrong old links and translation variants are not conflicts |
| 5 | Image quality | `gate_images.py` (thresholds from `catalogue/bootstrap/checks.py`) | Shortest side ≥ 180 px, blur (Laplacian variance) ≥ 40, no exact duplicate image | Exclude the image or find another source |
| 6 | Look-alike control | `pick_novec.py` | New card's pad cosine to any other Japanese printing < 0.95 | Printing alternative: image + features, no vectors |
| 7 | Candidate guard | last statement of `02-seed-and-apply.sql` | All row counts match; vector and artwork hashes recomputed in SQL match; every rename, link and image applied | Transaction rolls back; fix the cause and rerun only `02` |
| 8 | Loader-equivalent check | `verify_<x>.py` | `status=validated`, target schema matches, card and product digests match, vector manifests and aggregates match, artwork files match, feature store loads | Do not switch staging |
| 9 | Artifact upload | `sha256sum -c` on staging | Every file checksum OK; parent feature manifest hash unchanged | Re-upload; never edit the parent folder |
| 10 | Staging health | `/api/v1/health` | `ready: true` with the new import ID within about 10 minutes | Read the API logs (e.g. "malformed artwork index" was a wrong env path); roll back if not quickly fixable |
| 11 | Test photos are real | `contact_sheet.py` | Each eBay photo checked by eye against the reference | Set it aside in `ebay-photos-excluded/` with a reason |
| 12 | No regression | panel comparison script | 28-photo regression: best match and status identical to the previous candidate. Earlier waves' eBay panels: best match and status identical. No confidently wrong match on the new photos | Roll back to the archived release env |
| 13 | Stability | `docker inspect`, `journalctl -k` | No API restart or OOM kill during the panels | Investigate memory before keeping the candidate |
| 14 | Recorded | `events.jsonl`, `PROCESS-AND-PENDING.md` | Step, results, evidence hashes and rollback path written | Write them before starting the next step |

Lower-ranked alternatives changing in already-uncertain scans has been accepted so far, and the owner was told each time. A changed best match or status is a regression unless it improves an expected card, as Lance's Charizard did in JAFIX.

### 4.9 Same image, variants and reprints (decision guide)

#### Treatments

A card can get one of four treatments. Choose per card and record the reason in the candidate metadata.

| Treatment | What the card gets | Effect | Use when |
|---|---|---|---|
| **Scannable** | Own image + pad/square/artwork vectors + feature record | Can be the top scan result | The artwork is distinct from every other printing (cosine < 0.95 to other same-language cards) |
| **Printing alternative** | Own image + feature record, **no vectors** | Never the top result. When a photo matches its twin, it is offered as an alternative in the same printing family (the family is matched by name) | The card is the same artwork as another printing that already has vectors (reprints, deck versions, alternate-border versions) |
| **Display-only** | Own image only, feature record unavailable | Shows in search and on its card page with price; never offered by the scanner | The image is right but scanning could confuse it and it has no name family to join (e.g. different cards on one shared template) |
| **Visual alias** | No own image; the card shows its owner's image (`visual_image_aliases`, the alias's collector number must equal the owner's) | Search and card page show the twin's image | Only an identical twin's image exists and the card is the same print in another product (e.g. English Unown and Yellow A twins) |

#### Cases met so far

| Situation | Example | What we did |
|---|---|---|
| Japanese and English versions of the same art | ja:S5I-085 vs en:swsh5-168 (0.965) | Keep both scannable. Cross-language twins are normal; the scanner separates them with OCR/language |
| Same Japanese art reprinted in another set | ja:SM2p-011 / ja:SM4p-020 (0.9995) vs ja:SM2K-010 | The earliest printing keeps vectors; later reprints become printing alternatives |
| A new card's twin already has vectors | SV-P energies 037–044 vs SV-P 100–107; ja:PCG1-075 vs ja:pooka-wcp-85 | Every new card in the group becomes a printing alternative |
| Different cards on one template (close, not identical) | Holon Energy GL/FF (0.956); VS1 Technical Machines 02 (0.95+) | Same rule (≥ 0.95 means printing alternative); names differ, so they act as display-only. Prefer this over the scanner returning the wrong one |
| Same card, two Cardmarket versions with different looks | MFB basic energies, grey vs blue border | Split into separate cards: existing rows = grey (V2), new rows `en:mfb-*-blue` (collector `N-blue`) = blue (V1), each with its own image and product |
| Same card, versions not visually distinct (V1/V2 by print run) | 167 Japanese cards in `id-held.json` | Keep one card. Product ID only after a page check; V numbering does not follow product-ID order |
| Deck or kit version, near-identical except a deck symbol | EX trainer-kit Latias 8/9 | Printing alternative. Vectors made a Latios photo flip to Latias; that was rolled back |
| Letter variants (Unown) | neo2 Unown F/D | Match on the letter exactly; a different letter is a hard conflict, so the card or set is held |
| Holo, reverse holo and other finishes | TCG Collector `setCardCountMode=anyCardVariant` | One catalogue card per number. Use the standard-finish image; finishes are not separate rows unless the catalogue already has them |
| Duplicate-looking images (gate hash collision) | ja:VS1-104 / ja:VS1-112 | Compare the files' SHA-256. Different files are a coarse-hash collision, not a duplicate |
| An identical image file for two cards | none yet | Hold both until the source shows two different scans; never give two cards the same file as their own image |

#### Rules

- Always measure. Before deciding, compute the cosine of each new pad vector against the served index and the other new cards (`build_vectors_*.py` reports it, `pick_novec.py` groups at 0.95). Never decide from the name alone.
- When unsure between scannable and printing alternative, choose printing alternative. It can be promoted later after a staging test with real photos of both printings.
- Test any group of look-alikes on staging with real photos of each printing. Keep the candidate only if no photo flips to the wrong printing. (This is how the Latias/Latios and MFB Potion cases were caught.)

### Known problem

Base-set Charizard (`ja:PMCG1-021`) photos select the 25th/30th reprints; image fixes tested and ruled out.

Both photos stay in `vintage/panel-vintage-18.json` (`ebay-ja_PMCG1-021-1`, `ebay-ja_PMCG1-021-2`), so a future fix shows up as an improvement. On the catalogue staging serves, the first photo is `printing_ambiguous` on `ja:M6a-137` and the second is `uncertain` on `ja:S10P-030`. The JASETS switch moved them to `ja:S5R-006` and `ja:S3a-030` and was rolled back. Those two cards were then left out of the scan index on JASETH. The second photo returned to `ja:S10P-030`. The first moved to `ja:CP6-011`, so JASETH was rolled back. `ja:CP6-011` was then left out of the scan index on JASETH3. The Cardmarket link candidate kept those best cards and statuses. The view-title candidate kept them again. Staging now serves the view-title candidate. Both photos are back to the previous best card and status. Investigate `ja:S5R-006`, `ja:S3a-030` and `ja:CP6-011` later. A cleaner TCG Collector scan is already the reference. An approved eBay photo of the same card was measured locally and did not make `ja:PMCG1-021` the selected card, and the official site does not publish the 1996 Expansion Pack scan. `ja:neo2-057` still has no image.

Telling a base-set card from a reprint of the same art is a scanner change. It was not done. It needs its own approval and a full panel run.

## 5. What is left (in priority order)

1. **16 absent sets are on staging** as `PS-CATALOGUE-EN-JA-VIEW-20261018` (JACM plus English view titles). All 1,613 have images and features. 1,331 have scan vectors. `ja:S5R-006`, `ja:S3a-030` and `ja:CP6-011` have no scan vectors; investigate them later. 1,586 have a Cardmarket page. 27 do not: 25 title mismatches in `cardmarket/links-held.json`, plus `ja:S2-022` and `ja:S3-025`, whose pages are already on `ja:SV-P-222` and `ja:SV4a-325`. Do not re-apply `data/catalogue-gaps/tcgdex-empty-sets-20261017/prepared-jasets-v1/02-seed-and-apply.sql`.
2. **Cardmarket links (1 Japanese row still without one).** JALINKS14 linked `ja:SV-P-272`. `ja:neo2-057` still has no image. What remains:
   - `extra-gengar-mimikyu-gx-103-095` still has no page. Its stored picture is the 102 card, and both the 102 and 103 pages already sit on `ja:SM9-102` and `ja:SM9-103`. The picture stays, because the feature store is bound to that file and the 103 scan already belongs to `ja:SM9-103`. `ja:SV-P-272` (エネルギー転送) now has the Energy Search (272) page. The picture is 272/SV-P, between Victini 271 and Potion 273, so price id 838366 stays. `ja:neo2-057` still has no image. `ja:M-P-155` has the V2 page only; a second Riolu product in the file was not on the page and was not linked.
   - **632 (MC 477, SV4a 45, SM6 110):** product lists were read in the owner's browser. 629 unique links are on JACRRAWL. The three held URL collisions (`ja:MC-067`, `ja:MC-100`, `ja:MC-124`) were moved onto those cards on JALINKS6.
   - **The other 192** were rematched on 2026-10-16 and held: 157 name-only collisions, 15 numbers with no product, 13 sets with no mapped expansion, 6 products that matched two cards, and `ja:web1-002` (Nidoran) whose only product is Nidoran [M].
3. **Product IDs (4,053 without one):** the previous 2,440, plus the 1,613 new cards, which have no product id. Most of the older ones have no link (item 2). 169 are versioned products (V1/V2) that need a page check (`japanese-wave1-20261015/cardmarket-product-file/id-held.json`). V numbering does not always follow product-ID order.
4. **Names.**
   - 10 trainer names are left unchanged because there is no confident official form (listed in JAFIX `ja_fixes.names_left_unchanged`).
   - The neo3 and neo4 Unown cards still have single-letter names (e.g. "k"). Rename them as アンノーン plus the letter (e.g. アンノーンK) after confirming the convention.
   - Other vintage sets not covered by this wave may still have machine-translated names. Search `cards.name` for Latin letters or obvious translations.
5. **Wave 3 leftovers:** the 5 non-English Ancient Mew versions (Cardmarket V1–V5).
6. **Production:** decide when and how to promote. The production API needs the same 3 GiB memory limit first, because scans peak at about 2.1 GiB with the current catalogue. Before production, confirm the app presents `printing_ambiguous` as a choice for the user, not a confirmed match.

## 6. Pitfalls learned (save time)

- **Shell:** `cd` is broken in the owner's shell (a gvm hook), so use absolute paths and `/bin/ls`. Never name a script `inspect.py`, because it shadows the stdlib module. Under `set -e`, `diff` returns 1 when files differ and stops the script.
- **Secrets:** don't print role or env files. The auto-mode classifier blocks it, and they contain credentials. Load the role URL straight into an env var.
- **Env edits:** never use a global substitution on the release env. A schema rename once also changed `ARTWORK_BUNDLE_DIR` to a missing folder, and staging reported "Unreadable or malformed artwork index" until it was fixed.
- **Insert guards:** when a candidate claims Cardmarket products, count products that already point to the card. Two did, and the guard expected the wrong total.
- **Old links:** some older "helper-expansion" Cardmarket links point to unrelated products. The vintage gate found 32; check the slug against the card before trusting it.
- **Bad source names:** many vintage catalogue names were machine translations (爆風 for Blastoise, 政治 for Politoed). Name checks must allow for bad catalogue names. A real conflict is a correct Japanese name of a different species, or a different Unown letter.
- **Merging:** the session's safety check blocks merging PRs without review, so the owner merges.
- **Verify scripts:** the same global-substitution mistake happened to a `verify_<x>.py` copy, when the artwork path was renamed along with the schema. Change only the `S=` / `IMPORT=` line, and point the artwork and feature paths at the bundles the candidate actually uses.
- **Role expiry:** roles expire silently, and the error is "SASL authentication failed". Check `expires_at` in the role JSON and create a new role rather than retrying.
- **Waiting on background jobs:** wait on the job's own output file or a marker such as `"cards"` in its log, not on a shared output file. A waiter once fired early on an unrelated line.
- **eBay search:** listing titles lie. Filter out graded, lot, proxy, custom, metal and gold listings, and still check every photo by eye: the vintage run found a Bouffalant, a novelty card and a different Celebi printing under correct-looking titles. Unnumbered vintage cards cannot be filtered by number in titles.
- **TCG Collector numbers:** unnumbered vintage sets show "No. 001", which is TCG Collector's own order. It matched the catalogue order for every set except neo2 (Unown), but always verify by name.
- **Cleared links:** the 10 cleared Cardmarket links now show no price on purpose; the old prices belonged to unrelated products.
- **Python on the Mac:** the system python3 has no `yaml` or `numpy`. Run such checks inside the API image.
- **Percent signs in SQL:** `cursor.execute(sql)` with no parameters stores `%%` as two percent signs. The JASETS seed file doubled them, and `en:exu-%3F` became `en:exu-%%3F`. The import manifest was repaired in the schema. Do not run that file again, and do not run the `%%` replace a second time.
- **Transactions:** a statement before `with conn.transaction()` opens an outer transaction, and the block becomes a savepoint. Closing the connection then rolls the schema back even though the script printed success. Put `SET` inside the block, and read the new schema back on a second connection before trusting the commit.

## 7. Where this can run

This work needs the owner's Mac, or a machine with the same access:

- the run folder `data/catalogue-completion` (149 GB, gitignored, not on GitHub);
- `ssh auctaro-staging`;
- a logged-in `pscale`;
- the owner's Chrome (TCG Collector blocks automated access with Cloudflare);
- Docker with `scanapp-api:local-amd64`.

A cloud session started from the repo has none of these. Only database-side tasks could run there (re-matching Cardmarket links, product IDs), and only with a PlanetScale service token and the needed files supplied.

## 8. Access

| What | How |
|---|---|
| PlanetScale | org `pokesingle`, database `pokesingle-db`, branch `main`. `pscale role create pokesingle-db main <name> --inherited-roles pg_read_all_data,pg_write_all_data --ttl 3h --org pokesingle -f json > role.json` (admin: `--inherited-roles postgres --ttl 1h`). Connect on port 6432, `sslmode=verify-full`, `prepare_threshold=None`. |
| Staging host | `ssh auctaro-staging` (sudo). Compose: `/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code/compose.dokploy.yaml`. Data volume: `/var/lib/docker/volumes/scanapp-scanapp-z1mwj4_scanapp-data/_data`. |
| Staging API | `https://scan.pokesingle.com/api/v1/health`, `/api/v1/cards/{id}`, `/api/v1/cards/{id}/image` |
| Browser | Owner's Chrome via the Claude in Chrome tools (TCG Collector, eBay, pokemon-card.com) |
