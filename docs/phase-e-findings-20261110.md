# Phase E findings and proposed next steps (2026-11-10)

For review. This records where English and Japanese card coverage stands after the final sealed run,
what is ready for production and what is not, and the open decisions. Nothing here has touched
production.

## Summary

- **Catalogue:** JAREC15 is the final catalogue. 99.2% of English and 98.9% of Japanese cards have an
  image; the rest are display-only.
- **Scanner:** all 16 scanner flags are on in staging and are the code defaults (PRs 115, 116, 117).
- **Final sealed run (972 photos), corrected score:** 95.3% right card first, **0.2% wrong card
  first** (2 photos; upper bound 0.7%). On the 486 never-run photos alone: 0.4% (upper bound 1.5%).
  The 1% wrong-first bar is **met on the corrected score**.
- **Correction:** the first version of this document reported 15 wrong-first (1.5%). After the
  photos were opened, 13 of those 15 turned out to be **my labelling mistakes**: the scanner had
  returned the card that is actually in the photo. See section 2.
- **Per-release gate:** passed (upper bound on wrong-first 0.7%, under 3%; no right → wrong).
- **Production:** not provisioned. The production host has no ScanApp service, credentials,
  release file or data volume, so the switch cannot yet be a single command.

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

- The final catalogue (JAREC15), its 16 flags, and the release file (identical to staging's
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

Both use the same release file (catalogue and 16 flags). The compose files differ on 24 effective
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

1. **The 1% bar** is met on the corrected score. Remaining work, in progress:
   - one tuning round on Modern JA printing order (number-led choice inside a same-art group), and
     the two real errors;
   - a fresh, never-run sealed set of about 500 photos with the stricter label check, run once on
     the tuned candidate. This gives a figure that no correction has touched.
   - If launch cannot wait, shipping the current staging configuration is defensible on the
     corrected score; the fresh sealed run then becomes the first post-launch check.
2. **Production provisioning** (section 4, items 1–4). These are owner actions; after them, the
   switch is one scripted step.
3. **Browser worklist:** the 6 Yellow A images, and replacement scans for the 31 eBay-imaged cards.
   These go into one English image batch, with the usual replay gate.
4. **Clean-up:** drop the unused JAREC16 schema and its staged artifacts on staging.
