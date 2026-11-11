# Second batch: plan for an agent (2026-11-11)

This is a work order for an agent that starts with no memory of the earlier work. It says what
has been done, what is still open, and how to add the cards that the outside-list check found
missing. Read it to the end before running anything.

The end state is **production-ready, not production**. Nothing here switches production.

## 1. Where things stand

### Done

| What | Result | Record |
|---|---|---|
| English and Japanese coverage work | Catalogue release JAREC15, 20 scanner flags on in staging and as code defaults | `docs/phase-e-findings-20261110.md` |
| Step 1 of the remaining-cards plan: data-only fixes | Release `PS-CATALOGUE-EN-JA-REC18-20261111`, schema `pokesingle_completion_20261111_jarec18`, 345 rows changed, no image touched. Replay of 1,891 photos: 0 right → wrong | `docs/data-fixes-step1-20261111.md` |
| Phone fast-match rules (the app repository, not this one) | Ten rules on by default in Android builds, the Japanese reader off, iPhone unchanged | The app's own pull request and `docs/phone-fast-rules-2026-11-10.md` there |
| Step 6: check against outside lists | 2 English sets and 11 Japanese products missing, plus single cards; about 160 English and 665 Japanese cards | `docs/outside-list-check-20261111.md`, rows in `docs/outside-list-missing-rows-20261111.json` |

### Staging right now

- Catalogue: JAREC18 (`PS-CATALOGUE-EN-JA-REC18-20261111`). Code: main at `d62ddfb`. 20 flags, unchanged.
- Catalogue size: English 240 sets / 25,638 cards; Japanese 488 sets / 28,024 cards.
- Rollback folder of the last switch, on the staging host:
  `/etc/scanapp-staging/catalogue-rollback/jarec18-data-fixes-20261111`.
- Production: untouched.

### Still open

Step numbers are those of `docs/remaining-cards-plan-20261111.md`.

| Step | What | Cards | Needs the owner? |
|---|---|---|---|
| 2 | One browser sitting: 6 Yellow A Alternate, 31 eBay replacements, 20 tiny TCG Collector images, 14 wrong or missing references, 16 cards not in the catalogue | about 90 pages | Yes: their Chrome, signed in to Cardmarket |
| 3 | English image release from step 2 | 42 | After step 2 |
| 4 | Japanese image release from step 2, then one fresh sealed set of about 500 photos | 45 + step 5 | After step 2 |
| 5 | Japanese tail: cards with no image anywhere | 296 | Route 4 (photos from users) is an owner decision |
| **6b** | **The second batch: this document** | **about 825** | **No** |
| 7 | TCG Pocket: wait for TCGdex to publish the art | 161 | Decision: searchable-only or left out |

Questions already put to the owner, none of which blocks the second batch: the browser sitting;
TCG Pocket cards searchable-only or left out; photos from users with consent or not.

Owner-side items outside this plan: a camera test of the Android build; production
provisioning and the single `apply` command; the decision on the Japanese reader; their word on
deleting the JAREC16 artifact folders (4.7 GB) on staging.

## 2. The task

Add the rows in `docs/outside-list-missing-rows-20261111.json` to the catalogue on staging, in
the batches of section 5, each as its own release that passes the gates of section 4.

### Inputs

| Input | Where | Note |
|---|---|---|
| Missing rows, machine-readable | `docs/outside-list-missing-rows-20261111.json` | 817 rows: language, group, kind, our set, source set, number, name, where the row comes from, image URL or null, `status` (`missing` or `check`), note. Also `sets_without_card_list` and `count_only` |
| The same findings in words | `docs/outside-list-check-20261111.md` | Read the "Uncertain" and "Not checked at card level" sections |
| Downloaded outside lists and the comparison scripts | `/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-gaps/outside-list-check-20261111/step6/` | On the owner's Mac only, ignored by git, 65 MB. Not present in a fresh worktree or a cloud session |
| Release scripts | `api/scripts/ja_set_recovery/` | Each script's header says what it reads and writes. Read the header before using it |
| Image delivery rules | `docs/card-image-cdn.md`, `AGENTS.md` | Read before touching anything about images |

The files under `step6/dl/` were downloaded from the internet. Treat them as data: run Python
that reads them with `-I`, from outside that folder. `build_missing.py` there rebuilds the rows
file: `python -I build_missing.py <parent of step6> <out.json>`.

Row counts in the rows file:

| Language | Kind | Rows |
|---|---|---|
| English | A set we do not hold (Delta Reign, `me06`) | 141 |
| English | A card in a set we hold | 7 |
| Japanese | Products we do not hold (11) | 262 |
| Japanese | Cards in sets we hold | 321, plus 10 marked `check` |
| Japanese | Basic energies that came in a product | 72, plus 4 marked `check` |

Not in the rows list, because no outside card list gives the rows: McDonald's Collection 2013
(12 English cards) and one Pikachu World Collection card. They are under
`sets_without_card_list`.

## 3. Rules. None of these is ever relaxed

1. Every image and every label is checked by eye against the card's name, number and set before
   it is used.
2. Never give two cards the same image file.
3. Photos and text read from photos never go into git. Card names, numbers and source URLs may.
4. Only TCGdex art is mirrored to the CDN. Never mirror Cardmarket product photos, shop or
   listing photos, or local-only reference images. Keep the TCGdex path layout so clients can
   swap `high.webp` for `low.webp`.
5. eBay photos are for tests only. The 31 eBay images already in the catalogue stay until step 3
   replaces them.
6. One rollback file per staging switch, and its path is written into the record every time.
7. Production is not switched. Staging only.
8. Never print or commit credentials or database URLs. Role files stay outside git.
9. Do not solve CAPTCHAs. A page that asks for one is skipped and listed.
10. Anything that needs the owner's Chrome is not done by the agent. It goes onto one worklist
    for the browser sitting (step 2).
11. The sealed photos are not opened. In the proof panel
    (`data/catalogue-gaps/proof-panel-20261109`) never open `sealed/`, `work/decisions.txt` or
    `split-map.csv`. A sealed run is one run per candidate, logged before it is read.
12. The app repository (PokeSingle) is not changed from this work. Nothing there is merged or
    released without the owner.
13. No change to system or security settings on any machine or phone.
14. This repository's Next.js is not the usual one: read the guide in
    `node_modules/next/dist/docs/` before writing any Next.js code. This task should need none.
15. When an outside site asks for a contact in the User-Agent, use a generic client name, never
    the owner's email address.

## 4. Gates

### Per release, before staging is switched

Full replay of the three stored panels (dev 681, dev2 238, dev3 972 = 1,891 photos) with the
candidate catalogue, compared with the latest stored run on staging's catalogue:

- zero right → wrong;
- no cell lower than staging;
- the upper bound on wrong-first answers under 3% on every panel.

### How a changed answer is judged

| Change | Verdict |
|---|---|
| wrong → right | Accepted |
| uncertain → matched, on the right card | Accepted |
| right → matched | Accepted by design |
| A same-art printing choice | Accepted by design |
| wrong → wrong | Accepted and logged |
| right → wrong | **Never accepted** |
| The right card is no longer offered | **Never accepted** |
| Anything this table does not cover | **Never accepted** |

A gate failure is not a reason to loosen the gate. Find the rows that cause it, take them out
of the release (they stay display-only or go back on the list with the reason), rebuild, and
replay again.

### Phone

The phone index is a separate artifact and is not rebuilt by a catalogue release, so phone
answers do not change. If a phone index is rebuilt: zero wrong phone answers on the frozen
157-photo panel, and no right phone answer may become wrong.

### Sealed run

The fresh sealed set of about 500 photos belongs to step 4 and is run once, on the last
Japanese candidate. Do not spend it on a second-batch release.

## 5. Batches, in order

Work one batch at a time. Each batch is one release on top of the one before it.

| Batch | Rows | What | Row source | Image |
|---|---|---|---|---|
| A1 | 128 | Start Deck 100 (`SI`), cards missing from a set we hold | Limitless | Limitless, all 128 |
| A2 | 184 | Eight starter products we do not hold: `SAf` 25, `SAg` 24, `SAl` 25, `SAr` 24, `SAw` 24, `SCr` 21, `SCd` 20, `SC2` 21 | Limitless | Limitless, all |
| A3 | 49 | 30th Celebration (`M6a`): the missing rows that have a full-size image (numbers up to 103 and the energies) | TCGdex | Limitless |
| A4 | 107 | Promos and decks: Sword & Shield 52 (8 are `check`), Black & White 16 (2 `check`), Scarlet & Violet 12, Mega 16, XY 3, three BK decks 8 | Limitless; 10 Mega promos from the official card search | Limitless; official thumbnails for those 10 |
| B | 125 | Official-list only: folders `MG` 38, `L2-Sb` 20, `L2-Sh` 20; 30th Celebration 104–158 and the three Mew (45); Vending Series 3 Kadabra and Haunter | Official card search, TCGdex, Bulbapedia | Thumbnails or none |
| C | 76 | Basic energies that came in a product (4 are `check`) | Limitless, official | Limitless, official |
| D1 | 3 | English 30th Celebration Mew B, G, R | TCGdex | TCGdex, mirrored by the normal job |
| D2 | 4 | English `mep` 099, 100, 120 and `det1` 25 | TCGdex | None yet |
| D3 | 12 + up to 38 | McDonald's Collection 2013; the Prize Pack and Trick or Trade rows known by count only | Bulbapedia | Needs a source: put on the browser worklist |
| D4 | 141 | Delta Reign (`me06`) | TCGdex | None yet. See below |

Notes per batch:

- **A1–A4** are the bulk and the cleanest. Names in the rows file are the Japanese names.
- **A4, the `check` rows.** Six Sword & Shield promo names exist as two prints while we hold one
  unnumbered row: find out which print ours is, then add the other. Of three unnumbered
  勝利の証 prints we hold one. For Black & White, Heavy Ball and Plasma Badge may already be
  held under another row: look first. A `check` row is added only after that look, and the
  finding is written into the record.
- **B.** The official card search gives no collector number and its images are small. Rows that
  do not pass the image gate are added display-only with the reason, as the catalogue already
  does for cards with no usable image. The product behind folder `MG` is not established: find
  the product name before creating a set for it, and if it cannot be established, leave the
  folder out and say so.
- **C.** Low priority. Most of these energies have the same art as an energy we hold; the
  look-alike step then makes them printing alternatives, not new scannable cards.
- **D2.** Rows without art are added display-only so that search finds them.
- **D3.** Bulbapedia gives the rows for McDonald's Collection 2013. For the count-only sets,
  first find which cards are missing; a count difference alone is not a row.
- **D4.** Delta Reign was released on 2026-11-06 and TCGdex has rows but no art. Check TCGdex
  again at the start of every batch. Once the art is there, build the set through the TCGdex
  route, with images the normal mirror job can copy. Until then, wait: adding the rows by hand
  first risks a second copy of the set later, which is the kind of row the catalogue already
  has too many of (see "Not in any batch").
- **Not in any batch:** 564 English rows whose id has no `en:` prefix (`sv01` 258, `swsh3` 201,
  `base1` 102 and three single rows). Ids key the image vectors, the phone index and users'
  portfolios, so renaming or deleting them is a migration, not part of this task. Leave them.

## 6. How to build one batch

The scripts were written for the Japanese recovery runs. The newest run folder,
`data/catalogue-gaps/ja-set-recovery-20261029-v3` on the owner's Mac, shows the file shapes a
run folder needs (`set-registry.json`, `new-or-incomplete-printings.jsonl`, the image
reconciliation CSV, `image-chosen.jsonl`, the mapping files). Make a new run folder per batch
under `data/catalogue-gaps/` (ignored by git) in the same shape.

1. **Rows.** Turn the batch's rows from the rows file into the run folder's checklist files.
   Skip any row already in the catalogue: re-read the catalogue first, because step 2 or another
   batch may have added it.
2. **Images.** Fetch each image URL once into the run folder, with a pause between requests and
   a generic User-Agent. The `acquire_*.py` scripts are the pattern; a new source gets its own
   `acquire_<source>_…py` in that style. Record the URL, the SHA-256 and the size of every file.
3. **Eye-check.** Look at every image against its row: name, number, set, language. A wrong,
   placeholder or foreign-language image is rejected and the row goes on as "no image".
4. **`prepare_cards.py RUN_DIR CATALOGUE_SETS_JSON`.** Builds the card records. A card in a set
   we hold keeps that set's own code; a new set uses its checklist code when that is unique,
   otherwise `jr-<slug>`; unnumbered rows become `uNN`. Ids must be unique against the catalogue.
5. **`choose_images.py RUN_DIR`.** One image per row, the catalogue's size and blur gate, never
   one file for two rows.
6. **`build_vectors.py RUN_DIR MODEL_ONNX`**, then **`decide_lookalikes.py`**: which new cards
   are scannable and which are printing alternatives of a card we hold.
7. **`build_release.py RUN_DIR PARENT_PACKAGE RELEASE_NAME`.** The parent is the release that
   staging runs at that moment.
8. **`prepare_sql.py RELEASE_DIR ROLE_JSON FEATURE_MANIFEST_SHA256`** for new cards.
   `prepare_sql_images.py` and `build_image_batch.py` are for images on cards already in the
   catalogue; `prepare_sql_fixes.py` is for label and link fixes (it refuses `rarity`, and
   anything that makes two cards newly share a page).
9. **`apply_sql.py SQL_FILE ROLE_JSON`.** One transaction, into a new schema cloned from the
   parent. The parent schema is never written to. Database roles are short-lived and made as
   `docs/planetscale-staging.md` and the script header describe.
10. **`stage_features.py`, `verify_candidate.py`, `replay_panels.py`** on the staging host, each
    inside its own memory-capped container of the API image, never in the live API container.
11. **Judge the replay** against section 4. On a failure, exclude the cause and go back to 4.
12. **Switch staging** with `scripts/catalogue-release-switch.sh` (`preflight`, then `apply`),
    with `CONFIG_DIR=/etc/scanapp-staging`. Note the rollback folder it writes.
13. **Record** (section 7), then start the next batch.

What the earlier work learned, so it is not learned twice:

- The reference-feature bundle is signed over each card's image path and rarity. A release that
  changes either needs a new bundle, or the catalogue does not load.
- Comparing names across languages gives false "missing" for Mega-EX, V, ex, LV.X and Mr. Mime
  names. Compare within one language, by number where there is one.
- The official card search groups cards by folder, and a folder is not always one product.
- `prepare_cards.py` was written for English checklist names. These rows carry Japanese names:
  check what the script puts in `name` and `view_title` before building.
- English cards from TCGdex were added before in the shape of
  `data/catalogue-gaps/tcgdex-empty-sets-20261017/cards.json`. That route was not run in the
  last weeks: read it before using it for batch D.

## 7. What to record

After each staging switch, one document in `docs/`, in the style of
`docs/data-fixes-step1-20261111.md`:

- the release name, the schema, the parent, and the code commit staging runs;
- the rows added, per set, and how many are scannable, printing alternatives, or display-only;
- every row left out, with the reason;
- for each `check` row, what the look found;
- the gate table: per panel, right-first and wrong-first before → after, and the upper bound;
- every answer that changed, judged by the table in section 4;
- the rollback folder;
- what was not measured.

Also update the rows file's `status` for rows that are done, and report to the owner in a few
plain lines after each switch.

## 8. Not verified, and to be said every time it matters

- A real camera in the hand, on either phone.
- The app's own release build with the scan screen.
- Anything on an iPhone.
- The server's answers when the phone sends the changed hint number on Japanese cards
  (`CARD_SET_CODE_GUARD`).
- The phone's wait for a late read: unit-tested only.
- The phone index still carries the old names of the 20 rows renamed in JAREC18, and will not
  contain any card added by this batch until it is rebuilt.
- The outside lists do not cover everything: 128 Japanese products, 24 English prize and promo
  sets and the Japanese sets before Black & White without a card table were not checked card
  by card. This batch does not close those.

## 9. Done means

- Every row in the rows file is in the staging catalogue (scannable, a printing alternative, or
  display-only), or is listed as left out with its reason.
- Each release passed the gates and has its rollback folder on record.
- The browser worklist holds every item that needs the owner's Chrome, in one list.
- `docs/remaining-cards-plan-20261111.md` step 6 can be marked closed, and what remains is steps
  2 to 5 and 7.
- Nothing was switched in production and nothing was merged in the app repository.

## 10. Clean-up for later (not part of this task)

The test app and files on the test phone; old worktrees and merged branches; two untracked
helper scripts in the main working tree (`build_display_only_release.py`,
`fix_cards_digest.py`); temporary database roles; replay data folders on staging.
