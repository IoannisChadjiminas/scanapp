# Catalogue completion — handoff (2026-10-16)

This replaces the 2026-10-15 handoff (no longer in the repo root; its plan and the English work are summarised in `PROCESS-AND-PENDING.md`). It covers where the work stands, how each step is done, what is left, and the rules to keep.

**The run folder** holds the full history:

- Folder: `data/catalogue-completion/20261004-01/`.
- `PROCESS-AND-PENDING.md` is the narrative history.
- `events.jsonl` is one line per step, with evidence hashes.
- Read the last few sections of both before starting.

**Start here:**

1. Confirm what staging serves: `curl -s https://scan.pokesingle.com/api/v1/health` should show `PS-CATALOGUE-EN-JA-FIX-20261016` and `ready: true`. If it shows something else, read the end of `events.jsonl` first.
2. Read sections 3 (rules), 4.8 (gates) and 4.9 (variants).
3. Create a 3-hour read/write PlanetScale role (section 8) and run the "Useful queries" gap count to confirm the numbers in section 2.
4. Pick the next item from section 5 (neo2 is the smallest self-contained one) and follow section 4 step by step, logging as you go.

## 1. Goal

Complete the scan catalogue on **staging** (never production) so that:

- every card has a reference image;
- every card that can be told apart visually has vectors (it is scannable);
- every card has a working Cardmarket link and price.

Each change ships as a new inactive PlanetScale candidate schema. It is checked, switched on staging, tested with real-photo panels, and kept only if nothing regresses.

## 2. Where things stand

| | Value |
|---|---|
| Staging serves | `PS-CATALOGUE-EN-JA-FIX-20261016` (schema `pokesingle_completion_20261016_jafix`) |
| Feature dir / artwork dir | `reference-features/20261016-ja-vintage` / `artwork/PS-CATALOGUE-EN-JA-VINTAGE-20261016` (JAFIX reuses the vintage bundles) |
| Cards | 48,657 in total, of which 14,706 are Japanese |
| Vectors | 42,323 per mode (pad and square), plus 18,804 artwork regions |
| Japanese with an image | 14,662 of 14,706 (**44 left**) |
| Japanese with a Cardmarket link | 13,605 (**1,101 left**) |
| Japanese with a Cardmarket product ID (price) | 12,266 (**2,440 left**) |
| English | All 109 gaps closed (see the 2026-10-15 sections of `PROCESS-AND-PENDING.md`) |
| Staging API memory | 3 GiB RAM + 1 GiB swap (PR IoannisChadjiminas/scanapp#47, merged 2026-10-16 06:08Z) |
| PlanetScale storage | 64 `pokesingle*` schemas, about 22 GB in total. Each new candidate is a full copy and adds about 0.35–0.45 GB. Old schemas are kept on purpose (delete nothing); ask the owner before any clean-up |
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

## 5. What is left (in priority order)

1. **neo2 (16 cards without images).**
   - TCG Collector numbers Unown F and D as 025 and 026, where our rows hold d/f.
   - Check the neo2 page (or Bulbapedia) to fix the order of the Unown rows.
   - Then run `vintage/map_vintage.py` for neo2 only and build a small candidate.
   - The images are already downloaded in `vintage/tcgc-images/`.
2. **neo4 (1 card):** TCG Collector has no entry for it (`vintage/mapped-held.json`, status `no_card`). Try official pokemon-card.com.
3. **M-P promos 101–127 (27 starter promos, Bulbasaur to Quaxly):** not published yet on TCG Collector or pokemon-card.com (newest official Bulbasaur is M1L). Recheck weekly.
4. **Cardmarket links (1,101 Japanese cards without one).**
   - **632 (MC 477, SV4a 45, SM6 110):** these need a full product list.
     - Cardmarket caps listings at 300.
     - The expansion IDs are MC 6381, SV4a 5519 and SM6-JP 3896.
     - Either use the project's staging scraper, or crawl slowly (one page every 30–60 s) once the block is lifted, never from the owner's connection again without asking.
   - **The rest (mostly vintage):** the product was ambiguous or not found. Rerun `japanese-wave1-20261015/match_ja_links.py` now that the names are correct; the official names should make many name matches unique.
5. **Product IDs (2,440 without one):** most have no link (item 4). 169 are versioned products (V1/V2) that need a page check (`japanese-wave1-20261015/cardmarket-product-file/id-held.json`). V numbering does not always follow product-ID order.
6. **Names.**
   - 10 trainer names are left unchanged because there is no confident official form (listed in JAFIX `ja_fixes.names_left_unchanged`).
   - The neo3 and neo4 Unown cards still have single-letter names (e.g. "k"). Rename them as アンノーン plus the letter (e.g. アンノーンK) after confirming the convention.
   - Other vintage sets not covered by this wave may still have machine-translated names. Search `cards.name` for Latin letters or obvious translations.
7. **Wave 3 leftovers:** the 5 non-English Ancient Mew versions (Cardmarket V1–V5).
8. **Production:** decide when and how to promote. The production API needs the same 3 GiB memory limit first, because scans peak at about 2.1 GiB with the current catalogue.

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
