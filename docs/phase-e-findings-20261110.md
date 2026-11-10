# Phase E findings and proposed next steps (2026-11-10)

For review. This records where English and Japanese card coverage stands after the final sealed run,
what is ready for production and what is not, and the open decisions. Nothing here has touched
production.

## Summary

- **Catalogue:** JAREC15 is the final catalogue. 99.2% of English and 98.9% of Japanese cards have an
  image; the rest are display-only.
- **Scanner:** 20 scanner flags are on in staging and are the code defaults: 16 from PRs 115, 116
  and 117, and four footer-evidence rules from the tuning round (PRs 119 and 120). See section 6.
- **Fresh sealed run after tuning (496 photos never run before):** 95.0% right card first
  [92.7, 96.6], **0.6% wrong card first** (3 photos; upper bound 1.8%). The measured rate is under
  the 1% bar; its upper bound is not. No label in this run has been corrected. By their expected
  cards, all 3 wrong-first photos are of two cards whose catalogue reference image is wrong or
  missing. See section 6.
- **Final sealed run (972 photos), corrected score:** 95.3% right card first, **0.2% wrong card
  first** (2 photos; upper bound 0.7%). On the 486 never-run photos alone: 0.4% (upper bound 1.5%).
  The 1% wrong-first bar is **met on the corrected score**.
- **Correction:** the first version of this document reported 15 wrong-first (1.5%). After the
  photos were opened, 13 of those 15 turned out to be **my labelling mistakes**: the scanner had
  returned the card that is actually in the photo. See section 2.
- **Per-release gate:** passed (upper bound on wrong-first 0.7%, under 3%; no right → wrong).
- **Production:** not provisioned. The production host has no ScanApp service, credentials,
  release file or data volume. The release package is on main (`docs/release/phase-e/`): once the
  host is provisioned, the switch is one command and the rollback is one command (section 6).

## 1. Coverage (JAREC15, `pokesingle_completion_20261110_jarec15`)

| | English | Japanese |
|---|---|---|
| Cards in the catalogue | 25,638 (240 sets) | 28,024 (488 sets) |
| Scanned directly (in the scan index) | 25,430 | 23,741 |
| Same-art printing of an indexed card (offered as a printing choice) | 13 | 3,967 |
| No image: display-only, searchable, not scannable | 195 | 316 |
| Share with an image | 99.2% | 98.9% |

- Chinese cards (zh-cn 877, zh-tw 7,436) are in the catalogue but were outside this goal; most have no
  image.
- Coverage is measured against our own catalogue (TCGdex plus the recovered sets). It has not been
  checked against an outside master list of every printed card.

### Known limits

- **316 Japanese cards without an image** (earlier reported as 296; 20 more have a tcgcollector
  source link that never produced an image).
- **195 English cards without an image**, including the 6 Yellow A Alternate cards on the browser
  worklist and TCG Pocket cards, which are digital and cannot be photographed.
- **186 English images below the high-resolution bar.** The Rocket's Sneasel (Best of Game 5) upgrade
  is eye-checked and staged (`data/catalogue-gaps/phase-d/ptcg/bog-5.png`) but was not shipped: the
  card is already imaged at 444 px and the upgrade alone would need a full release cycle.
- **31 English cards whose only image is an eBay listing photo** (McDonald's Collection 2015 and
  trainer kits). Kept by owner decision, since no other source could be fetched and the cards are
  returned correctly: all 31 eye-checked as the right card, and a self-scan of the 31 images led with
  the right card for 30. The 31st is DP Trainer Kit Riolu, a same-art printing choice with Diamond &
  Pearl Riolu 61, with both offered. Replacement scans exist on Bulbapedia, CardTrader and Card Codex
  but need a browser, so they are on the browser worklist.

## 2. Final sealed run (the one run on the final half)

Setup: JAREC15 + 16 flags, main `fb7316c`, 972 photos (486 never run, 486 run in earlier rounds).
Logged in `sealed/runs.log` before any result was read. The photos were not looked at.

### As first reported (before the labels were checked)

912 right first (93.8%), 15 wrong first (1.5%), all 15 in the never-run half (3.1% there).

### What the 15 were

After the run the half was retired to the development set, so the photos could be opened. All 60
photos that were not right-first were checked against the photo itself (number, set mark, slab
label):

- **13 of the 15 wrong-first were label mistakes.** The scanner returned the card in the photo; the
  label was wrong. Examples: a card reading 16/64 with the Jungle mark labelled as Base Set 2; POP
  Series 5 cards labelled POP Series 1; Japanese secret rares 070/066 and 070/069 labelled as
  number 009; four old Japanese promos labelled with the Pokédex number ("No. 150", PSA "#025")
  instead of the promo.
- **2 are real scanner errors**, both Modern JA: Blastoise EX XY1 014/060 returned as the stamped
  promo of the same art (status uncertain), and Meloetta SM10a 027/054 returned as an unrelated
  promo.
- 2 more labels were wrong among the other rows (one offered, one retake); they do not change the
  wrong-first count.

**Cause (mine):** labels come from eBay listing titles. The title parser read some numbers wrongly,
and my eye check of the 486 new labels passed them. The next sealed set uses a stricter check: the
number strip and set mark are read at full size for every photo, and a promo number is never taken
from a dex number.

**How far to trust the correction:** it was made after the results were read, and only the misses
were all checked. As a balance, 48 right-first never-run photos were drawn at random (6 per cell)
and checked the same way: 48 of 48 labels were right. Labels and scanner are independent (titles
versus image), so a wrong label on a right-first photo would need both to make the same mistake.
The corrections are recorded in `sealed/runs.log`.

### Corrected score

| Part | Photos | Right card first (95% interval) | Wrong card first (95% interval) |
|---|---|---|---|
| Never run before | 486 | 94.2% [91.8, 96.0] | 2, 0.4% [0.1, 1.5] |
| Run in earlier rounds | 486 | 96.3% [94.2, 97.6] | 0, 0.0% [0, 0.8] |
| **All** | **972** | **95.3% [93.7, 96.4]** | **2, 0.2% [0.1, 0.7]** |

Per cell, all 972:

| Cell | Photos | Right card first | Wrong card first |
|---|---|---|---|
| Modern EN | 141 | 97.2% | 0 |
| Modern JA | 117 | 86.3% | 2 (1.7%) |
| Numbered older EN | 135 | 99.3% | 0 |
| Numbered older JA | 126 | 98.4% | 0 |
| Promo EN | 137 | 96.4% | 0 |
| Promo JA | 121 | 95.0% | 0 |
| Unnumbered vintage EN | 100 | 97.0% | 0 |
| Unnumbered vintage JA | 95 | 90.5% | 0 |

**The 1% bar:** 2 wrong-first out of 972 is 0.2%, upper bound 0.7%. On the never-run half alone it
is 0.4%, upper bound 1.5% (486 photos are too few to put the upper bound under 1%).

**Weakest cell:** Modern JA, 81.8% right first on never-run photos. Of its 12 other misses, 9 show
the same thing: the number and set mark are legible, the right card is offered, but a reprint with
the same art is listed first. That is a printing-order problem, not a wrong card, and it is what
the tuning round is working on. Unnumbered vintage JA (84.6% on 26 never-run photos) is the known
vending / quick-starter same-art choice.

**Tuning signal:** the never-run half is 2 points lower on right-first than the reused half
(94.2% against 96.3%). The reused photos still flatter the scanner a little, but far less than the
first score suggested.

## 3. What happened today

- Sealed run 4 (585 photos) passed the per-release gate. The five new scanner flags were switched on
  in staging, with a rollback file, and made the code defaults (PRs 116 and 117).
- The sealed half grew to 972: 99 photos used in earlier rounds were moved to the development half
  (chosen at random from the two over-full vintage cells), so that half the photos are never-run.
- The phone index was exported from JAREC15 and published on staging. The server's manifest check
  passes (catalogue, model, vector and ID hashes match the loaded snapshot).
- Rollback was rehearsed on staging. **Found and fixed:** once a flag is on in code, removing it from
  the release file no longer turns it off. The staging rollback file now sets the five flags to
  `false` explicitly, and a second rehearsal confirmed they resolve off, then on again. Rollback and
  forward each take about 1.5 minutes, with health ok and 0 restarts.
- A JAREC16 that made the 31 eBay-imaged cards display-only was built and then dropped after the
  owner decision. Its schema exists unused (`pokesingle_completion_20261110_jarec16`). It also
  failed to load in a replay ("Invalid immutable retrieval segment lineage"): removing cards from
  the middle of the scan index needs more than the builder does.

## 4. Production readiness

### Ready

- The final catalogue (JAREC15), its flags (20 since the tuning round, section 6), and the release
  file (identical to staging's
  `/etc/scanapp-staging/catalogue-release.env`).
- A rollback file pattern that sets every flag explicitly, rehearsed on staging.
- Phone index version `63a3707111add1d751949858766dd479d60d7f248367a389173f110d3842bbdf` for
  JAREC15 (51,431 rows).
- An artifact allowlist with checksums, computed on staging. Total ~12.6 GB: models, reference
  features `20261109-ja-recovery-img6`, artwork `20261110-ja-recovery-vec15`, reference images, and
  the phone index.

### Not ready: needs the owner

Read-only check of `auctaro-prod` on 2026-11-10: no `/etc/scanapp-production/`, no ScanApp
container. The host has 4 GB RAM with about 1.3 GB available; staging's API uses about 0.9 GB idle,
with a 3 GB limit.

1. Decide host capacity: resize, or accept the risk of running a 3 GB-limit API next to the
   existing services.
2. Create the ScanApp production Compose service in Dokploy (`compose.dokploy.production.yaml`) and
   give Dokploy access to the repository.
3. Create a read-only production catalogue role and put it in
   `/etc/scanapp-production/planetscale.env`. Set `PORTFOLIO_DATABASE_URL` and
   `SCANAPP_SERVICE_TOKEN` (`docs/production-single-server.md`).
4. DNS/HTTPS for `scan-prod.pokesingle.com`.

Once those exist, the remaining steps are mechanical and can be scripted:

- copy the allowlisted artifacts from staging to the production volume, then verify their checksums;
- install the release file, start, check health;
- publish the phone index if `CARD_INDEX_PUBLISH` is turned on in production.

### Staging and production config differences (effective values)

Both use the same release file (catalogue and flags; 20 flags since section 6). The compose files differ on 24 effective
settings. Most of the difference is the phone stage-1 fast path and client features, which staging
has on and production's compose leaves off. That was an earlier rollout choice: turn them on one at a
time. The sealed runs measure the server path, which is the same in both.

| Setting | Staging | Production |
|---|---|---|
| `STAGE1_BACKGROUND_CHECK`, `STAGE1_EARLY_EXIT`, `STAGE1_SET_TOTALS`, `STAGE1_PROMO_NUMBERS`, `STAGE1_PRINTING_GROUPS`, `STAGE1_NORMALIZE_DUPLICATES`, `STAGE1_DIAGNOSTICS`, `STAGE1_FAMILY_VECTOR`, `STAGE1_TWIN_GUARD` | on | off |
| `STAGE1B_SERVER_FRAME`, `STAGE1B_TEXT_VERIFY`, `STAGE1B_FRAME_FALLBACK` | on | off |
| `APP_CLIENT_EMBEDDING`, `APP_CLIENT_LABEL`, `APP_CLIENT_QUALITY` | on | off |
| `APP_SLAB_DETECTION` | off | on |
| `GRADING_REQUIRES_CLIENT_HINT` | off | on |
| `CARD_INDEX_PUBLISH` | on | off |
| `STORE_CAPTURES` | on | off |
| `PRICE_GUIDE_ENABLED`, `TCGDEX_PRICES_ENABLED` | on | off |
| `SCAN_WAIT_LIMIT` | 6 | 2 |
| `PORTFOLIO_DATABASE_URL`, `SCANAPP_SERVICE_TOKEN` | not used | required |

### AGENTS.md check

- Only TCGdex art is mirrored to the CDN. The 68 English cards whose image is a Cardmarket product
  photo keep their own URL and are not mirrored, as `docs/card-image-cdn.md` allows.
- `image_url` stays with the catalogue API, and the TCGdex path layout (`high.webp`/`low.webp`) is
  unchanged.
- No credentials or photos in git.

## 5. Proposed next steps (for decision)

1. **The 1% bar.** The tuning round and the fresh sealed run are done (section 6). The measured
   wrong-first rate is 0.6% on photos no correction has touched; the upper bound is 1.8%. To bring
   the upper bound under 1%:
   - fix the two catalogue image gaps behind the 3 wrong-first photos (`ja:XYP-050`, whose
     reference is a card back, and `ja:jr-vending-machine-series-3-green-u21`, which has no
     reference), as one Japanese image batch with the usual replay gate;
   - then one more never-run sealed set of about 500 photos. With none wrong, 493 photos give an
     upper bound of 0.8%. The 496-photo set is spent for this release and cannot be reused.
   - If launch cannot wait, shipping the current staging configuration is defensible: every
     per-release gate passed and the measured rate is under 1%.
2. **Production provisioning** (section 4, items 1–4). These are owner actions; after them, the
   switch is the one `apply` command in `docs/release/phase-e/README.md`.
3. **Browser worklist:** the 6 Yellow A images, and replacement scans for the 31 eBay-imaged cards.
   These go into one English image batch, with the usual replay gate.
4. **Clean-up:** the unused JAREC16 schema was dropped on the owner's instruction (15:03Z; staging
   unaffected). Its two artifact folders on staging's data volume (4.7 GB) are still there.
5. **Phone fast matching for Japanese cards** (section 7): review pokesingle PR 284, then collect a
   Japanese phone panel so its two switches can be gated.

## 6. Tuning round, the fresh sealed run and the release package (added later on 2026-11-10)

### The four rules

All four read the collector line at the foot of the card (`api/app/recognition/footer_evidence.py`,
PR 119). Each has its own flag.

| Flag | What it does |
|---|---|
| `PRINTING_EXACT_FRACTION` | One clean fraction that contradicts the shown card shows the single same-title card with that number and printed total. The photo stays a printing review. |
| `PRINTING_BARE_NUMBER` | Inside a same-art group, one very confident bare number of three or more digits that is exactly one member's number shows that member first. |
| `OCR_SET_CODE_READ` | A set code read beside a fraction that confirms the set's total (`SM10a` beside `027/054`) is not taken as a collector number. |
| `RETRY_OWN_LANGUAGE` | A second read that was rejected only over language is kept when its own language and a clean fraction confirm the card. The result stays a review. |

### Gate before staging (1,891 photos, candidate against staging)

| Panel | Photos | Right first | Wrong first (95% upper bound) | Right → wrong |
|---|---|---|---|---|
| Development set | 681 | 636 → 637 (93.5% [91.4, 95.2]) | 4 → 4 (1.5%) | 0 |
| Development set 2 | 238 | 232 → 232 (97.5% [94.6, 98.8]) | 0 → 0 (1.6%) | 0 |
| Retired sealed half | 972 | 926 → 938 (96.5% [95.2, 97.5]) | 2 → 0 (0.4%) | 0 |

13 photos changed, all to the right card first. No cell lower. The rules were written from the
retired sealed half, so its figures are in-sample.

### The fresh sealed run (496 photos, run once, logged before reading)

These photos were collected and labelled after the labelling mistakes of section 2, with the
stricter label check, and had never been run. Nobody has looked at them since.

| Cell | Photos | Right first, staging side | Right first, tuned | Wrong first (both sides) |
|---|---|---|---|---|
| Modern English | 73 | 67, 91.8% [83.2, 96.2] | 68, 93.2% [84.9, 97.0] | 0 [0.0, 5.0] |
| Modern Japanese | 81 | 77, 95.1% [88.0, 98.1] | 78, 96.3% [89.7, 98.7] | 0 [0.0, 4.5] |
| Numbered older English | 65 | 65, 100% [94.4, 100] | 65, 100% [94.4, 100] | 0 [0.0, 5.6] |
| Numbered older Japanese | 60 | 59, 98.3% [91.1, 99.7] | 59, 98.3% [91.1, 99.7] | 0 [0.0, 6.0] |
| Promo English | 50 | 50, 100% [92.9, 100] | 50, 100% [92.9, 100] | 0 [0.0, 7.1] |
| Promo Japanese | 62 | 57, 91.9% [82.5, 96.5] | 58, 93.5% [84.6, 97.5] | 1, 1.6% [0.3, 8.6] |
| Unnumbered vintage English | 35 | 35, 100% [90.1, 100] | 35, 100% [90.1, 100] | 0 [0.0, 9.9] |
| Unnumbered vintage Japanese | 70 | 58, 82.9% [72.4, 89.9] | 58, 82.9% [72.4, 89.9] | 2, 2.9% [0.8, 9.8] |
| All | 496 | 468, 94.4% [92.0, 96.1] | 471, 95.0% [92.7, 96.6] | 3, 0.6% [0.2, 1.8] |

- **Per-release gate: passed.** No right → wrong, no cell lower, wrong-first upper bound 1.8%.
- 3 photos changed, all to the right card first. Tuned, the right card is first or offered on 490
  of 496; 3 photos get no answer.
- **1% bar:** measured rate 0.6%, under the bar; upper bound 1.8%, over it. The shortfall is one
  of: 429 more photos at 3 wrong (925 in all), or the two catalogue gaps fixed and a new set.
- The 3 wrong-first photos are identical on both sides. By their expected cards: 1 on `ja:XYP-050`
  (reference image is a card back) and 2 on `ja:jr-vending-machine-series-3-green-u21` (no
  reference image). Identified from the labels; the photos were not opened.
- The gain is smaller here than on the retired half (+0.6 points against +1.2), as expected for
  rules written from the retired half.
- Weakest cell: unnumbered vintage Japanese, 82.9% right first, with the right card offered on 9
  more of its 70 photos.
- Short of plan in two cells: unnumbered vintage English 35 of 44 photos, promo Japanese 62 of 70.

### Staging

- Switch `flags20-20261110`, 13:30Z to 13:33Z, made with `scripts/catalogue-release-switch.sh`
  (its first real run): preflight including the checksums of 112,478 artifact files, health ok,
  0 restarts, all 20 flags match. Rollback file
  `/etc/scanapp-staging/catalogue-rollback/flags20-20261110/catalogue-release.env.rollback`.
- The four flags became code defaults in PR 120 (`e06982b`). Staging runs that commit (checked
  14:44Z): healthy, 0 restarts, same import id, release file unchanged.

### Release package (on main, `docs/release/phase-e/`)

- `catalogue-release.env`: the release (schema, import id, artifact directories, 20 flags). No
  secrets.
- `README.md`: the one `apply` command, the one `rollback` command, the preflight checklist, the
  staging and production configuration table (verified against both compose files; it replaces
  the table in section 4, which was less exact), the phone index version and the artifact
  manifest's location and checksum.
- `RESULTS.md`: the gate and the sealed run per cell.
- `scripts/catalogue-release-switch.sh`: writes the rollback file before changing anything and
  rolls back by itself if health or any flag does not match.

## 7. Phone fast matching (the app, not this repository)

The phone shows a provisional card before the server answers. A read-only review of the app found
why Japanese cards rarely get one:

- 10,277 of the 23,741 Japanese rows in the phone index carry an English-only name, and the phone
  compares the Japanese name it reads as plain text. The server's full pipeline bridges this with
  its species table; the phone did not.
- The phone took some Japanese set codes as promo numbers (`SM8b 027/150` read as `SM88`).
- Not addressed: the phone does not read `NNN/DP-P`-style or bare promo numbers, and the 4,283
  Japanese same-art printings without a vector of their own are not in the phone index.

pokesingle PR 284 adds both fixes behind switches that are off by default
(`PHONE_JA_SPECIES_NAMES`, `CARD_SET_CODE_GUARD`). Its unit tests pass. **The phone panel replay
was not run:** the frozen 157-photo panel's phone inputs are not on the development machine, and
that panel has no Japanese text reads, so it cannot test the names change. The switches stay off
until a panel with Japanese cards read on a real phone shows zero wrong phone answers. A phone
miss costs speed only: the server's answer always replaces the phone's.

## 8. Open catalogue issues found while labelling

None blocks the release; each is a wrong or missing reference, a count, or a card not in the
catalogue.

- **Wrong or missing reference image:** `ja:XYP-050` (card back); `ja:jr-miscellaneous-promos-068`
  (an English Pikachu); `ja:M-P-168` (none); `ja:DP3-062` Corsola (different art); `ja:L1HG-41`
  (the holo version); vending series 1 `u19` and `u20`, series 3 `u21` and `u14`, and
  `ja:jr-yamabuki-city-gym-deck-u15` (none); `en:pop4-2`, `en:pop4-9`, `en:pop5-2`, `en:basep-36`
  (none).
- **Cards not in the catalogue (Japanese):** neo1 Meganium LV.54; Shibuya's Pikachu 002/S-P;
  Pikachu 291/SV-P; Rescue Team DX's Pikachu 036/S-P; Hama-chan's Slowking; Southern Islands Onix;
  Venusaur LV.64 (GB); the Mewtwo LV.67 contest card; the e-Card starter deck (Moo-Moo Milk
  029/029); World Champions Pack (Pichu 030/108); ADV Wigglytuff ex 058/083; a DP half-deck
  stadium 014/014; PCG deck Tyranitar ex δ 004/024; SMP2 (Detective Pikachu 014/024); the svHK
  deck (Switch Cart 018/053).
- **Cards not in the catalogue (English):** the 30th-anniversary Shining Celebi reprint (106/105).
- **Numbers and totals:** L2 and L3 recorded as 70 while the cards print /080; SM7a 50 against
  /060; SM10b 56 against /054; DP1–DP3 numbers are roster numbers while the cards print
  `DPBP#NNN`; Zekrom prints `BW005` while the id is `en:bwp-BW05`.
- **Data shape:** mixed id styles in L1HG and L1SS; text notes in `twins` fields; SV4a's set name
  shown as レイジングサーフ; the "pop1" candidate pool mixes POP Series 1, 2, 4 and 5.
