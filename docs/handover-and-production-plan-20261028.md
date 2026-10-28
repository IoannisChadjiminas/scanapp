# Handover: faster scans on both phones, and the road to production (2026-10-28)

For the next agent. Repos: **scanapp** (server, `/Users/ioannischadjiminas/WebstormProjects/scanapp`, GitHub IoannisChadjiminas/scanapp) and **PokeSingle** (Flutter app, `/Users/ioannischadjiminas/StudioProjects/PokeSingle`, GitHub IoannisChadjiminas/pokesingle). Test phones: Galaxy A55 (adb `RZCX702S3EW`) and iPhone 15 (UDID `00008120-00140DE22139A01E`). Staging: `ssh auctaro-staging`, container `scanapp-scanapp-z1mwj4-api-1`, public `https://staging-scan.pokesingle.com`.

## Owner's rules (keep)

- Plain short English with the owner. Every behaviour change behind its own switch; test before switching on. Production stays off unless the owner says so.
- **Staging is read-only** for agents unless the owner explicitly allows a write for a named task (they did once, for publishing the phone index).
- 0 wrong cards shown and 0 background-check disagreements are the gate for anything that answers early.
- Photos and OCR text never in git; never print secrets (`config/auth.local.json`, PlanetScale URL).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Every server ranking change (number rules, guards, choose list) is replayed on all stored staging scans before merging, switch off vs on; 0 scans may move to a wrong card (see "Testing a ranking change on stored scans").
- Staging auto-deploys scanapp `main` (Dokploy). The owner sets Dokploy environment values.
- Helpers: the owner asks for Haiku 5.5 helpers (high or normal effort) for implementation.

## What is done (all merged)

### Server (scanapp)

| PR | What | Switch | Code default | Staging | Production compose |
|---|---|---|---|---|---|
| #84 | Background check re-runs with the phone's text/outline/crop | `STAGE1_CHECK_PHONE_INPUTS` | off | on | off |
| #83 | Keep the exact uploaded photo next to the review record | `STORE_ORIGINAL_UPLOADS` | off | on | off |
| #85 | A bare number (attack damage) can't lift a much weaker picture over the leader (the Toxel→Bibarel bug) | `RANK_BARE_NUMBER_GUARD` | off | on | off |
| #81 | Phone's name+number stand in for the footer OCR when they name exactly one card in the picture top 20 | `CLIENT_TEXT_AGREE` | off | on | off |
| #86 | Diagnostics keep provisional/index/footer fields | — | — | — | — |
| #87 | Phone card index: export script, `/api/v1/card-index/manifest` + immutable file routes, cached validation | `CARD_INDEX_PUBLISH` | **on** | on (index published) | off |
| #88 | When the printing is unsure, the choose list also offers same-name prints up to 0.08 lower (Evolutions 9/108 under Base Set 46/102) | `PRINTING_CHOICES_WIDER` | off | owner setting it on | off |
| #90 | A set total cut off by its last digit at the photo edge ("9/10" for 9/108) counts as the card's number, not a conflict. Replay: 8,093 scans, 1 change (Charmander 0a4f643b, lc-70 → xy12-9, right) | `OCR_CUTOFF_TOTAL` | off | owner setting it on | off |

Docs: `docs/full-pipeline-speed-plan-20261026.md`, `docs/on-phone-match-best-frame-plan-20261027.md`, `docs/ios-parity-plan-20261027.md`, `docs/phone-index-shipping-plan-20261028.md`, `docs/phone-index-shipping-fixes-20261028.md`, `api/scripts/on_phone_index/README.md` (operator sequence), `docs/experiments/*` (results).

### App (PokeSingle) — all on by default in `main`

| PRs | What |
|---|---|
| #175–#179 | Android fingerprint (LiteRT, Play asset pack `card_embedding`), outline fix, full-res footer read |
| #186, #187 | On-phone index search (native C on Android) + match log (`ON_PHONE_INDEX`) |
| #188, #185, #189, #190 | Footer extra 250 ms, name rules, live reader + live-name rule, bigger scan box, chips under the box (number, price, Cardmarket logo, Live/Trend/date) |
| #191 | Phone match runs right after the shutter; provisional card ("checking") replaced by the server's answer (`PHONE_PROVISIONAL`) |
| #192–#197 | iPhone: Core ML fingerprint fix, big box + chips, live text, Vision footer read, Swift index search, provisional card (`IOS_*` switches, all on) |
| #198 | App downloads the index from the server on Wi-Fi, checks sha256, swaps atomically, cleans old versions (`CARD_INDEX_DOWNLOAD`) |

### Measured (staging, owner's cards)

- A55: 7–9 of 16 photos answered early (30–590 ms server), all confirmed by the background check; provisional cards on 7–8 of 16, 1.4–1.9 s after the shutter, 0 overturned.
- iPhone 15: fingerprint on all 15 photos (65–113 ms), 9 of 15 early answers, all confirmed; a provisional card 0.38 s after the shutter, confirmed.
- Index download: iPhone 35.7 MB in 16.5 s, A55 in 3.2 s (Wi-Fi), checksums verified, swap OK.
- Staging published index: version `2bcfd9b9e3b4166238df5efcaf211fda767e9e56890bf3a0cf93b8f065ccde51` (43,695 rows, model `2ddf6ec79e37`, catalogue import `PS-CATALOGUE-EN-JA-ENID2-20261019`).

## Open issues (next work, in priority order)

1. **326 cards have a reference image but no picture vector** (313 Japanese, 13 English; see "Missing cards"). Cheapest catalogue win: embed them and publish an additive snapshot, then a new phone index.
2. **Cut-off collector numbers**: Evolutions Charmander 9/108 read as "9/10" / "801/6" (server) or nothing (phone); the footer crop misses the bottom-right corner. The "9/10" case is handled by #90 (`OCR_CUTOFF_TOTAL`). Still open: widening the footer crop on old-style layouts, and the phone reading no number at all.
3. **Prize Pack totals**: `PPS5-PAR-*` sets have no row in `set_totals`, so a bare number fits them and the Prize Pack copy is often shown first. Add the base set's printed total for Prize Pack mirror sets.
4. **Toxel MEP 078**: the number in the black promo box is never read on either phone.
5. **Name rules gaps** still seen: stage words alone ("STAGE"), Pokédex lines, short noise ("Ee f Chm"). A noisy but "valid-looking" photo name beats a correct live name (`LIVE_NAME_WINS` only replaces names that fail the rules).
6. **Tests**: 2 known failing tests on main (`inapp_cardmarket_reader_test` "the loading bar stops once a read has an answer", `match_sheet_test` "Retake keeps the photo in place…"); `batch_mini_strip_test` "a listing sample from today says 'Today'" fails just after midnight.
7. **Live checks still to do**: `PRINTING_CHOICES_WIDER` and `OCR_CUTOFF_TOTAL` on a real Charmander 9/108 scan with the number cut off at the edge; `CLIENT_TEXT_AGREE` applies to few scans (phone rarely sends name+number) — revisit after the number fixes.

## Testing a ranking change on stored scans

Scripts and details: `api/scripts/stored_scan_replay/README.md`. Use it for any change to `rank.py`, `printing.py` or the number rules, before the PR is merged.

1. **Export** the stored scans, read-only (the script is streamed into the container; nothing is written on staging):
   `ssh auctaro-staging "docker exec -i scanapp-scanapp-z1mwj4-api-1 python3 -" < api/scripts/stored_scan_replay/export_cases.py > <work>/cases.jsonl`
   About 8,100 scans and 40 MB on 2026-10-28. The first line carries staging's own ranking switches, so the replay ranks as staging does. The file holds OCR text: keep it outside git (scratchpad) and delete it afterwards.
2. **Set totals** (needed by number rules such as `OCR_CUTOFF_TOTAL`): the stored top 20 doesn't carry them; pass `--catalog` and `--totals` from the last phone-index export (step 6 of "Adding new cards").
3. **Replay** from the branch with the change, the new switch off and then on:
   `cd api && .venv/bin/python scripts/stored_scan_replay/replay_ranking.py <work>/cases.jsonl --flag <setting_name> [--catalog … --totals …] [--set name=value]`
   It prints each scan whose first card or choose list changes (card ids and names only) and the totals.
4. **Gate**: look at every changed scan (its stored photo if `STORE_ORIGINAL_UPLOADS` kept it, or the owner's confirmation). Each must move to the right card or a fair choose list; 0 to a wrong card. Put the counts in the PR body.
5. Limits: it reranks the stored picture top 20 and OCR read; it does not re-run OCR or the picture search. OCR or crop changes need the photo replays instead (`STORE_ORIGINAL_UPLOADS` originals).

## Missing cards (catalogue coverage)

Counted on 2026-10-28 from the live cloud snapshot (export `PS-CATALOGUE-EN-JA-ENID2-20261019`): catalogue cards against rows in the picture-vector snapshot (= the phone index).

| Language | Cards | With a vector | No vector | of which: image but no vector |
|---|---:|---:|---:|---:|
| English | 25,638 | 25,430 | 208 | 13 |
| Japanese | 16,319 | 16,005 | 314 | 313 |
| Chinese (simplified) | 877 | 0 | 877 | 0 |
| Chinese (traditional) | 7,436 | 2,260 | 5,176 | 0 |
| **Total** | 50,270 | **43,695** | **6,575** | **326** |

**Why `/health` says 44,021 and the phone index has 43,695.** `/health` `coverage.indexed` (`app/db.py` `coverage()`) counts catalogue cards with `has_image = 1`, not vectors. 326 cards have `has_image = 1` and a reference image (`image_path` under `/data/reference-images/…`, 324 also a remote URL) but no row in the vector snapshot, so neither the server's picture match nor the phone index can find them (text can still reach them). By set: Shiny Star V (ja S4a) 150, Rapid Strike Master (S5R) 23, Amazing Volt Tackle (S4) 21, Matchless Fighters (S5a) 17, Infinity Zone (S3) 11, My First Battle (en mfb) 10, Expansion Pack 20th Anniversary (CP6) 10, SV promos 9, others. They look like images added in later batches (e.g. `en-20261015-mfb-*`) whose vectors were never appended. The phone index is correct: it has every vector the server has (same ids sha256 `ab5b4059…`). None of the 326 are visual-image aliases (the snapshot's 34 aliases are separate).

So: `/health` overstates picture coverage by 326; the real numbers are 43,695 with a vector and 6,575 without. Two follow-ups: (a) embed the 326 (images exist) in the next additive snapshot; (b) have `/health` report the vector count too (e.g. `coverage.vectors` from `snapshot.indexed_count`) so the two numbers can't be confused again.

## Adding new cards: what has to be regenerated

The live catalogue is the PlanetScale **cloud snapshot** selected by `/etc/scanapp-staging/catalogue-release.env` (`PLANETSCALE_SCHEMA`, `PLANETSCALE_IMPORT_ID`; production: `/etc/scanapp-production/…`). See `docs/planetscale-staging.md` and `docs/production-single-server.md`. Local `/data/vectors/pad` on staging is an old bundle and is not what recognition uses.

For each batch of new cards (English, Japanese, Chinese):

1. **Card rows**: add the cards (id, name, set, collector number, printed number, language, Cardmarket links) in a new reviewed catalogue release (new PlanetScale schema/import id). Add the set's printed total to `set_totals` (also Prize Pack mirrors).
2. **Reference images**: one clean front image per card (source as in earlier recovery work: `data/catalogue-gaps/`, `data/catalogue-completion/`).
3. **Picture vectors**: embed each image with the server's model (DINOv2-small, `pad` preprocessing, model sha `2ddf6ec79e37…`, `app/recognition/embed.py` `DinoEmbedder`). `api/scripts/build_cloud_reference_recovery.py` builds an *additive* candidate from the active cloud snapshot: it keeps the old vectors/features unchanged, appends the new reviewed references, and emits a compare-and-swap SQL transaction for a separately authorised publisher (it never publishes by itself).
4. **Reference features** (local artwork check, SIFT): `api/scripts/build_reference_features.py`. The bundle is tied to the CPU architecture and OpenCV build — build it natively for the server's architecture (x86_64 today; never relabel a Mac/Arm bundle). Also the artwork bundle selected by `ARTWORK_BUNDLE_DIR`/`REFERENCE_FEATURES_DIR` if used.
5. **Publish the release** (owner-authorised): apply the SQL, update the release file atomically, recreate only the API, check `/api/v1/health` (new import id, counts) and a few card routes; keep the rollback file/image.
6. **Phone index** (after the server runs the new snapshot): follow `api/scripts/on_phone_index/README.md` and the runbook (scratchpad copy: `staging-publish-runbook.md`):
   - `export_cloud_snapshot.py` inside the API container → vectors + paired `catalog.sqlite`;
   - copy `set_totals` with the SQLite backup API; copy the model;
   - `export_index.py` on the Mac → candidate `<version>/` (4 files);
   - optional parity check `check_compressed_index.py` against the same export;
   - place in `/data/phone-index/<version>/` via a temp folder (verify sha256), then `ACTIVE.next` → `ACTIVE`; keep old version folders for phones mid-download; remove macOS `._*` files if copied with tar from a Mac.
   - Verify: manifest 200, file range 206, ETag = sha256. A 503 means the candidate doesn't match the running snapshot.
   - Phones pick it up within a day (daily check, Wi-Fi only) and replace their index atomically.
7. **Re-check**: a short scan round on both phones; no wrong cards; background check agreeing.

## Production rollout (proposal, needs the owner's go per step)

1. Freeze the server flags that passed on staging and set them in the production environment one by one, watching the logs: `RANK_BARE_NUMBER_GUARD`, `STAGE1_CHECK_PHONE_INPUTS`, `CLIENT_TEXT_AGREE`, `PRINTING_CHOICES_WIDER` and `OCR_CUTOFF_TOTAL` (after their live check), `STORE_ORIGINAL_UPLOADS` (disk ~0.4–0.8 GB per 1,000 scans), `CARD_INDEX_PUBLISH` (after placing a production index built from the production snapshot).
2. App release: new build numbers; Android AAB with the `card_embedding` asset pack (Play); iOS with the on-demand Core ML model (TestFlight; see open PokeSingle #174 `deploy_ios.sh`). All new app switches are on by default; production builds must point at the production API and production Firebase.
3. Before the release: run one full round on both phones against production-like settings.
4. After the release: watch `card_index.download`, `phone_provisional.final` (agree must stay true), stage 1 background-check disagreements (must stay 0), and download volume on the server/Cloudflare.

## Practical notes

- Test builds: `flutter build appbundle --profile …` then `bundletool build-apks --local-testing --connected-device` + `install-apks` (bundletool from Homebrew, 1.18.3). Git-ignored model files must be copied into worktrees: `android/card_embedding/src/main/assets/CardEmbedding.tflite`, `ios/OnDemand/EmbeddingAssets/CardEmbedding.mlpackage`, and `config/auth.local.json`. Before installing over the A55 app, check no scan is in flight (`queue.enqueued` = `scan.result` for the running process). Never uninstall (keeps the index and data).
- iPhone install: `flutter build ios --profile …` then `xcrun devicectl device install app`; the phone must be unlocked to launch; the device console stays empty — read the iPhone's events from the staging log (`scan.diagnostics phone event=…`).
- The A55's adb connection drops now and then; restart `adb logcat` recording before each round.
