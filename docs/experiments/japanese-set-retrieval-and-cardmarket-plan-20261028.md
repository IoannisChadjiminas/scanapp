# Japanese catalogue recovery and Cardmarket linking plan — 2026-10-28

**Execution handoff (updated 2026-10-29):** Follow [the agent handoff](japanese-set-recovery-agent-handoff-20261029.md) for the owner-selected combined release, scraper readiness, checkpoints and the global images/links-before-vectors milestone. This document remains the detailed source/mapping reference.

Status: implementation plan; no catalogue or runtime changes are authorized by this document alone.

**Routing checkpoint, 2026-10-29:** See [the routing update](japanese-set-routing-update-20261029.md). The master index yielded 800 observed links: 276 collection targets, 59 held shared/combined/pool cases, and one unresolved Creatures Deck route. These counts describe source routing, not card completeness. Fetch each provider listing once and reconcile group membership separately.

## Objective and scope

**Execution-location decision, 2026-10-29:** Run acquisition natively on the owner’s
Mac with visible local Chrome and a dedicated persistent profile. Reuse/adapt the
existing scraper locally; do not use or deploy the staging scraper for collection.
The owner handles Cloudflare checkboxes in that same local browser window. Follow
the newer execution handoff for macOS launch options and manual-wait behavior.
Target-compatible Linux/x86 recognition features are a later offline build step.


Recover missing Japanese printings with accurate identities, reference images,
recognition assets and their corresponding Cardmarket singles pages. Preserve
existing card IDs, holdings, verified mappings and recognition behavior.

The [set audit](japanese-set-completeness-audit-20261028.md) found 281 absent
checklist groups and 55 present groups below reference count. These include
expansions, decks, promos, energy pools and overlapping bundles. First convert
checklist entries into a deduplicated printing inventory; never treat the group
counts or row-count differences as a final number of new cards.

Start from the current validated cloud release, presently
`PS-CATALOGUE-EN-JA-NEO2057-20261028`, and capture its digests, image/artifact
manifests and phone index. Recheck the actual active release before building;
never assume the baseline has not moved while sources are being gathered.

## Delivery order

| Stage | Scope | Initial checklist entries | Completion output |
|---|---|---:|---|
| 0 | Normalize all 281 absent / 55 potentially incomplete groups | Reconcile first | One printing ledger with aliases, source coverage and verified gaps |
| 1 | MBG Gengar and MBD Diancie pilot | 44 numbered entries | Validate source collection and Cardmarket mapping; retain for the combined release |
| 2 | Remaining six Mega-era products | 173 | Verified inventory for the combined release |
| 3 | Twenty Scarlet & Violet-era products | 871 | Same source/link gates; review chunks feed the combined release |
| 4 | The 55 potentially incomplete groups | Unknown until card reconciliation | Exact missing-print list; fill verified gaps only |
| 5 | Remaining 253 absent groups | Includes old promos, decks and energies | Era-by-era recovery with explicit unresolved cases |

The first 28 modern groups total 1,088 reference entries before deduplication,
unnumbered energy reconciliation and variant checks. This is not 1,088 guaranteed
new catalogue rows. MBG/MBD checklist counts are 22 each, while marketplace and
official searches also list their unnumbered basic energies. Include those
products explicitly in reconciliation; a deck's 60 physical cards are quantities,
not 60 distinct catalogue printings.

Owner decision, 2026-10-29: collect the whole scope first, then generate all
verified vectors/features in one bulk job and assemble one combined catalogue,
artifact package and phone index. Internal review/compute chunks are checkpoints,
not separate releases. Use subsets only to isolate regression failures.
Reprints with the same code/number across sub-decks must not become duplicate IDs.

## 1. Establish the printing inventory

For each reference group, record the official product/checklist, release date,
era, Japanese name, printed set code, collector number, printed total, rarity,
artwork/finish/edition/stamp distinctions and source card IDs. Resolve code
aliases using era and product identity: SC and MP are reused; display names alone
are not global keys. Match existing cards and all recovery prefixes before
proposing a new row. Keep group-to-card relationships separately from card identity.

Prefer the official Pokémon Japanese card database for modern cards. Its search
responses enumerate source card IDs and image paths; card details establish the
printed fraction, name and product. Cross-check against TCG Collector's checklist.
For older cards outside official coverage, cross-check independent specialist
checklists and existing recovered data. TCGdex is useful where populated, but is
not the complete baseline and its code/third-party mappings are not proof alone.

Keep printed totals independent of checklist length. For example MBG 003/021 has
a printed total of 21 even though its numbered checklist includes 022/021.
Do not fabricate numeric fractions for unnumbered energies or vintage cards.
Assign stable IDs consistent with existing conventions; MBG 003 is proposed as
`ja:MBG-003`. Confirm unnumbered card naming against the existing schema first.

Deliverables: `set-registry.json`, `printing-inventory.jsonl`, `existing-matches.jsonl`,
and an exact `new-or-incomplete-printings.jsonl`. Each proposal needs source evidence.

## 2. Retrieve and verify images

Prefer the official front image for the exact Japanese printing. Use an existing
cached source or a clean specialist scan only when the official source is absent
or unusable. Preserve original bytes and provenance: source page/image URL,
retrieval time, dimensions, SHA-256, source card ID and visual review decision.
Reject wrong language, wrong number/artwork/stamp, back images, watermarks over
the card, severe clipping and unreadable references. Do not synthesize references
or use an English reprint as the Japanese display image.

Store a durable local copy and test the API image route. External display URLs can
fail even when an image was retrieved successfully. Use the existing stored-image
fallback where necessary. Produce paired review sheets for uncertain printings.

Deliverables: immutable original images, `image-manifest.jsonl`, and review decisions.

## 3. Resolve Cardmarket URLs and product IDs

### Verified starting points

- [MBG singles](https://www.cardmarket.com/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Gengar-ex)
- [Mega Gengar ex, mBG 003](https://www.cardmarket.com/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Gengar-ex/Mega-Gengar-ex-mBG003)
- [MBD expansion](https://www.cardmarket.com/en/Pokemon/Expansions/MEGA-Starter-Set-Mega-Diancie-ex)
- [Mega Diancie ex, mBD 005](https://www.cardmarket.com/en/Pokemon/Products/Singles/MEGA-Starter-Set-Mega-Diancie-ex/Mega-Diancie-ex-mBD005)

These specific pages were found in Cardmarket search results during planning;
archive current product-page evidence and capture their numeric IDs before final
mapping approval. A set page is a discovery source, not a card's final URL.
The `/en/` URL component is the website language, not proof of the card language.
Use the Japanese-product printing and source image/code, not the English reprint.

### Acquisition and matching sequence

1. Reuse existing cloud `cardmarket_products`, helper mappings and prior verified
   source caches where they cover the exact new product. Never relink an existing
   owner merely to obtain a URL for a new card.
2. Download Cardmarket's official public Pokémon singles product catalogue once
   and cache it. The current file was checked on 2026-10-28: version 1, 75,066
   products, fields `idProduct`, `name`, `idCategory`, `categoryName`,
   `idExpansion`, `idMetacard`, `dateAdded`. **It has no canonical URL, printed
   card number or expansion-name field.** Use it for ID cross-checks and joins,
   not as a complete exact-print matcher.
3. Build an explicit set-registry mapping from Japanese product/code/era to the
   observed Cardmarket expansion and `idExpansion`. Enumerate that expansion's
   singles pages and capture actual product URLs, displayed names/codes/numbers,
   numeric product IDs and relevant variant/image evidence. Reuse the logic in
   the prior `read_cm_sets.py` / `read_cm_ids.py` workflow, with new inputs and
   persisted progress. Do not rerun its hard-coded historical import scripts.
4. Require agreement on Japanese product identity, set/deck, full number including
   suffixes, translated species/trainer name, and artwork/edition/finish/stamp
   where relevant. Transliteration/name normalization proposes candidates; it
   cannot approve a link by itself. Neither artwork similarity nor a shared
   `idMetacard`/third-party ID proves the same printing.
5. Save the actual canonical singles URL; never construct a slug from a name or
   guess V1/V2/V3. Reject sealed decks, expansion landing pages, search-result URLs,
   invalid-product responses and redirects to another printing as final mappings.
   Check for URL/product-ID ownership conflicts across the entire catalogue.
6. Keep several real variants as separate reviewed listing choices where the
   existing model supports them. Do not assign one arbitrary version as confirmed
   foil/edition. A stock count or the absence of offers is not proof of no product.
7. Record one outcome per printing: `verified`, `ambiguous`, `not_found`,
   `not_listed_confirmed`, or `blocked_source`. Only verified mappings may set
   `cardmarket_verified`. Not found/blocked are not the same as not listed.
   Keep the exact URL null when unverified; any search link must remain explicitly
   a search link and must not be used for price identity.
8. Join verified numeric product IDs to the existing Cardmarket price-guide
   importer. Confirm the Japanese product and finish; leave absent prices null.
   A correct URL can exist without a usable price-guide observation.

Direct Cardmarket page requests sometimes return 403. Prefer cached public data,
then the local visible-browser listing/page workflow with conservative pacing and resume
state. On a Cloudflare checkbox, pause Cardmarket work, preserve the challenged
browser session, show the owner that exact session and wait for them to manually
tick it. Disable automatic checkbox clicking for this collection mode. Resume
only after owner confirmation and verification that the same session now shows
the expected content. See the execution handoff for watchdog/session handling;
do not treat a blocked request as proof of absence.

Mapping evidence ledger fields: proposed catalogue ID, source product/card ID,
Cardmarket expansion ID, product ID, actual URL, displayed code/number/name,
finish/edition information, image comparison result, source page/capture time,
verification state, reason and any existing URL owner. Retain the evidence behind
every accepted or held decision. Public source caches stay outside tracked code.

Deliverables: `cardmarket-products.jsonl`, `proposed-mappings.jsonl`,
`verified-mappings.jsonl`, `held-mappings.jsonl`, and a human-readable review page.
Card retrieval and marketplace linking have separate progress counts.

## 4. Build additive catalogue and recognition candidates

Reuse existing loaders and release checks. The current
`api/scripts/build_cloud_reference_recovery.py` is restricted to one existing
row without an image; it cannot directly add whole new sets. Extend or introduce
a tested batch builder with explicit new-row proposals and no implicit live writes.

Build from the active cloud snapshot and preserve old row/vector bytes and the
existing retrieval segments. Include card rows, matching marketplace product/helper
rows, provenance, set totals, image paths, FTS and operational totals. Update all
catalogue/vector/artwork digests and release manifests together. Apply explicit
schema-column selection; do not depend on arbitrary export column order.

Use the unchanged DINO model and preprocessing. Generate new full-card vectors,
artwork records and native x86 reference features using the staging OpenCV contract.
Review close same-language artwork/reprints against the existing curation. Some
new catalogue printings should be manual printing choices rather than independent
picture vectors; document and verify how those choices can be reached. Never
reintroduce the 326 deliberate vector exclusions wholesale.

Clone a new inactive schema. Append artwork row indexes after the actual maximum,
not the row count: the live table has gaps. Preserve old IDs, data/grants and
asset manifests; replace a hardlinked manifest by a new inode before editing it.
The publisher must reject a changed parent digest or an already existing target.
Keep database credentials private and use the established authorized publisher.

Build the paired phone index from this exact candidate and the same model;
verify existing phone vectors/IDs/metadata remain preserved where the format
permits. Do not mix an old operational catalogue/FTS or empty set totals into the
candidate replay as happened in the first rejected Ruin Wall comparison.

## 5. Review and regression gates

- Every proposed printing is reconciled with its checklist; every scannable
  reference has a valid stored image and the expected vector/native artifacts.
  Missing or intentionally excluded vectors are explicit, not silently omitted.
- Every accepted Cardmarket mapping has exact-print evidence and no unexplained
  ownership collision. Publish verified URLs only. Report unresolved/not-listed
  cards honestly; do not promise marketplace coverage where no product is proven.
- Parent catalogue rows/mappings, vectors and artifact bytes remain unchanged
  except explicitly reviewed corrections. Normal cloud and native loaders pass.
- Relevant API/card/number/marketplace/confirmation tests and the full API suite pass.
- Run paired full-scanner replays on the existing photo panel plus all new labelled
  cases: the user's three Gengar photos, both Exeggutor photos, vintage Charizard,
  Ruin Wall/Kabuto, English/Japanese/PCG/vintage panels and negatives. Do not run
  another heavy scanner inside the live API worker. Compare against a frozen,
  correctly paired baseline from the current active release.
- No previously correct first result may become wrong. No new wrong automatic
  matches or unrelated printing choices. Review every changed result, including
  new choices, and record intended improvements separately from regressions.
- Cached phone-vector parity, compressed-index behavior, manifest/checksum/range
  checks and representative regular-app scans on Android/iOS must pass.

Adding MBG should let its exact Japanese printing enter retrieval. The unrelated
Charizard-suggestion defect is a **separate recognition fix**, behind its own
switch. Test name/structured-number conflicts, unknown cards and genuine reprints;
run the stored-scan replay for any ranking/printing rule change and the full photo
panel. Do not conceal that defect by merely adding one Gengar reference or weaken
all number/identity guards in the catalogue-import release.

## 6. Publish the combined reviewed release and retain rollback

Prepare a sealed release package: inactive schema/import selectors, immutable
images/features/artwork, phone index, checksums, exact SQL and rollback settings.
Obtain the normal owner authorization for that concrete release. Verify the inactive
cloud snapshot in a separate resource-limited read-only container first.

With activation authorization, select the new schema and artifact paths atomically,
recreate only the API with its retained image, require public readiness and exact
image delivery, then atomically select the matching phone index. Verify public
manifest, full-file checksums, Range 206 and ETags. Keep previous release files,
image, schemas and phone versions. No production activation is included.

On both normal phone apps, verify index update, new-card scans, correct choice/save
and existing cards/background checks. Keep integration tests on an emulator with
`--no-uninstall`; do not uninstall either physical phone app.

## Progress reporting and next concrete step

The global run reports: distinct proposed/recovered printings; missing images; independent
vectors versus review-only printings; verified Cardmarket links; ambiguous/not-found/
not-listed/blocked mappings; prices available; photo/phone regression outcomes; and
activation state. Never replace these with a single “all cards complete” count.

First implementation task: reconcile the complete MBG/MBD inventories (including
unnumbered energies), retrieve the original Japanese images, and produce a reviewed
card-to-Cardmarket mapping pack, then finish the remaining acquisition queue.
After acquisition is reconciled, build one combined inactive release. Source
acquisition and planning do not activate anything.

## Sources checked and existing implementation references

- [Official Japanese MBG/MBD products](https://www.pokemon-card.com/products/mega/mb.html)
- [Official MBG Gengar card](https://www.pokemon-card.com/card-search/details.php/card/48264/regu/all)
- [Japanese checklist reference](https://www.tcgcollector.com/sets/jp)
- [Official Cardmarket singles product file](https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json)
- [Cardmarket Japanese/Western product guidance](https://help.cardmarket.com/en/finding-and-listing-pokemon-cards)
- `api/scripts/on_phone_index/README.md`
- `docs/experiments/neo2-057-reference-20261028.md`
- `docs/cardmarket-photo-audit.md`
- `data/catalogue-gaps/tcgdex-empty-sets-20261017/read_cm_sets.py` and `read_cm_ids.py`
- `scripts/build_manual_cardmarket_review.py`, `api/app/cardmarket.py`, `api/app/price_sources.py`
