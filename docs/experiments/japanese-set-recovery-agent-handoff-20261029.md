# Agent handoff: recover Japanese sets, images and Cardmarket links

Updated: **2026-10-29, Asia/Nicosia**. This is the execution handoff requested by the owner. **Do not start work merely because this document exists.** The latest instruction is to finalize this plan first. When the owner asks to execute it, continue within the authorized collection scope without seeking permission for each set or batch.

## Current routing checkpoint — 29 October 2026

Follow [the routing update](japanese-set-routing-update-20261029.md) for the latest evidence, counts and execution order. All 336 groups were checked against 800 observed Cardmarket expansion links. The seed list now has **276 collection routes** (198 added to the previous 78). Another **59 groups have held shared/combined/pool candidates**, and **one group, 25th Anniversary Creatures Deck, has no confirmed Cardmarket route**. None is declared unfindable. Collection routes are not verified exact-print mappings.

Collect the 276 mapped routes now while reconciling checklists/images. Deduplicate the 29 review-pool URLs against those routes: only 13 are additional initial URLs. Implement the review-pool adapter before collecting that many-group manifest; do not feed it to the one-group runner. Resolve actual printed-code, language, stamp and variant conflicts before mapping any products. All acquisition feeds one bulk vector job and one combined release.

## 1. Outcome and fastest practical approach

Build a reconciled Japanese printing inventory, download all retrievable missing reference images, and associate the correct Cardmarket singles URLs/product IDs. **Complete the global acquisition/reconciliation phase before starting vectors.** Then run one bulk vector/feature job, assemble one combined catalogue and phone index, and run the full regression gates before proposing activation.

**Owner decision, 2026-10-29: one combined release for all verified additions.** Use one global collection queue and one bulk vector/feature run with resumable compute checkpoints. Review chunks and compute chunks are internal work units; they are not separate releases. MBG/MBD is a scraper/mapping validation pilot only and must not be published ahead of the combined release. Do not scrape every product page if its set listing already supplies the required evidence. Cache once, deduplicate jobs, resume from checkpoints and retry exceptions separately.

The collection pipeline should be:

```text
Audit groups → resolve actual printing identities and set aliases
             ├─ official/specialist set checklists → card metadata + image URLs
             └─ existing Cardmarket scraper → expansion listings + product URLs
                       ↓
           download unique images + reconcile exact-print mappings
                       ↓
         global acquisition report: resolved / held / unavailable
                       ↓
              one bulk vector/feature run → combined regression gates
                       ↓
         one combined inactive release → authorized staging activation
```

Avoid per-set API restarts, repeated whole-catalogue embedding, individual live-price scraping, and immediate deployment of each compute batch. These are unnecessary for acquisition.

## Execution location: owner’s Mac (confirmed 2026-10-29)

**Run the collection scraper locally on the owner’s Mac, not on the staging
server and not through the staging scraper API.** This decision supersedes the
server-lane instructions in the older detailed plan. The Mac is Apple Silicon
(arm64), and Google Chrome is installed in `/Applications/Google Chrome.app`.

Use a native macOS Python environment and visible local Chrome. Reuse the existing
scraper’s parsing, browser/session and queue logic, with a tested macOS collection
mode. The current launch helper forces Xvfb and Linux Chrome arguments; it needs
platform-aware local options. Do not assume the Linux/x86 scraper Docker image
will provide a normal interactive Mac browser. Disable Xvfb and omit Linux-only
launch flags in native Mac mode. Keep the server launch path unchanged.

Use one dedicated persistent local browser profile, separate from the owner’s
personal/default Chrome profile. Preserve it across collection pauses/resumes;
keep its cookies and credentials private and out of Git, public source evidence
and reports. Default to a direct local connection; do not copy staging proxy/API
secrets onto the Mac or enable a paid proxy merely to reproduce server settings.
If browser debugging is required, bind it to loopback only.

The owner manually completes Cloudflare in **this visible local scraper window**.
Pause all Cardmarket navigation while waiting, keep that tab/session open, then
verify clearance in the same window before resuming. Do not silently switch the
collection back to staging, another profile, headless Chrome or a different IP.

The job ledger, downloaded images, source evidence and progress reports live
locally in the run directory. Keep the Mac awake for the intentional run and
checkpoint for restart; do not silently install scheduled/recurring jobs.
Staging is used later only for explicitly scoped read-only baseline verification
and the existing authorized release workflow. Collection requires no staging
scraper deployment, API restart or catalogue write.

Local acquisition does not change the artifact compatibility requirement: native
reference features must still match the staging Linux/x86 OpenCV contract. Build
those later in a suitable offline target-compatible environment; do not relabel
Mac-native features as server-compatible. Preserve the one combined release plan.

## 2. Scope and counting rules

The 2026-10-28 audit compared 462 TCG Collector Japanese checklist groups against the live catalogue:

| Bucket | Groups | Treatment |
|---|---:|---|
| No identified catalogue rows | 281 | Reconcile full checklists against existing cards before adding rows |
| Present, below checklist row count | 55 | Compute exact missing printings; do not download/recreate the entire group blindly |
| Equal/higher row count | 126 | Not proven complete; retain as a comparison reference, outside the initial missing-group queue |

Initial acquisition queue: **336 groups**, keyed by reference group identity, **not just set code**. Some are overlapping deck bundles or promo/energy pools. Some share a Cardmarket expansion and must reuse the same scraped pages. Do not claim 281 distinct physical set codes or sum checklist entries as unique missing cards.

The first 28 modern absent groups contain 1,088 reference entries before deduplication. All 206 catalogue ID-prefix groups, including `pc-`, `pooka-` and `ra-` recovery IDs, were included in the audit. Reuse the recorded mappings instead of rediscovering them.

Resolve reused codes by era/product: Sword & Shield `SC` starter decks are not BW Shiny Collection; miscellaneous `MP` is not Mega promo `M-P`. Preserve printed number suffixes. Printed totals differ from checklist length: MBG `003/021` still has total **21** even though a numbered `022/021` exists. Unnumbered energies must not receive invented fractions.

## 3. Actual starting state and files

Repository: `/Users/ioannischadjiminas/WebstormProjects/scanapp`.

Read before execution:

- `AGENTS.md` in the repository.
- `docs/experiments/japanese-set-completeness-audit-20261028.md` — complete absent/partial lists and alias method.
- `docs/experiments/japanese-set-retrieval-and-cardmarket-plan-20261028.md` — detailed identity, source, mapping and release rules.
- `docs/experiments/mbg-gengar-catalogue-gap-20261028.md`.
- `docs/experiments/neo2-057-reference-20261028.md` and `docs/handover-and-production-plan-20261028.md` — release/rollback and regression context.
- `docs/scraper-host.md`, `scraper/main.py`, `scraper/worker.py`, `scraper/supervisor.py`, `scraper/browser.py`, `scraper/allow.py`.

Existing inputs (public card data, git-ignored):

```text
data/catalogue-gaps/ja-set-audit-20261028/
  comparison.json                  # All 462 groups, statuses, aliases and counts
  summary.json
  catalogue-sets.json               # Paired Japanese rows grouped by ID prefix
  live-set-counts.json              # Live primary counts matched the paired export
  tcgcollector-sets.json
  tcgcollector-source.txt           # Complete rendered source used for the audit
  official-mbg.json                 # Official MBG search response
  official-all.html
  tcgdex-sets.json
  audit.py, compare.py              # Original audit scripts; some paths point to scratch

data/catalogue-gaps/ja-set-recovery-plan-20261028/
  modern-batch-backlog.json         # 28 modern groups, ordered by priority
  pilot-link-seeds.json             # Observed Gengar/Diancie product URLs, IDs still unverified
  products_singles_6.json           # Cached official Cardmarket singles catalogue
  product-file-metadata.json
```

The product file was fetched on 2026-10-28: version 1, 75,066 products. It contains `idProduct`, `name`, `idCategory`, `categoryName`, `idExpansion`, `idMetacard`, `dateAdded`. **It does not contain canonical URLs, collector numbers or expansion names.** It cannot independently establish exact-print matches. Refresh only if stale for the work being done; archive the prior file/hash.

Staging baseline/reference only — not the collection execution location (re-read before release work):

```text
SSH:       auctaro-staging
API:       scanapp-scanapp-z1mwj4-api-1
Scraper:   scanapp-scanapp-z1mwj4-scraper-1
Lane:      http://scraper:8000   (private, reached from API container)
Schema:    pokesingle_completion_20261028_neo2057
Import:    PS-CATALOGUE-EN-JA-NEO2057-20261028
Vectors:   43,696
JA rows:   16,319
Phone:     033ea5e4e7d96c24dd689d39d5266553f870bd7d93252043696633b9fadabffd
```

Do not expose environment files, API keys, proxy credentials or database URLs. Preserve the current service settings, image and active selectors. The owner has authorized acquisition using the existing scraper; this is not authorization to activate new catalogue releases or production.

### Important scraper finding from the preliminary attempt

The installed **server** scraper was healthy. Its current `/scrape` endpoint accepts **individual singles product URLs** and parses offers. Set listing pages are rejected by its URL allowlist, and its readiness probe looks for offer rows. Simply sending set URLs to that endpoint will not work.

A historical **server-side** standalone preliminary MBG set-page attempt reused the installed browser/proxy code and timed out at 90 seconds with **zero products and no saved HTML**. It did not demonstrate that set scraping works. The temporary pilot process subsequently exited; no collection job is intentionally left running. Do not blindly repeat that attempt across 336 groups or start the vector phase based on it.

## 4. Acquisition priority and batching

Queue all 336 groups from the beginning, with this priority order. These are work priorities, not separate end-to-end deployments.

| Order | Work unit | Reference entries / purpose |
|---|---|---|
| A0 | Repair/test set-page collection and prepare registries | Prove one complete paginated set before scaling |
| A1 | MBG + MBD pilot | 44 numbered entries; reconcile basic Darkness/Psychic energy products separately |
| A2 | Remaining 6 Mega-era absent groups | 173 entries before reconciliation |
| A3 | 20 Scarlet & Violet-era absent groups | 871 entries before reconciliation |
| A4 | 55 potentially incomplete groups | Exact missing-card diffs only; prioritize large gaps and owner scan failures |
| A5 | Remaining 253 absent groups | Process by era/source availability; hold ambiguous legacy identities separately |

Within A2–A5, prefer sets whose source registry is already resolved and whose listing/image sources are accessible. One inaccessible group must not block independent collection jobs. Keep its failure in the exception queue.

Large combined deck groups such as SVD/SVM can be split into review chunks while sharing one inventory and preserving canonical printing IDs. Deck card quantities and overlapping product lists must not create duplicate cards.

## 5. Phase A0: make the scraper collect sets safely

1. Check the local Mac Python environment, native Chrome compatibility, dedicated profile ownership and free resources. **Use one visible local Cardmarket browser/navigation at a time.** Do not start or use the staging scraper for this collection. Preserve the owner’s personal Chrome windows and profiles.
2. Add a native local catalogue-listing runner reusing the existing scraper components, with macOS launch options, serialized browser ownership, persistent profile and checkpointed queue. Keep server price-offer behavior and tests unchanged. No network-facing scraper service is required; if a local control endpoint is used, keep it loopback-only and authenticated.
3. Add a separate strict URL validator for observed Cardmarket set/catalogue routes. Allow only HTTPS Cardmarket Pokémon catalogue/set-listing URLs and the supported pagination/filter parameters. Do not remove the existing product allowlist or create an arbitrary URL fetcher.
4. Implement set-page readiness and parsing. A valid page must identify the expected expansion and yield product cards/links or an explicit genuine empty state. A challenge, timeout, wrong expansion, consent/interstitial or rate-limit page is not an empty set.
5. Parse actual singles URLs, displayed names/codes/numbers, product IDs where genuinely present, image/variant evidence and pagination. Extract available expansion IDs/names into a shared Cardmarket registry. Discover links and pagination from the page; do not guess product slugs or invent expansion IDs.
6. Collect **all pages with “only available” disabled**. Follow the observed next-page links, track visited pages, deduplicate canonical products and detect loops. Compare the unique-product count with the page's declared total where available. Preserve original URL path case and meaningful variant information.
7. Persist each completed page immediately and mark a group complete only after pagination/reconciliation succeeds. Cache valid source HTML or structured evidence, retrieval time and checksum. Avoid retaining seller-account/offer data when only product catalogue evidence is needed.
8. Test real page fixtures and the critical failure paths: multi-page traversal, repeated pages, wrong-set redirect, zero stock, genuine empty set, challenge/manual-wait/resume (including watchdog/session preservation), rate limit, timeout/resume and duplicate products. Do not write tests that only mirror helper internals.
9. Run a live read-only MBG pilot. It must yield its numbered products plus the separately identified energy product and observed Gengar URL. Verify MBD next. If the pilot still fails, inspect the actual loaded page/stage and fix or record the cause before scaling.

Collection pacing: one navigation in the local scraper browser at a time, initially at least 15 seconds between Cardmarket page starts, and never faster than an existing stricter limit. Honor Retry-After and pause local Cardmarket navigation on rate limits. Preserve the dedicated local profile/session; do not evade blocks by rotating identities. Stop on a human challenge requiring intervention. Collect official assets independently while the lane waits.

### Owner rule: Cloudflare checkbox requires manual completion

If Cardmarket shows a Cloudflare checkbox or human-verification challenge:

1. Pause the Cardmarket parsing/navigation queue and record the current job as
   `waiting_for_owner`. Preserve the challenged browser page and its session.
2. Notify the owner that the page needs their tick and show the exact challenged
   tab in the visible local scraper Chrome window. A screenshot alone cannot
   complete it. Do not send the owner to another browser/profile and assume its
   clearance transfers; do not move the collection to a remote browser.
3. **Wait for the owner to manually tick/complete the challenge.** Do not click it
   automatically, use a CAPTCHA-solving service, rotate identities, repeatedly
   reload it or let another queued job replace the challenged page.
4. After the owner confirms completion, check that the same session shows the
   expected Cardmarket catalogue/product content, then resume the exact saved
   job. Elapsed time alone is never permission or evidence of clearance.
5. Keep progress saved while waiting. Independent official-source/image work may
   continue, but Cardmarket work remains paused. If the challenge/session expires,
   report that and wait for manual completion again rather than bypassing it.

This rule overrides automatic checkbox interaction in the existing scraper
browser code for this collection run. The collection mode must disable that
interaction and preserve the waiting session without the normal job watchdog
silently killing/replacing it. Keep the pause observable and resumable; do not
label the set empty, missing or complete. If safe session preservation cannot be
implemented, stop Cardmarket collection and report the specific limitation.

The local collection mode is a scraper change, not a recognition change. Test and run it on the Mac. No staging deployment is needed for acquisition; preserve the API, web, server scraper and existing catalogue/phone selectors. Do not push or redeploy `main` to install the local helper.

## 6. Phase A: one resumable global collection run

### A.1 Build registries before scheduling pages

Create a group registry with a stable audit/reference identity, era, source URL/ID, original and normalized set codes, official product IDs, Cardmarket expansion IDs/observed set URLs, expected numbered/unnumbered coverage and matching evidence.

Match known aliases from the audit and existing recovered rows first. A shared code or translated title is a candidate, not proof. If two checklist groups use the same Cardmarket expansion, schedule each expansion page once and attach both group references.

Reuse the current cloud product/helper rows and historical caches before issuing new requests. Historical scraper scripts contain hard-coded tab IDs, old schemas and counters: reuse their parsing/matching ideas, not their live write entrypoints.

### A.2 Fetch checklists and image references by set

- Modern cards: use the official Japanese product/card search and details. Cache the set response, source card IDs and image URLs. Cross-check the full checklist, secret entries and unnumbered cards.
- Older cards: use TCG Collector and specialist checklist/scan sources where official coverage is absent. Maintain per-card provenance and mark discrepancies for review.
- TCGdex: use as an additional populated source, not the complete set inventory.
- Fetch exact details only where the set response lacks required identity fields. Do not fetch the same card separately for every bundle membership.

Known MBG official query: `https://www.pokemon-card.com/card-search/resultAPI.php?regulation=all&regulation_sidebar_form=all&pg=947&page=1`. Its cached response has 23 entries, including the unnumbered energy; do not mistake the 22-entry numbered checklist for the entire product inventory. Resolve MBD's product against the official product registry rather than blindly extending numeric IDs.

### A.3 Scrape Cardmarket by expansion, not by card

Load each expansion's catalogue pages through the tested **local** scraper collection mode. Save actual singles links and whatever printing/ID metadata the listing exposes. Join numeric IDs against the cached product catalogue, scoped to the verified expansion. `idMetacard` and a repeated name are not exact-print identifiers.

Fetch an individual product page **only** when the listing lacks a required numeric ID, has conflicting metadata/variants, or needs exact-print confirmation. Track these as deduplicated exception jobs. Reuse known verified URL owners; never steal an existing mapping for a new row.

### A.4 Download images independently of the Cardmarket browser

Download observed official/specialist image URLs with a bounded normal HTTP pool on the workstation. Start with four concurrent downloads total, no more than two to one host; lower this on errors or any published stricter limit. Do not use expensive browser/proxy page loads to fetch ordinary public image assets.

Deduplicate by source asset URL and final byte hash, while retaining every printing's separate identity/provenance. Check MIME, successful decode, dimensions, cropping, Japanese language, number/artwork/stamp and watermarks. Keep original bytes. Do not substitute an English image or synthesize a reference. Use the existing stored-image route when external display delivery is unreliable.

### A.5 Reconcile exact-print mappings and handle exceptions

A verified mapping must agree on the Japanese product, set/deck, full collector identifier and relevant artwork/edition/finish/stamp. `/en/` is the Cardmarket interface language, not the printing language. Preserve true listing variants as separate choices where appropriate.

Per-card marketplace states:

```text
verified | ambiguous | not_found | not_listed_confirmed | blocked_source
```

A 403/timeout means blocked, not “not listed.” Absence of offers means zero stock, not absence of a product. Never replace an unresolved exact URL with an English counterpart or mark a search URL as verified. Prices remain null when the verified product has no guide data.

Only verified links set the existing `cardmarket_verified`/provenance fields. Check collisions across the complete catalogue, not just the current batch. Keep source mismatches and ownership conflicts visible in the held ledger.

### A.6 Checkpoints, retries and recovery

Use a small SQLite job ledger with transactional updates and an OS/process lock so two invocations cannot execute the same browser queue. Retain immutable raw/structured page evidence and a content-addressed image store.

Suggested entities: groups, source_pages, card_proposals, image_assets, product_candidates, verified_mappings and jobs. Job keys must include provider, operation, observed expansion/source ID and page/card identity. Record attempts, last outcome, retry_at, source checksum and parent job dependencies.

Use states such as `pending`, `running`, `done`, `retry_wait`, `waiting_for_owner`, `held`, `blocked`. A crashed process returns expired running leases to pending. Never automatically retry or expire `waiting_for_owner` as an ordinary running job. On resume, skip checksum-valid completed work; retry corrupt/missing files and due retry_wait jobs only. Separate operational retry from manual review; never automatically turn held matches into verified mappings.

For a timeout, allow one delayed retry on a healthy unchanged source/lane, then hold it for diagnosis. For rate limits, honor the source's retry time. Do not open every blocked product repeatedly. End each pass with a complete exception report and counts, rather than stopping at the first blocked set.

## 7. Phase A exit gate: what “retrieved” means

Before vectors, produce one acquisition report covering every one of the 336 initial groups and every deduplicated proposed printing:

- Existing row matched, genuine new printing, genuine missing asset, or unresolved identity.
- Reference image downloaded and validated, or a documented source/quality blocker.
- Exact Cardmarket URL/product ID verified, or an explicit unresolved/not-listed state.
- No pagination jobs or ordinary image downloads silently left pending.
- Group checklist coverage reconciled, including secret/unnumbered entries and duplicate bundle membership.

Do not label blocked/unresolved rows as completed. Finish all independent acquisition work first. If required images or printing identities remain inaccessible after diagnosis, report the exact exceptions and keep the global vector milestone pending until the owner resolves or explicitly accepts their exclusion. A genuinely confirmed absence of a Cardmarket product is an explicit marketplace outcome, not a reason to invent a link.

The owner specifically requested images and links first. Do not silently generate vectors for the first few successful sets while the global acquisition pass is still running.

## 8. Phase B: efficient vector/feature computation after acquisition

1. Freeze the verified eligible inventory and compare it with a fresh active cloud snapshot. Rebase if the parent release changed. Preserve old card IDs, mappings, existing embedding bytes and retrieval segments.
2. The current `api/scripts/build_cloud_reference_recovery.py` supports **one existing missing-image row**. It is not a whole-set importer. Implement a tested additive new-card batch builder; do not remove assertions and run it as if it already supports this workload.
3. Keep the unchanged DINO model/preprocessing and native x86/OpenCV feature contract. Reuse one model session per compute worker. Compute only new/changed approved images, caching each result by image hash + model/preprocessing/feature-contract hashes. Never reuse across incompatible contracts.
4. Process bounded compute chunks (initially about 100 eligible references per chunk), saving results atomically. Chunking is for restartability and memory control; it does not require rebuilding or publishing the catalogue per chunk. Adjust only from measured memory/runtime.
5. Review close same-language artwork/reprints. Retain the 326 previously curated exclusions. Some new printings may be reachable review choices instead of new independent retrieval vectors; explicitly verify their choice path. Do not assume a same-art foreign-language vector is an exact Japanese printing.
6. Assemble a cumulative candidate from cached chunks, including new rows, true printed totals, marketplace rows/helpers, source provenance, stored images, native features, artwork bundle, compatible operational FTS/totals and all digests/manifests.
7. Append artwork database indexes after the actual maximum, not the row count; the live parent has gaps. Preserve immutable hardlinked parent data and replace manifests via new inodes.
8. Export one paired phone index for the combined release from its exact catalogue/vector snapshot. Regenerate it only if the candidate changes after a failed check. Avoid exports for individual compute chunks. Preserve old phone vector/ID/metadata prefixes where the format permits.

Run expensive full-scanner regressions only for assembled review candidates and after substantive changes, not after every downloaded image or compute chunk. Run meaningful unit/contract tests as the relevant code is implemented.

## 9. One combined release and regression gates

Collect and reconcile the entire scope, freeze the verified eligible inventory,
then run one bulk vector/feature job with resumable checkpoints. Assemble all
verified additions into **one candidate schema/import, one coherent artifact
package and one phone-index version**. Perform one full regression campaign on
that combined candidate. Do not schedule per-set or 100–300-card activations.

Use MBG/MBD and other small subsets to validate the tooling and review identities,
without publishing them separately. If the combined regression fails, use cached
chunks and subset replays to isolate the offending references, resolve the failure,
then rebuild and recheck the combined candidate. Do not silently shrink the scope
or mark unresolved cards as done; report exclusions and their evidence explicitly.
If testing proves a separate release is necessary, explain the evidence and obtain
the owner's agreement to change the combined-release plan.

Keep new catalogue recovery separate from ranking/presentation fixes. The observed Gengar → Charizard suggestion defect and Exeggutor false-footer conflict need their own switches and test/replay evidence. Adding one reference does not certify that the guard defect is fixed.

The combined release candidate must pass:

- Exact schema/identity/number/URL checks; every accepted marketplace mapping has evidence; no unexplained URL/product ownership conflicts.
- Existing catalogue rows/mappings/vectors/artifacts unchanged except expressly reviewed corrections; normal cloud/native artifact loaders pass.
- Relevant API tests and the full API suite.
- Paired full-scanner replay against a frozen operationally identical baseline: existing English/Japanese/PCG/vintage/negative panel plus all saved Gengar, Exeggutor, Charizard and Ruin Wall cases. No previously correct result becomes wrong; no new wrong automatic answer or unrelated printing choice. Inspect every changed answer/choice list.
- Stored-scan replay for any ranking/printing-rule change; it does not replace full photo replay for new retrieval references.
- Phone compressed-index parity; public-ready manifest, checksum, Range/ETag checks after authorized activation; normal Android/iOS download/scan/confirm/save and background-check QA.

Do not run a second heavy scanner inside the live API worker. Use offline x86 execution or a separate resource-limited validation container. Photos/OCR stay outside Git. Scripted Flutter integration tests run on an emulator with `--no-uninstall`; physical phones keep their normal app and data.

Publish only through a new inactive cloud release and immutable assets with rollback. Obtain owner authorization for the concrete activation, preserve the retained API image/settings, validate the API before atomically switching phone ACTIVE, and retain the old schema/index. No production rollout is included.

## 10. Concrete artifacts the executing agent must produce

Create a new run directory such as `data/catalogue-gaps/ja-set-recovery-20261029/` (git-ignored public source data). Keep raw source evidence immutable; put resumable state separately.

```text
run.json                          # Scope, active baseline, versions, checksums
set-registry.json                 # All 336 groups + exact provider mappings
jobs.sqlite                       # Job state, leases, attempts and dependencies
source-pages/                     # Cached source evidence with hashes
images/                           # Original image blobs; per-print associations separate
printing-inventory.jsonl
existing-matches.jsonl
new-or-incomplete-printings.jsonl
image-manifest.jsonl
cardmarket-products.jsonl
verified-mappings.jsonl
held-mappings.jsonl
review/                           # Paired evidence and human-readable decisions
acquisition-report.json
STATUS.md                         # Current counts, exceptions and exact resume command
vectors/                          # Created only after the acquisition milestone
combined-release/                # One sealed release, index and regression evidence
```

Provide a CLI for initializing, collecting, resuming, reconciling, reporting and later building candidates. These are requirements to implement, **not commands that already exist**. Document the real tested commands in STATUS.md once implemented.

On every significant checkpoint report: groups enumerated/completed/blocked; distinct new printings; valid images; verified links; mapping exceptions; eligible/reference-only vectors; tests; publication state. Avoid a single “complete” percentage that mixes these milestones. Do not claim phone QA from an offline vector test.

## 11. Immediate next-agent checklist

1. Read this handoff and the audit; inspect current Git changes without overwriting them. Planning documents are currently local/uncommitted. Do not push `main` just to save them: staging auto-deploys it.
2. Verify the active baseline read-only, then prepare the native local Python/Chrome environment and dedicated profile. Record sanitized results; do not start server-side collection.
3. Implement/checkpoint the local acquisition ledger and macOS set-listing mode with meaningful tests, including manual Cloudflare wait/resume.
4. Prove complete MBG/MBD set collection and exact Gengar/Diancie mappings; save a review sample.
5. Initialize all 336 groups and run the global resumable acquisition queue in priority order. Collect checklists/images independently while the local Cardmarket browser is busy, waiting for the owner or cooling.
6. Reconcile and report all exceptions. Finish the acquisition milestone before vectors.
7. Only then run the bulk vector/feature job with cached checkpoints, assemble/test one combined release and phone index, and present its concrete activation package.

Do not stop after merely writing a runner or starting a background process. Follow the run to completion or document a specific external blocker with exact progress and a working resume path. Do not create recurring automations or leave unattended work under a claim that it is finished.

## Local collector repair verified on 29 October 2026

The expansion page links to a singles **listing**, which the old allowlist and
probe did not support. It is now supported alongside numeric expansion filters.
The response preserves observed pagination and listing links. The local batch
runner follows them, checkpoints every page, deduplicates canonical product URLs,
and pauses immediately for owner-only Cloudflare interaction. It never uses the
existing automatic checkbox helper in catalogue-listing mode.

Live MBG/MBD collection succeeded: 23 products each (44 numbered products plus
Darkness/Psychic Energy). The exact `mBG003` and `mBD005` product URLs are present.
A larger numeric Eevee Heroes listing returned 30 products and a next-page link.
Evidence and durable progress are under
`data/catalogue-gaps/ja-set-recovery-20261029-v3/`.

Continue using `api/scripts/ja_set_recovery/README.md` and `collect_listings.py`.
Add observed group-to-Cardmarket set mappings to `listing-seeds.json` in registry
priority order. The pilot initially had two mapped groups. The current routing checkpoint below supersedes that historical count. A completed
listing traversal is not proof of checklist completeness or an exact catalogue
mapping. Reconcile identities/images before the combined vector and release phase.
