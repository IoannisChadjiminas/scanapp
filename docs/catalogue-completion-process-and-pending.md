# Catalogue completion: process and pending work

Verified 2026-10-05 17:20 EEST. This is a status snapshot and continuation guide for the authorized English-first catalogue task. The original requirements remain in [scrape_map_vector_properties.md](/Users/ioannischadjiminas/WebstormProjects/scanapp/scrape_map_vector_properties.md).

## Current result

The live scanner is ready and still serves **PS-CATALOGUE-EN-004-20261004**, schema `pokesingle_completion_20261004d`, on PlanetScale `pokesingle/pokesingle-db/main`. Published work from this task totals **622 primary mapping repairs, 121 new reference images, 243 full-card vectors and 244 artwork regions**, across four activated batches. There are also 205 helper mirrors of existing mappings; these are not 205 additional primary repairs. Paid browser requests recorded by the task: **0**.

These are capability improvements, not fully verified physical printings. The task ledger records **0 fully finished physical-printing cases** because exact finish, stamp, provenance or live-link gates can remain open. Prepared offline work is not included in published totals.

| Live physical catalogue | Rows | Missing references | Missing primary URLs | Unique rows missing either |
|---|---:|---:|---:|---:|
| English | 23,154 | 282 | 1,391 | 1,484 |
| Japanese | 14,706 | 2,583 | 11,620 | 12,459 |

English excludes 2,480 digital Pocket rows without deleting them. Reference and URL queues overlap: 189 English rows lack both; 93 lack only a reference; 1,202 lack only a primary URL. These are catalogue row counts, not a proven deduplicated count of exact physical printings.

The runtime has 48,653 catalogue rows and 39,574 indexed references across languages. The published [review HTML](https://ioannischadjiminas.github.io/cardmarket-version-photos/) remains on the activated release. Its verified SHA-256 is `2cfe52ef980a8f5a79d541783d731192d7a12eb8a71b0035eda7febfaea24d80`. Historical counts in the original plan are not used as current progress.

## Process we follow

1. **Recheck the active state.** Read PlanetScale primary counts and active import, scanner health, published review HTML, saved mappings, image/vector manifests and deployed scraper settings. Start from the durable checkpoint rather than repeating searches.
2. **Reconcile exact identities.** Compare language, set/deck/subset, raw collector number and denominator, emblem, copyright, printing, finish and stamp. A website's `/en/` or `/ja/` interface does not establish the card language. Register verified aliases and keep contradictory rows separate.
3. **Reuse evidence before fetching.** Reuse accepted existing images, archived pages, listing caches and vector/features whose hashes match. Escalate unresolved sources through official sources, appropriate independent archives and exact store/reference pages. Save observed URLs, response outcomes, image hashes and per-card decisions. Never construct an unobserved product URL.
4. **Separate recognition from marketplace verification.** A verified reference can support recognition while the exact Cardmarket product, finish or live access remains pending. A listing photo can confirm marketplace identity without qualifying as an independent original. Third-party provenance and compressed-source limitations remain explicit.
5. **Build offline, in reliable batches.** Freeze approved selection bytes and the active parent. Add pad/square DINOv2 vectors, artwork regions and compatible reference features. Preserve old vector bytes and all unrelated mappings. Keep rejected families and failed evidence in separate queues. Full-card coverage and artwork coverage are tracked separately.
6. **Test before publication.** Verify source hashes, identities, dimensions, finite normalized vectors, unique IDs, expected deltas and unchanged parent fields. Run independent physical-photo queries for every new source/layout family. Replay the frozen controls, including slab, phone, printing and grading cases. No lost correct match or grading change is accepted. Measure a fixed live staging panel before cutover.
7. **Prepare a coherent candidate.** Use a versioned candidate schema/import; load bounded guarded batches and read back counts, manifests, mapping ownership, helpers and digests. Keep candidate activation false until all gates pass. Obtain any exact DDL confirmation required by the write tool.
8. **Preserve and validate rollback.** Retain the previously validated schema/import, pinned API image, configuration and feature/artwork bundles. Check disk headroom and test parent/candidate loading before activation. Keep all older rollback archives.
9. **Publish together.** Activate the tested schema/import and matching artifact paths, verify startup checksums, health, images and the fixed scan panel, then generate/publish the review HTML from that activated import. Persist the correction ledger and checkpoint after each atomic batch.

## Latest candidate and verification

The initial 86-reference candidate failed regression before publication: it lost the existing McDonald's 2016 Pikachu match and changed one grading output. Its full evidence and artifacts remain archived. Its cloud overlay is prohibited from execution.

The revised **54-reference candidate** excludes 32 affected family references and restores their parent bindings. It has **108 new full-card vectors and 108 artwork regions**. Coherent offline integrity checks preserve existing vectors, card fields and mappings. Its 70 guarded SQL statements are prepared and statically checked; **0 have been executed**.

The new replay is complete: **177 photos**, comprising 160 baseline controls, **12/12 eligible independent queries correct**, and five excluded-family queries retained as holds. **0 lost correct matches; 0 grading changes; identity and grading gate passed.** Scanner thresholds and the model were unchanged. This establishes the offline replay gate, not the remaining staging, rollback or publication gates.

| Additional offline family | References | Current verification / hold |
|---|---:|---|
| EX Trainer Kit 2 Minun/Plusle | 15 | Build integrity passed; independent Vulpix 7/12 and Grumpig 3/12 photos 2/2 correct; full regression pending |
| DP Lucario | 9 | Build integrity passed; Quick Ball 10/11 independent photo correct; full regression pending |
| Modern Mew, Gothitelle, Mega Gardevoir ex, Charmeleon | 4 | Build integrity passed; independent physical-photo queries and full regression pending |
| DP Manaphy / SM Raichu | 24 | Build integrity passed; Buizel independent query did not identify the exact printing; family held |
| HGSS Gyarados / Raichu | 59 | Build integrity passed; physical-photo panel 2/3 correct; failed original query retained, family held |

There are **197 distinct offline-built reference candidates**, including rejected or held candidates. This is not an additional completed count. The filtered 54 is a subset of the former 86, so both must not be added together. Source identity review has accepted 226 candidate references; source acceptance alone does not satisfy recognition, provenance, mapping, finish or publication gates.

## What is pending

**Release gates for the 54-reference candidate:** exact `CATALOGUE-EN-CANDIDATE-SCHEMA-005` DDL approval is not recorded; cloud loading/readback, coherent runtime import validation, rollback loading, staging control/latency checks, activation and review publication remain pending. Earlier schema approvals do not approve this exact CREATE request. The SQL is reviewable in [en005-ddl-request.sql](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/en005-ddl-request.sql). Independent offline work can continue while this gate is pending.

**English references:** all 282 missing live references have a per-card durable disposition. The following groups are disjoint and sum to 282.

| Pending group | Rows |
|---|---:|
| Revised candidate passed regression; release gates pending | 54 |
| Failed printing-family / parent-regression holds | 32 |
| Modern references built; independent queries pending | 4 |
| Verified original source still missing | 21 |
| Unown duplicate-reference/alias regression holds | 28 |
| My First Battle unnumbered printing scope pending | 28 |
| My First Battle exact originals missing | 6 |
| Dark Energy independent-query hold | 1 |
| DP Lucario: query passed; full regression pending | 9 |
| Riolu denominator contradiction: visible 6/61 vs expected 6/11 | 1 |
| DP Manaphy / SM: exact-print query hold | 24 |
| EX Minun/Plusle: queries passed; full regression pending | 15 |
| HGSS physical-query family hold | 59 |

The 32-reference hold consists of McDonald's 2015 (12), McDonald's 2024 (15), red Latias deck cards 8–10 (3), and Lycanroc deck cards 16 and 30 (2). Exact card IDs, evidence and reasons for all 282 rows are in [the English reference hold list](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/documentation-20261005/english-reference-holds.md) and [queue v9](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/english-remaining-reference-queue-en005-offline-v9.json).

**English mappings:** 1,391 physical English rows still lack primary URLs. The exact current IDs, names, set IDs and collectors are exported in [english-missing-primary-urls.json](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/documentation-20261005/english-missing-primary-urls.json). Existing mapping evidence must be reconciled with product ownership, language and printing; unresolved source access and finish cases remain separate. This inventory overlaps the reference list and must not be added to 282. A stored URL does not prove fresh live accessibility.

**Japanese:** acquisition/processing has not started in this run. The English gate permits Japanese work once every physical English item is published/validated, explicitly excluded for a supported reason, or assigned a precise unresolved/manual hold. It does not require pretending every hold is solved, and it does not allow calling the English catalogue fully mapped. The next Japanese step after a recorded gate audit is the 50-record pilot, reusing existing user scraper output and official/legacy/deck evidence with language-negative tests.

**Other capability holds:** stamp, finish, live URL access, original-source provenance and unsupported-layout cases remain explicit even when a reference is indexed. The exact-print completion total stays separate from image/mapping totals.

## Budgets and behavior preserved

The latest deployed scraper-settings checkpoint records daily limits of **50 pages / 50 MB**, a 30-page session limit, single browser operation and inactive photo scraping. The historical plan's 1,000-page value is not permission to increase the deployed limit. No services have been purchased.

Offline heavy work stays within the existing Linux/amd64 builder limits of 2 CPUs and 3 GiB per job, with at most two heavy jobs concurrently. Fresh 25-case replay processes avoid the previous memory failure; the old failure logs are retained. Staging hardware is unchanged. Recognition thresholds, grading behavior and the deployed speed030 image remain unchanged by catalogue work.

The latest published rollback parent is `/etc/scanapp-staging/catalogue-rollback/20261004-en004-speed030-parent`. It preserves the previous validated import and compatible speed030 runtime. Older archives must remain. Do not replace the runtime with the older speed029 image during a catalogue rollback.

## Resume and evidence

The authoritative checkpoint is [run.json](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/run.json); evidence is append-only in [events.jsonl](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/events.jsonl). Queue and report files supplement the checkpoint; completed report files can be newer than fields last saved in run.json. This documentation refresh reconciles that lag: the 177-photo replay and four-reference build are complete.

Read the latest checkpoint and queue, recheck the active schema/import and deployed budgets, and resume the next unfinished gate. Do not repeat cached discovery, execute the superseded 86-reference overlay, mark uncertain rows done, or publish prepared-only totals. The immediate independent work is full-regression preparation for the EX15/DP9 cohorts, independent queries for modern4, remaining exact-source research and verified URL reconciliation; publication remains serialized.

Key evidence: [54 replay summary](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/speed030-en005-54-regression-v1/combined-177.summary.json), [54 coherent report](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/en005-54-coherent-v1/report.json), [54 overlay validation](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/en005-54-overlay-v1/validation.json), [EX15 physical-query summary](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/speed030-ex15-pooka-family-queries-v2/regression.summary.json), and [modern4 build report](/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/source-recovery-resume-001/modern4-pooka-offline-pilot-v1/report.json).
