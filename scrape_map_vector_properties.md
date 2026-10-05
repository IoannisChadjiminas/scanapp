# Complete English, then Japanese: scrape, map, recover images and vectorize

Prepared on 4 October 2026 (Asia/Nicosia), from an audit performed on 3 October UTC, for Codex to execute in a **new session**.

## 1. Objective and execution boundary

Finish the physical English catalogue first, then the physical Japanese catalogue. For each in-scope printing, find an independently sourced reference image, establish its exact identity, recover the correct Cardmarket product URL(s), preserve finish/printing distinctions, prepare recognition artifacts and publish an auditable result.

The fastest reliable approach is **set-level reconciliation plus an exception queue**, not individually searching every row. Reuse existing images, vectors, product URLs and expansion dumps before paying for new browser requests.

This file is a plan, not a claim that the work below has been performed. Its baseline comes from read-only PlanetScale MCP queries, the published review HTML, staging configuration/manifest inspection and repository code. No mappings, vectors, scraper jobs or database rows were changed during this audit.

Accuracy takes precedence over reducing a pending counter. A record that cannot be established reliably stays pending with a specific reason and its evidence. Completing research and completing mapping are different outcomes.

Do not change scanner thresholds, grading policy, production-labelled branch settings or hardware as part of catalogue completion. Preserve the existing late-grading behavior: return clean ungraded when grading misses the card deadline.

## 2. New-session handoff

### Locations and active deployment

| Item | Location / value audited on 3 October UTC |
|---|---|
| Working repository | `/Users/ioannischadjiminas/WebstormProjects/scanapp` |
| Current code commit | `ed676ab5e4e3c727c7c9587885486004f45178f0` |
| Mapping rules | `/Users/ioannischadjiminas/StudioProjects/PokeSingle/docs/cardmarket-listing-mapping.md` |
| Public review page | [Cardmarket version photos](https://ioannischadjiminas.github.io/cardmarket-version-photos/) |
| Review repository | [cardmarket-version-photos](https://github.com/IoannisChadjiminas/cardmarket-version-photos) |
| Public staging API | `https://scan.pokesingle.com` |
| Staging SSH alias | `auctaro-staging` |
| Dokploy checkout | `/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code` |
| Compose project | `scanapp-scanapp-z1mwj4` |
| API container | `scanapp-scanapp-z1mwj4-api-1` |
| Scraper container | `scanapp-scanapp-z1mwj4-scraper-1` |
| Shared data volume | `scanapp-scanapp-z1mwj4_scanapp-data` |
| PlanetScale organization / database / branch | `pokesingle / pokesingle-db / main` |
| Active schema / import | `pokesingle_recovery_20261003 / PS-RECOVERY-011-20261003` |
| Active artwork bundle | `/data/artwork/PS-REFERENCE-027-20261003` |
| Active precomputed reference features | `/data/reference-features/20261003-recovery027-amd64` |
| Staging secret file | `/etc/scanapp-staging/planetscale.env`; never print, copy into reports or commit its contents |

The current API loads a pinned, validated PlanetScale snapshot into a read-only in-memory cache at startup. Editing a local SQLite catalogue or HTML alone does **not** update that snapshot. API catalogue-write endpoints are intentionally blocked. New catalogue data must be published through a validated import and an explicit staging cutover.

### First actions in the new session

1. Read this file, repository `AGENTS.md`, the mapping rules above and any applicable skills. Check the current working tree; preserve unrelated work and historical untracked datasets.
2. Read `/api/v1/health`. Resolve the actually active schema/import, model, artwork and feature bundle; the values above are a baseline, not hard-coded future truth.
3. Re-run the baseline queries in section 13 using PlanetScale read-only access. Take a consistent snapshot/export before generating candidates.
4. Fetch the **published** review data, not only the old `/tmp/cardmarket-version-photos.v4JAO5/index.html`. The temporary file may disappear or become stale.
5. Create a new dated run directory under `data/catalogue-completion/`; do not overwrite prior discoveries or selections.
6. Build the exhaustive joined inventory and classify physical/digital, language, aliases, image status, mapping status and vector status.
7. Resolve the integrity exceptions in section 4 in a disposable candidate, with before/after evidence. Do not blanket-clear conflicting URLs.
8. Implement and test the small missing orchestration pieces described below. Start with a 50-record English pilot, then expand to whole-set batches.
9. Publish validated English batches while keeping unresolved English cases separate. Start Japanese acquisition/processing after English has reached the completion gate in section 11.
10. At session end, update `run.json`, queue counts, checkpoint paths, next actions and activation status so another session can resume without repeating searches.

Only this planning document was requested in this session. A later request to execute it should drive external writes/publication; the document itself is not evidence of new approval or completed changes.

## 3. Audited baseline: what is actually remaining

### Catalogue rows, not unique physical printings

| Coverage | English: all imported rows | Japanese |
|---|---:|---:|
| Catalogue rows | 25,634 | 14,706 |
| Image marked present / pad vector present | 25,070 | 12,123 |
| Image missing | 564 | 2,583 |
| Square vector present | 25,069 | 12,123 |
| Artwork-index cards | 4,188 | 2,312 |
| Primary Cardmarket URL stored | 21,141 | 3,086 |
| Primary URL missing | 4,493 | 11,620 |
| Indexed card with no primary URL | 4,077 | 9,876 |
| Stored URL but missing image | 148 | 839 |

Important scope correction: **2,480 English rows belong to Pokémon TCG Pocket**, including 161 missing images and no stored Cardmarket primary URLs. The provider explicitly identifies their series as `tcgp`; these digital cards should not create a physical Cardmarket mapping backlog. The series was checked through [TCGdex's series endpoint](https://api.tcgdex.net/v2/en/series/tcgp), including sets A1, B1 and B2a.

After excluding those currently identified digital sets, the English row-level backlog is:

- **23,154 physical-catalogue rows**, with 22,751 images/pad vectors.
- **403 missing images**: 148 already have a stored URL; 255 lack both image and URL.
- **2,013 missing primary URLs**, including 1,758 rows with images/vectors already available.
- These are still row counts, **not deduplicated print counts**. There are 561 English groups with identical language/set/name/collector fields, spanning 1,122 rows. Legacy unprefixed and `en:` IDs explain many of them; exact printing/variant equivalence must still be checked.
- Do not delete Pocket or alias rows during this project. Record exclusions/aliases explicitly and preserve existing scan/history references. Separately evaluate whether digital entries should participate in a physical scanner's runtime search.

### Product and review inventories

PlanetScale has **71,296 Cardmarket products**: 35,796 marked matched with a card owner, and **35,500 unmatched**. That unmatched total includes multiple languages, variants, missing catalogue printings and non-card products; it is not an English/Japanese card count.

There are **1,874 stored expansion crawls**, all carrying the historical completeness marker `1`. Completeness describes that saved crawl, not present-day completeness or freshness. Most products have no separate `listing_image_url`: only 5,473 products carry one. Additional listing photos exist in review caches/HTML, so those caches must be joined before requesting more photos.

The published HTML contains **27,503 review rows** and 6,660 reference-card records. Its top-level summary includes older September totals; those totals must not replace live database counts. Audited HTML SHA-256: `03bfcf3ed5075637ee8bd77306f3d72a9eaec25bf95eade17eff091b2e94942d`.

| Explicitly language-labelled review subset | English | Japanese |
|---|---:|---:|
| Rows | 1,837 | 2,787 |
| Mapping saved and indexed according to review flags | 1,401 | 1,152 |
| Mapped rows with recognition warning | 572 | 70 |
| Unmapped rows | 436 | 1,635 |

English's 436 comprises **402 manual mapping holds, 33 TK11 print holds and one non-card item**. The familiar 402 dropdown is therefore not the complete English backlog. Japanese also has **16,933 rows in legacy `ja_unlinked`, `ja_nonum` or `ja_sibling` statuses**, many without a populated language field. They overlap the language-labelled subset and must not be added to it blindly.

The 572 English recognition warnings are **not 572 unmapped cards**. Preserve their saved mappings unless identity evidence is wrong; test recognition and printing ambiguity independently. Review `mapping_saved=false` on older/null-language rows is also not authoritative proof of no database mapping: several historically completed statuses lack the newer flag.

### Current artifact properties

- Full-card vectors: **39,453 pad / 39,452 square**, 384 dimensions, DINOv2-small.
- Pinned model revision: `ed25f3a31f01632728cabb09d1542f84ab7b0056`.
- DINOv2 ONNX SHA-256: `2ddf6ec79e377069b6e884a838f42c65b8a70e222dada1eeeb41979948ce1146`.
- Artwork: **6,531 cards / 13,062 regions** across all languages. Existing profiles are `conventional_window` and `broad_center_hypothesis`; these are retrieval hypotheses, not verified exact-layout classification.
- Precomputed reference features: `reference-features-v1`, 48,653 catalogue entries, **39,453 available**; unavailable references are explicitly recorded.
- Staging artifact sizes: reference features approximately **3.5 GiB**, artwork approximately **23 MiB**. A second full feature copy does not fit in the audited 1.6-GiB free disk space.
- Feature contract includes x86_64, OpenCV 4.11.0, NumPy 2.2.6, Pillow 11.3.0, the OpenCV build checksum, crop/mask settings, two SIFT configurations and thumbnail preprocessing. A Mac-native rebuild is not automatically compatible with staging.
- The general manifest `counts.card_embeddings` says 78,904, but actual pad plus square rows total **78,905**. Reconcile this stale aggregate in the next candidate; per-mode counts/manifests are the checked runtime source.
- No orphan vector IDs, no matched product owners missing from `cards`, and no nonempty primary URLs absent from the product table were found by the audit queries.

## 4. Fix integrity and inventory problems before adding more mappings

### URL owner conflicts

The audit found **163 primary-URL/product-owner disagreements**:

- 127 are explained at the ID-string level by legacy English IDs such as `base1-1` versus `en:base1-1`. Confirm equivalent printing/variant/source evidence and register aliases; do not call these 127 proven wrong cards.
- The remaining **36 are not explained by that prefix**. They include 12 cross-language disagreements and same-language collector/set conflicts. Some may be legitimate extra/native aliases, but several are demonstrably incompatible identities.
- Examples: English `en:swsh10.5-015` points to a Japanese Pokémon GO product owned by `ja:S10b-015`; English Aerodactyl V `en:swsh11-179` points to product #180; Japanese `ja:E2-076` points to a different L2 card; `ja:M3-061` points to an English M Rayquaza EX product.

Export all affected rows and images, separate alias equivalence from real conflicts, and propose targeted corrections. Preserve old values and product owners in the audit. Retain or restore the correct owner's link; do not transfer a URL just because it already appears on another card. Existing runtime identity guards are useful protection, not a substitute for correcting source data.

### Missing square vector

`en:mep-078` Toxel has a verified independent reference and a pad vector, but no square vector. Add the square vector from the **same verified source bytes** in the candidate and update the per-mode manifests/checksums. Keep its Cardmarket URL pending until the actual listing identity is verified; a usable recognition reference does not establish a marketplace slug.

### Scope, aliases and language

Build a registry of Cardmarket expansion → exact catalogue set/deck/subset/language. Validate registry entries with publisher/checklist evidence and representative edge cases. Include multilingual expansion families explicitly: a Cardmarket website path beginning `/en/` is the UI language, **not** proof that the card is English.

Preserve raw and normalized collector values. Only compare numeric padding within an already verified identity scope. Keep letter suffixes, denominators, promo prefixes, GG/TG/Shiny subsets, deck-circle numbers and set emblems. Do not collapse Aquapolis `95a`/`95b`, Trainer Kit E/Z labels or modern set/collector suffixes.

## 5. Build one exhaustive reconciliation inventory

Create a resumable `inventory.jsonl` from a consistent active snapshot, with one task key per canonical printing and separate related-product tasks. Join:

1. `cards`: identity, source, image and primary mapping fields.
2. `card_embeddings`: pad/square membership and source hashes.
3. `artwork_embeddings`: card/profile membership and provenance.
4. `cardmarket_products`: all listing URLs, product owners, image URLs and expansions.
5. `cardmarket_url_helpers`: helper/primary mapping metadata.
6. `cardmarket_review`: review evidence, holds, candidates and warnings.
7. `source_records`: stored expansion crawls and snapshots.
8. `reference_metadata`: vector manifests, original-source/review metadata and source selections.
9. Published HTML's embedded/cached photos and `official/`, `photos/`, `version-photos/`, `pairs/` assets; local prior recovery selections where hashes still agree.

Do not assume the review page, old SQLite volume or prior recovery inventory is complete/current. Include unmatched products not shown in HTML and catalogue cards with no review row. Also include verified Cardmarket printings absent from the catalogue; adding these can increase the inventory even while coverage improves.

Produce disjoint work queues, plus independent capability flags:

| Queue | Next action |
|---|---|
| Identity/owner conflict | Resolve before further linking |
| Exact card exists, URL missing | Reconcile imported set URLs; no new image/vector if already usable |
| Exact card exists, image missing | Recover independent reference; mapping may already be done |
| Exact printing absent | Establish native identity first, then image and mapping |
| Same printing, different finish listing | Attach validated listing variant to existing card |
| Stamp/deck/edition differs | Establish distinct printing, not a plain-art substitution |
| Source found, identity not proven | Review queue; do not publish vectors yet |
| URL known but page inaccessible | URL-access queue, separate from identity confidence |
| Recognition/printing warning only | Test with independent queries; preserve correct mapping |
| Digital/non-card/unsupported format | Explicit exclusion or separate collection |

Persist `run.json` with parent import, counts, file hashes, resumable checkpoints, attempts, approvals, verification decisions, published batch/import IDs and the next uncompleted step. Temporary directories are conveniences, not authoritative checkpoints.

## 6. Source strategy: where the original images come from

An “original” means an independent, full reference of the **correct printing**, not a generated reconstruction, a same-art substitute or the exact camera photo used to test the scanner. Official publisher art is preferred, but verified third-party scans are acceptable when clearly labelled.

### English source order

1. **Existing exact reference and frozen verified selections.** Revalidate identity and SHA-256; reuse rather than redownload/re-embed.
2. **Official Pokémon English database/assets and official product/checklist pages.** Use the [English card database](https://www.pokemon.com/us/pokemon-tcg/pokemon-cards). Existing discovery code handles multiple asset roots, promo padding and special subset aliases. An HTTP 200 from a guessed asset path is only a candidate until the visible identity agrees.
3. **Independent English scan catalogues:** [PkmnCards](https://pkmncards.com/), [Serebii Cardex](https://www.serebii.net/card/) and exact TCGdex references. These are not Pokémon-official sources. Confirm the card page, set, collector and actual image, not merely the search title.
4. **Exact promo/deck archives**, especially [Pokumon](https://pokumon.com/) for Trainer Kit circles, retailer/event stamps, W promos and distribution-specific releases.
5. **Exact TCGplayer product reference or a reputable store's independently identified scan** for remaining modern cards/promos. Retain source page and image URL separately. Prefer a higher-resolution source where available; do not infer a new product ID by incrementing another one.
6. **Owner-supplied scan/manual review** if independent online evidence remains unavailable. Keep provenance explicit and do not count it as an unseen benchmark query.

### Japanese source order

1. Reuse exact Japanese images and the existing user-scraped listing-photo cache. Listing photos confirm marketplace identity; they do not automatically supply an independent original.
2. **Official [Pokémon Japan card search](https://www.pokemon-card.com/card-search/).** Fetch each set listing once, then detail pages. Verify the Japanese title, actual printed number, official set identifier/regulation-logo evidence and image. The printed denominator is not a set code.
3. Exact Japanese TCGdex/Serebii/archive pages, clearly labelled third-party, for vintage sets and decks not covered by the official search.
4. Japanese promo/deck references and trustworthy card-store scans with the exact distribution/emblem/collector shown. Translation or species equivalence only generates candidates.
5. Manual scan/review when no independent source can establish the print.

The largest Japanese missing-image families are VS1, E1–E5, PMCG-era, neo and PCG sets. Work by complete set/archive rather than repeating thousands of card-name searches.

### Image acceptance rules

- Validate image bytes, dimensions, decoding, full-card visibility and checksum; reject placeholders, composites and wrong backs.
- Compare visible name/language, art, layout, set, collector/denominator, copyright, edition/stamp/emblem and special deck marks with listing characteristics.
- Run OCR to corroborate readable fields, never invent missing text. Contradictory readable evidence blocks acceptance; unreadable distinguishing evidence goes to review.
- A shared illustration or a high vector score does not establish an exact printing.
- Prefer clean, unobstructed scans. A Pokellector watermark does not make the identity wrong, but classify it as a fallback and test recognition before using it. Do not remove watermarks, stamps or fabricate foil/edition pixels.
- Keep `official_pokemon` separate from `independent_catalogue_not_official`. Keep representative base-art evidence separate from an exact stamped-print reference.
- Save source page, fetch time and content hash. Source availability and permission for public redistribution are separate issues; respect source terms, robots rules and permitted usage. Do not assume a publicly visible image can be mirrored publicly without restriction.

## 7. Cardmarket URL recovery and scraper use

### Reconcile cached URLs first

Most mapping work should not require opening a browser:

1. Extract exact existing URLs and product IDs from the stored 71,296 products, expansion snapshots, review rows and helper maps.
2. Normalize titles, removing copied price text such as `From 7,00 €` without changing identity tokens.
3. Group by exact expansion/language/deck/subset; verify that registry entry once.
4. Join full collector identity and card name inside that group. Verify art/print evidence against the saved listing photo when available.
5. Emit candidates with evidence and all sibling variants. Reject ambiguity/ownership conflicts instead of choosing the first result.
6. Request missing/changed product pages only after this local pass. Never synthesize `V1`, `V2` or a slug and mark it verified without positive listing evidence.

Use separate URL evidence states:

- `candidate_url`: proposed, not established.
- `listed_in_saved_expansion`: exact link captured in a dated source dump.
- `product_identity_verified`: canonical product page/metadata confirms the exact identity.
- `live_access_verified`: successful recent product-page fetch with expected canonical URL, identity and product ID.
- `blocked_or_unavailable`: 403/challenge/timeout; not proof the URL does not exist.
- `confirmed_not_found`: bounded reproducible 404/410 or documented removal, not an anti-bot error.

Being present in an old expansion dump can justify a researched mapping when the full identity is independently established, but it must not be described as a fresh live-page check. No shortcut converts an expansion-level fetch into independent live verification of every product.

### Current scraper capability and limits

Staging was checked: residential proxy configuration is present/effective, country `de`, scraper health OK and no active rate-limit cooldown. The browser is sticky/reused; sessions change on failed challenges/rate limits or replacement. Current effective limits:

| Setting | Audited value |
|---|---:|
| Browser slots | 1 by default |
| Attempt deadline | 90 seconds |
| Sticky browser lifetime | 1,800 seconds |
| API paid page budget | 1,000/day |
| API paid transfer budget | 1,000 MB/day |
| Session/IP hourly escalation limits | 1,000 / 1,000 |
| URL cooldown | 60 seconds |
| Configured page gap | 0 seconds |
| Scraper rate-limit cooldown | 900 seconds by default |

These are ceilings/settings, **not measured throughput**. On this shared 2-vCPU / approximately 4-GiB host, keep one browser. The API now allows 2 GiB RAM, scraper 1.5 GiB; many other services share the host. Disk had approximately **1.6 GiB free on a 38-GiB root disk**. Do not run a full vector build or duplicate an entire data volume there.

Important gaps in the current scraper:

- Its allowlist accepts Singles product URLs, not expansion catalogue/search crawling.
- Its parser/terminal conditions are oriented around offers/price reads, not a complete catalogue/photo evidence export.
- Its optimized browser blocks Cardmarket image hosts/resources. Extracting an image URL is not the same as downloading/seeing the image.
- Existing paid reservation accounting is designed around one price-read attempt. A future catalogue mode must account for all navigation and image bytes, not bypass the budget by calling `/scrape` directly.

Add an explicit, tested **catalogue-evidence mode** or a separate offline collector adapter before relying on the scraper for set discovery/photo capture. Preserve price mode unchanged. Catalogue mode should capture canonical URL, product ID, expansion/name/collector properties, variants, image URL/bytes, fetch outcome and timestamp, and recognize identity even when there are no sale offers.

Reuse the current proxy/session machinery only for authorized public requests. Respect `Retry-After`, rate limits and site rules; preserve cooldown/backoff instead of rotating proxies to evade an access restriction. Stop blocked work into a helper/manual queue after bounded attempts. Proxy rotation is a transport tool, not identity evidence or permission.

Start with one browser, a small jittered page gap and **at most three attempts per unresolved request**, with increasing backoff. Cache results by canonical URL and hash. Reuse successful sticky sessions; do not rotate on every successful card. Keep direct diagnostic probes off unless diagnosing a specific network failure because they add paid reads.

## 8. Printing, finish and property rules

Use the established mapping contract:

- Language, exact set/deck/subset and full collector identity must agree before a listing is attached.
- A finish change on the same printing uses the **same card ID**, with additional validated product URLs/finish properties.
- Primary URL selection is explicit: standard/plain listing where verified, not “V1 must be plain.” V-number semantics are product-specific and must be checked.
- A stamped prize-pack printing is not the plain main-set card just because art and collector number are shared.
- Different art, language, edition, deck emblem, numbered Trainer Kit circle or genuine release identity may require a distinct printing record; do not create a new identity for every foil finish.
- Oversized, composite/V-UNION, Raid Battle pieces and markers need explicit format/support decisions. Do not silently map them onto tournament-size cards.
- For truly unnumbered releases, verify the exact release, design, language, year/distribution and distinguishing print characteristics. Introduce a tested `unnumbered_identity` validation path where justified; do not fake a collector number, use the year as a number or reuse an arbitrary numbered Energy. If the current numbered-only builder cannot represent it, retain the hold until that path exists.

### Proposed evidence/task properties

This is the **target task/evidence contract**, not a claim these columns/tables already exist. Implement it first in versioned JSONL/JSON and map it to existing `metadata`/provenance fields. Add database tables only if needed for durable queue/alias relationships, with an explicit migration.

| Property group | Required information |
|---|---|
| Identity | task ID, stable card ID, aliases, language, physical/digital scope, set ID/name, exact expansion/deck/subset, category/format |
| Printed evidence | raw collector string, parsed prefix/number/suffix/denominator, set/emblem/regulation marks, edition, stamp/circle, copyright; unknowns remain null |
| Original source | source kind, source page, image URL/storage key, SHA-256, dimensions, quality/watermark flags, exact-print versus representative-art role |
| Listing | canonical product URL/ID, raw title, expansion, variant/version, finish, product owner, page/photo hashes, access/identity states and checked time |
| Verification | decisions, evidence references, OCR fields/confidence, visual comparison, conflict flags, reviewer/time, reason for approval/hold |
| Recognition | full-card model/revision/hash, pad/square preprocess version and vector hashes, artwork profiles/layout evidence, family ID, local-feature contract/checksums |
| Publication | parent import, candidate/batch IDs, schema/import, artifact hashes, regression results, cutover/rollback state, HTML revision |
| Retry/review | attempts per source, failure class, next retry, search scope exhausted, priority and precise user-review question |

Art-family grouping must be independently validated. Exact hashes can deduplicate identical source assets; perceptual hashes/vector/keypoint similarity propose shared-art families but do not automatically prove identical printing or finish. Grade, condition, seller stock and price are not stable card-image identity properties.

## 9. Execution order and batch policy

### Phase A — Baseline and integrity repair

Create the joined inventory, registry, alias/conflict report and fresh counters. Resolve the 36 non-prefix owner conflicts individually or hold them; verify the 127 prefix aliases. Repair Toxel square coverage, reconcile stale aggregate counts and exclude the 2,480 identified Pocket rows from physical completion metrics. No global relinking/rebuild.

**Deliverables:** inventory, alias registry, conflict decisions, physical scope totals and an independently validated pilot candidate.

### Phase B — English high-throughput mapping and source recovery

Prioritize work that completes a missing capability without new research:

1. Existing English image/vector → missing URL, using cached expansion products and exact set registry.
2. Existing English mapping → missing reference image: 148 row-level candidates before deduplication.
3. Missing both image/URL: 255 physical row-level candidates before deduplication.
4. Missing native print records discovered from unmatched products.
5. Manual print/finish holds and recognition warnings as separate tracks.

Pilot **50 English records** covering ordinary sets, trainers/Energies, promos, suffix/subsets, foil siblings and a stamped/deck exception. Review every changed identity/mapping. Once the full path passes, raise ordinary batches to **250–500 listings grouped by expansion** and publish by verified set or coherent source family. Process 25–50 ambiguous print exceptions per batch so evidence remains inspectable.

The 402 manual holds are research tasks, not all low-hanging mapping work:

| Main English hold group | Rows | Approach |
|---|---:|---|
| No number / exact release needed | 179 | Distribution/design catalogue, exact unnumbered identity; no numbered substitution |
| Trainer Kit exact numbered original unavailable | 92 | Deck list, circle/emblem, archive source; never plain-set art as exact scan |
| Print/finish exceptions | 49 | Listing siblings + exact stamp/edition characteristics |
| Oversized/composite | 21 | Separate format decision and reference, or explicit exclusion |
| Prize stamp layout mismatch | 10 | Verify actual series/stamp layout, keep separate printing |
| Exact stamped print or URL conflict | 7 | Resolve source and URL together |
| Raid Battle variant | 6 | Distinct game/format; not an ordinary VMAX printing |
| Listing photo unavailable | 5 | Recover cached or authorized listing evidence; do not equate unavailable with wrong |
| Retailer/event stamp source needed | 5 | Exact promotional distribution source |
| Professor Program source unavailable | 4 | Program-specific references, otherwise manual hold |
| Other/manual/unclassified groups | 24 | Split the 18 null-group rows and six remaining specific exceptions |

The separate **33 TK11 holds** include existing exact-stamp source candidates. Example: Alolan Ninetales SM128, blue circle 17, has a Pokumon source candidate, but was not mapped/indexed because reference quality/exact-print readiness remained unapproved. Recheck those candidates first instead of restarting general web searches.

For the 572 recognition warnings, group by underlying card/art family and cause. Test each changed reference against an independent query where available. Shared-art printing ambiguity is an acceptable reviewed outcome; correct mapping does not require an impossible visual distinction between identical finishes.

### Phase C — Japanese catalogue and mapping

After the English gate, use the same tested pipeline with Japanese-specific evidence:

1. Adopt and hash the user's existing Japanese scraper output; validate its schema/identity before trusting it.
2. Build the exact Japanese expansion/deck registry. Link whole standard numbered sets to existing Japanese rows; do not map English translations to English cards.
3. Recover the **839 already-mapped Japanese rows missing images** first, then remaining missing images grouped by official/vintage source set.
4. Reconcile the **9,876 image-indexed Japanese rows lacking primary URLs** and unmatched Japanese product families. These queues overlap, so use task keys rather than add their counts.
5. Establish absent vintage/deck/promo native records. Large old-source families require archive adapters; a repeated official-search failure is not proof no original exists.
6. Work unnumbered Energies, PLAY/PokePark/movie/deck-emblem promos and finish siblings in explicit exception batches.

Start with 50 Japanese records across modern sets, older sources, promos, unnumbered/deck cards and visually similar English/Chinese negatives. Use 250–500-listing ordinary batches only after that pilot passes; small batches remain appropriate for uncommon printings.

### Bounded research escalation

For an unresolved exact printing: existing cache → official source → two appropriate independent archives → exact store/reference page → manual queue. Record all attempts. Once a source family is exhausted, work another family rather than repeating the same search on every card.

A timeboxed first pass may move hard English cases to documented holds, but it must not label English “fully mapped.” At the English gate, each physical item must either be validated/published, explicitly excluded for a supported reason, or have a precise unresolved/manual hold. Japanese can then proceed while the English hold list remains visible.

## 10. Vector and precomputed-feature preparation

Do this offline against a disposable copy/export of the **active cloud snapshot**, not the stale operational SQLite catalogue.

1. Freeze accepted source bytes, identities, decisions and checksums in `selection.json`; no unresolved references enter it.
2. Append pad and square vectors only for new/changed accepted reference identities. Existing usable images and vectors are reused. Preserve unchanged IDs/order/vector bytes and record parent hashes.
3. Use the pinned DINOv2-small model, 384 dimensions and the existing preprocessing contract. Similarity scores are retrieval signals, not calibrated probabilities or mapping approval.
4. Prepare artwork vectors for every newly accepted reference, using validated layout treatment. Existing conventional/broad-center crops are hypotheses; full-art, e-Reader/asymmetrical, textless, composite and oversized layouts require inspection/explicit rules rather than one universal crop.
5. Expand existing artwork coverage by English then Japanese set batches. Track coverage independently: full-card coverage today does not imply artwork coverage. Prioritize shared-art/reprint/confusing families, then remaining eligible prints; unsupported layouts stay explicitly unavailable.
6. Build local reference features/thumbnails in the staging-compatible **linux/amd64** environment with the exact OpenCV/NumPy/Pillow/build/profile contract. Reuse unchanged verified `.npz` artifacts when that contract and the source hashes match; generate a new catalogue-bound manifest. A tested incremental reuse path is needed—the current feature builder recomputes all available references.
7. Validate array shape, finite normalized vectors, unique IDs, set membership, row/per-mode hashes, image-feature correspondence, artwork profile coverage and the feature reader contract.
8. Archive originals durably for reproducibility and review. Recognition can use precomputed features without original files on the server, but image endpoints/review still need a usable image source. Preserve existing image paths/source relationships or deliberately migrate them with a compatible new manifest.

R2 is an optional later storage adapter, not a prerequisite for completion. No configured R2 bucket was verified in this audit. If adopted, use content-addressed objects, retained source attribution/permissions, checksums and an explicit resolver; do not silently replace filesystem paths or assume the current feature builder accepts `r2://`.

Avoid full data copies/builds on the nearly full staging disk. Build on the local machine/offline builder, transfer only required validated additions, and budget old/new feature/artwork bundles plus rollback before cutover. The current feature bundle is approximately 3.5 GiB, so a naive second full deployment is blocked by capacity.

For unchanged feature files on the same filesystem, implement/test an immutable reuse deployment using **hard links or supported reflinks**, with a fresh release-specific manifest and independent files for changed/new records. The current feature reader rejects symbolic links. Never modify a hard-linked file in place: that would also alter the old release and destroy rollback integrity. Compare checksums before reuse, verify both manifests after assembly, and account for changed-file space explicitly. If same-filesystem immutable reuse is unavailable or the delta exceeds headroom, stop publication and arrange additional storage; do not drop validation or old releases to make it fit.

Never remove user data/rollback archives merely to create space without explicit direction.

## 11. Verification, publication and honest completion

### Gates for each batch

All changed records need identity/evidence checks. Sampling alone cannot certify unreviewed product mappings.

- No wrong-language, wrong expansion/deck, collector suffix or observed stamp/layout contradictions.
- URL ownership, primary-helper mirror and finish-sibling relationships agree after alias resolution.
- New references are independent of benchmark query photos; image hashes match approved selections.
- Pad/square and approved artwork vectors/features reference known stable IDs and matching source bytes.
- Existing correct links/vectors unchanged except specifically reviewed corrections.
- Unit tests cover every new normalization/parser/unnumbered/alias/scraper path and negative collision case.
- Re-run the frozen recognition baseline: **155 photos**, with raw **100/100**, slab **46/49 scorable**, and all five phone cases correct. Preserve correct matches; the three existing slab identity misses are not successes to advertise.
- Add held-out queries for each newly added source/layout family. A scan of the reference itself is a vector/index sanity check, not independent camera accuracy proof.
- Test shared-art different languages, plain versus prize stamp, holo siblings, Trainer Kit circles, V-UNION/oversized support decisions, blank/noise and wrong URL resolution.
- Preserve printing ambiguity and confirmation UX. Returning the right artwork family does not confirm an unreadable exact printing/finish.
- Test grading controls and late clean-ungraded responses; snapshot changes must not corrupt grading or mutate saved responses after return.
- Check upload-to-result latency on a small fixed phone/slab panel. The current hardware has no universal five-second SLA; avoid materially worsening the measured baseline by indiscriminate index expansion.

### Publish as a coherent snapshot

1. Freeze a candidate release with parent import, expected row/vector delta, all table/artifact digests, source approvals and test report.
2. Use a dedicated import/write role, not the runtime role. Prefer a new versioned candidate schema/import; never expose a partially loaded candidate as `validated`.
3. Bulk-load bounded chunks, validate foreign identities/uniqueness, all primary/helper/product mapping mirrors and checksums. Update both per-mode manifests and overall counts from actual rows; do not hand-edit checksums to hide failures.
4. Preserve the old validated schema/import, artifact directories, source values, config and API image for rollback. Confirm disk headroom before transferring/activating anything.
5. Stage compatible artwork/features/assets first, then cut over the API's pinned import/schema and artifact paths together. No per-card API reload.
6. Verify startup checksum success, `ready=true`, active import/version, per-language counts, image endpoints and the small live scan/variant control panel.
7. Verify wrong-URL rejection and valid finish selection. Test that chosen Cardmarket URLs survive confirmation/history.
8. Publish the review data/HTML from the **activated import**, not a separate manually maintained counter. The scanapp repository has Git-triggered deployment; a casual push can redeploy services. Use an explicit tested rollout, and do not promise an API-only deployment when using that hook.
9. Update durable checkpoints and retain a reversible correction ledger. Do not erase unresolved cases or overwrite historical selections.

PlanetScale's existing primary fields, `cardmarket_products` ownership and helper metadata must agree. For local candidate builds, also maintain the SQLite mapping code path and `/data/cardmarket-maps.json` export as applicable. The legacy `link-cardmarket.sh` and offload scripts are not a substitute for the cloud import/cutover protocol.

### HTML dropdown/status contract

Separate capability states so users can see the real result:

- `Done · English/Japanese · exact mapping + reference + full vectors`.
- `Done · mapping · artwork/printing recognition warning` (not a false confident printing).
- `Pending · exact original image`.
- `Pending · exact Cardmarket identity/URL`.
- `Pending · live URL access check`.
- `Pending · missing catalogue print`.
- `Pending · stamp/finish/manual identity review`.
- `Excluded · digital/non-card/unsupported format`, with a reason.
- Per-release “newly completed” filter and stable `?batch=` values.

Show both listing and independently sourced reference images, reference source link/type, mapped URL(s), finish/stamp properties and precise pending reasons. A saved mapping with blocked live access may show **mapping done / live check pending**, but not “everything verified.” Missing artwork-profile coverage should also remain visible.

Every task must finish with a durable disposition. **English/Japanese fully mapped** means all in-scope exact print mappings are resolved; **research pass complete** allows explicit holds. Never confuse those two claims or count exclusions as successful mappings.

## 12. Make it fast: implementation sequence and checkpoints

### Reuse existing tools, but remove hard-coded historical assumptions

| Existing component | Reuse / required adaptation |
|---|---|
| `api/scripts/discover_official_missing_images.py` | Official source adapters; add persistent per-request cache/resume and broader safe set/deck handling |
| `catalogue/bootstrap/catalogue.py` | Japanese set/detail parsers and collector safeguards; use discovery paths without live upserts |
| `api/scripts/verify_recovered_references.py` | OCR corroboration; add appropriate print/stamp quality review and unnumbered handling |
| `api/scripts/freeze_official_reference_selection.py` | Selection/evidence concept; parameterize its date, shard/source locations and decisions |
| `api/scripts/build_recovered_reference_candidate.py` | Append-only candidate construction; currently requires a numbered identity and an existing unambiguous set, so not enough for entirely new sets/unnumbered releases |
| `api/scripts/build_cloud_reference_recovery.py` | Guarded cloud correction example; currently single-card recovery, not a general multi-thousand mapping publisher |
| `api/scripts/build_reference_features.py` | Offline feature builder; add tested unchanged-artifact reuse if needed |
| `api/scripts/audit_recovery_candidate.py` | Integrity concepts; currently tied to old selection/artwork paths and must be parameterized |
| `api/scripts/probe_reference_recovery.py` | Frozen card/slab/phone replay and cloud-cache-like candidate test |
| `scripts/audit_cardmarket_photos.py`, `scripts/rank_cardmarket_photos.py` | Candidate retrieval and comparisons; ranking is not approval |
| `scraper/main.py`, `browser.py`, `proxy.py` | Sticky session/deadline machinery; add explicit catalogue mode and resource/accounting tests |
| `api/app/planetscale.py` | Keep validated pinned read-only runtime loading; do not bypass it |

Build the missing inventory/reconciliation, expansion registry, source adapters, task state machine, bulk candidate publisher and HTML exporter as small tested tools. Do not rewrite the recognition engine or refresh every vector for a URL-only change.

### Safe work overlap on the current setup

- Parallelize **bounded HTTP/cache discovery**, hashing and offline candidate preparation. Start with four direct image fetches and two Japanese detail fetches, matching existing discovery limits; reduce on rate-limit/error/memory signals.
- Keep the paid browser single-threaded. Do not launch overlapping chrome windows or embedding builds on staging while users test scans.
- CPU-intensive vector/feature work runs off the shared staging host. Start feature workers at one; raise only after observing memory/throughput on the builder.
- Within English, independent mapping-only, image-only and manual-review queues can progress without waiting for each other. Publication remains serialized.
- Cache exact URL/page/image outcomes and unchanged checksums. Fetch a set/detail listing once, review grouped contact sheets with zoomable number/stamp crops, and batch vector inference by accepted source.
- Review every ambiguous/contradictory item. For ordinary set batches, deterministic exact-identity checks plus recorded per-item comparison are required; one inspected card does not validate every card in a set.

### Timing and milestones

Do not promise a completion date before the first pilot. Discovery, source permissions/access, hard print variants and human review control the long tail.

| Milestone | Exit condition |
|---|---|
| Baseline | Exhaustive reconciled inventory; aliases/exclusions and conflicts quantified |
| English pilot | 50 varied records pass full evidence → candidate → staging → HTML flow |
| English ordinary batches | Every supported ordinary physical set reconciled; reusable sources/URLs consumed |
| English exception closure | Every remaining English task approved, explicitly excluded or documented as a precise manual/source hold |
| Japanese pilot | Japanese official/legacy/deck/language-negative cases pass |
| Japanese ordinary batches | Set-level mapping and available source families completed |
| Final audit | No unexplained inventory/task/artifact/HTML mismatch; both unresolved hold lists exported |

After the pilot report verified mappings/hour, references/hour, paid bytes/verified record, source failures, review minutes/exception, vector/feature build time and publication overhead. Estimate remaining work by those queue-specific rates, not one global cards/hour figure.

For planning only: 2,055 review rows still carry `pending_url_check` historically. If every one needs a new paid product request, the current 1,000-pages/day ceiling alone spans **at least three budget days**, before retries or other traffic. Cached link/identity evidence can reduce the work, but cannot be relabelled fresh live access. This illustrates why the plan separates URL identity and live accessibility.

## 13. Baseline query/runbook reference

These are read-only examples for the audited schema. Re-resolve the active schema/import first. The MCP query tool accepts **one SQL statement per call**, not semicolon-separated batches. Use primary reads for audit consistency, and a repeatable-read export for actual candidate construction.

```sql
-- Catalogue row counts and basic missing capabilities.
SELECT language, count(*) AS cards,
       count(*) FILTER (WHERE has_image = 0) AS missing_images,
       count(*) FILTER (WHERE coalesce(cardmarket_url, '') = '') AS missing_urls
FROM pokesingle_recovery_20261003.cards
GROUP BY language ORDER BY language;
```

```sql
-- Primary URL owner disagreements. Investigate aliases before calling them wrong.
SELECT c.id, c.language, c.name, c.set_id, c.collector_number,
       c.cardmarket_url, p.card_id AS product_owner,
       p.name AS listing_name, p.expansion
FROM pokesingle_recovery_20261003.cards c
JOIN pokesingle_recovery_20261003.cardmarket_products p
  ON p.url = c.cardmarket_url
WHERE p.card_id IS NOT NULL AND p.card_id <> c.id
ORDER BY c.language, c.id;
```

```sql
-- Present in pad but absent from square.
SELECT c.id, c.language, c.name
FROM pokesingle_recovery_20261003.cards c
WHERE EXISTS (
  SELECT 1 FROM pokesingle_recovery_20261003.card_embeddings e
  WHERE e.card_id = c.id AND e.mode = 'pad'
)
AND NOT EXISTS (
  SELECT 1 FROM pokesingle_recovery_20261003.card_embeddings e
  WHERE e.card_id = c.id AND e.mode = 'square'
);
```

```sql
-- Explicit review flags only; null-language/legacy rows need reconciliation too.
SELECT language, mapping_saved, recognition_review_pending,
       metadata->>'status' AS status, count(*)
FROM pokesingle_recovery_20261003.cardmarket_review
GROUP BY language, mapping_saved, recognition_review_pending, metadata->>'status'
ORDER BY language, status;
```

```sql
-- Historical crawl completeness accepts integer and boolean encoding.
SELECT count(*) AS expansions,
       count(*) FILTER (WHERE metadata->>'complete' IN ('1', 'true')) AS complete
FROM pokesingle_recovery_20261003.source_records
WHERE source_table = 'cardmarket_expansion_crawls';
```

Check health without initiating a scan or scrape:

```sh
curl --max-time 20 -fsS https://scan.pokesingle.com/api/v1/health
git status --short --untracked-files=no
```

Do not print container environment listings, connection URLs, proxy credentials, helper tokens or operational user data. Whitelist non-secret configuration fields when checking budgets/proxy availability.

### Prior evidence to preserve

- `/Users/ioannischadjiminas/WebstormProjects/scanapp/data/image-recovery/20261002-official/`: previous discoveries, pending inventory and frozen selections. Its old pending totals are not the latest backlog.
- `/Users/ioannischadjiminas/WebstormProjects/scanapp/docs/official-reference-recovery-20261002.md`: original-source recovery evidence; its historical “local only” status is superseded by the current active import.
- `/Users/ioannischadjiminas/WebstormProjects/scanapp/docs/cardmarket-photo-audit.md`: historical wrong-language/code collision evidence, not current counts.
- `/Users/ioannischadjiminas/WebstormProjects/scanapp/data/latency/staging-ocr-budget028-20261003/`: current 155-photo regression, live timing controls and deployed status.
- `/etc/scanapp-staging/ocr028`: current latency-change rollback material; inventory other release-specific archives before choosing a catalogue rollback.

The final deliverable is a validated catalogue/mapping/artifact snapshot and a review page generated from it, accompanied by two honest lists: **what is completed** and **exactly what remains unresolved**.
