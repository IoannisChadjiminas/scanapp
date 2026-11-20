# Japanese names, printing families and zh-tw rows (2026-11-14)

The owner approved the three open review items ("ok lets proceed now with these steps"). Two releases
build on the clean-up release (`docs/catalogue-cleanup-20261114.md`). They were gated together and
switched once, on the second:
- **NAMES3** (`pokesingle_completion_20261114_names3` / `PS-CATALOGUE-EN-JA-NAMES3-20261115`): gives
  3,660 Japanese rows their printed Japanese name and records printing families.
- **LINKS3** (`pokesingle_completion_20261114_links3` / `PS-CATALOGUE-EN-JA-LINKS3-20261115`, parent
  NAMES3): moves 59 Start Deck 100 Cardmarket links from `zh-tw:SI-*` to `ja:SI-*` and clears the other
  38 `zh-tw` links.

The first build (NAMES1 with 7,681 names, LINKS1 on top) failed the gate, and so did nothing on staging; see
"Gate". NAMES2/LINKS2 (CP6 held) were built but not replayed, because the solo re-run showed a second cause.
All six schemas stay inactive and untouched; none is dropped.

Production is not touched. Vectors, ids and images are unchanged.

## Switch

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-LINKS3-20261115`, schema `pokesingle_completion_20261114_links3` |
| Parent | `PS-CATALOGUE-EN-JA-NAMES3-20261115` (`pokesingle_completion_20261114_names3`), whose parent is CLEANUP1 |
| SQL | NAMES3: 36 statements, sha256 `69f4ba76c05d0204d4a4922793dfd97bdcb160b1b92d0c57d4fc5d51069fb1be`, cards md5 `9475aa3853660277c8559b2ce0d4ff1c`. LINKS3: 240 statements, sha256 `f2d9fd25dd70f7309205bfa555bb88d9bd92223e4e1a67acc5825a6c2891cac1`, cards md5 `e9524320fbf5616b29a154ac2e60f81c` |
| Bundles | unchanged: features `/data/reference-features/20261114-cleanup`, artwork `/data/artwork/20261114-cleanup` |
| How | `scripts/catalogue-release-switch.sh apply`, `RELEASE_NAME=catalogue-names-links-20261115` on 2026-11-15. Only `PLANETSCALE_SCHEMA` and `PLANETSCALE_IMPORT_ID` of the env file changed (checked line by line against the live file before the switch) |
| After | health ok, ready, import `PS-CATALOGUE-EN-JA-LINKS3-20261115`, restarts 0, no OOM |
| Rollback | `/etc/scanapp-staging/catalogue-rollback/catalogue-names-links-20261115` (rollback file points to CLEANUP1) |

## 1. Japanese names

**Target:** every `ja:` catalogue row whose name has no kana or kanji. That is 14,438 rows: 10,272 in the phone index plus 4,166 without a vector.

**Sources:**

| Source | What it holds for these rows |
|---|---|
| TCGdex ja | Nothing. Its Japanese sets for these rows list no cards (for example `/v2/ja/sets/S3a`: `cards: []`). These are the sets the recovery filled from English checklists. |
| TCG Collector | English names for Japanese cards; automated requests are refused (403). |
| Bulbapedia set lists | English card names only. Each card page states the Japanese name; see "Not done". |
| Limitless JP set lists (`limitlesstcg.com/cards/jp/<set>`) | Set code, printed number and the Japanese name for 264 sets (20,169 cards), BW era onward. Pages were saved on 2026-11-11 for the outside-list check. |

**Rule** (`api/scripts/ja_set_recovery/match_ja_names.py` for 1–4, `hold_split_names.py` for 5–6, deterministic):
1. **Join** only on set plus printed number, never on a name.
2. **Choose the set.** Each of our sets maps to the Limitless set where the most rows agree. The mapping is used only when at least 70% of the rows that find their number agree. 173 sets are mapped, including split sets such as `BW5-Brz` → `BW5z` and `XY11-Bb` → `XY11b`.
3. **Accept a name** only when it agrees with the row's English name:
   - `pair`: the same English/Japanese pair already exists on another Japanese row of the catalogue.
   - `species`: the English name's species translates (`ja_species_names.json`) into the Japanese name, with the same suffix (V, VMAX, VSTAR, GX, EX, ex, BREAK, …).
   - `set-aligned`: a name with no species in it (trainers, energies, species missing from the table), only from a set where at least 85% of numbered rows agree.
4. **Mega cards.** A Mega card whose source name has no Mega prefix is not accepted. Limitless drops it on XY Mega EX (CP6/91 is listed as `リザードンEX`).
5. **No split** (added after the LINKS1 gate). The server groups same-art Japanese printings by their exact
   `name` and breaks the tie inside the group. A rename is applied only when every `ja` row with that English
   name is renamed, to one spelling. If any row of that English name keeps it (no source, or review), all of
   them keep it. Otherwise a rename splits a group that was one: the SMP and XYP Pikachu promos became
   `ピカチュウ` while the DP-era Pikachu rows, with no Limitless list, stayed `Pikachu`, and two Pikachu photos
   lost their right card. This holds 3,932 rows (852 English names, largest Switch 79, Pikachu 62,
   Ultra Ball 60).
6. **CP6 held.** The 94 rows of CP6 (20th Anniversary) keep the English name. Their originals in PMCG1 are
   already Japanese, so the rename joins the reprint to the original's group, and seven Base Set photos went to
   the CP6 reprint in the LINKS1 gate.

Spelling is kept as the source prints it (`ガラル デスバーン` with a space). `view_title` keeps the English name, so English search still finds these rows.

**Results:**

| Result | Rows | In phone index |
|---|---:|---:|
| Name set from the source | 3,660 (pair 2,883, species 544, set-aligned 233) | 2,509 |
| Source name is already the row's name (`N`, `AZ`: printed in Latin letters) | 5 | 5 |
| Kept English: held by the no-split rule | 3,932 | 2,509 |
| Kept English: CP6 held | 94 | 84 |
| Kept English: the source disagrees with the English name | 247 | 163 |
| Kept English: number not on the mapped Limitless set (newest promos) | 702 | |
| Kept English: set has no Limitless list (DP, Platinum, LEGEND, ADV, PCG, e-Card, `jr-*`, …) | 5,803 | |

The two "number not on set" and "no Limitless list" groups together are 6,505 rows, 5,008 of them in the phone index.

Each row that keeps its English name is listed, with its reason and any candidate Japanese name, in `docs/catalogue-names-20261114-kept-english.tsv`. The review rows are mostly Mega EX cards and deck sets whose numbering differs from Limitless. Each changed row's source and check is stored in the release record `catalogue-names-ja:PS-CATALOGUE-EN-JA-NAMES3-20261115`. The held rows carry their candidate Japanese name in the list, so a later release can apply them together with the rest of their name group.

Examples, checked by eye on samples of each kind:
- `ja:S4-016` Talonflame V → ファイアローV
- `ja:BW9-070` Reversal Trigger → リバーサルトリガー
- `ja:S1a-016` Cinderace V → エースバーンV
- `ja:SVOD-003` Steven's Carbink → ダイゴのメレシー
- `ja:SMP-104` → シロデスナGX. Its English name was scraped text: `L18: 【30†Image: Palossand-GX`. That text is still its `view_title`, so it shows in the phone index `alt_name`; see "Not done".

**Phone and app:**
- The phone index `name` column now carries the Japanese name for the 2,509 indexed rows that changed.
- A new last column, `alt_name`, carries the English title.
- The app reads the first six columns (`PhoneCardMeta.parse` needs at least six and ignores the rest), so builds already shipped keep working.
- No column was reordered.

## 2. Printing families

**Rule** (`api/scripts/ja_set_recovery/printing_families.py`, `printing-family-v1`, deterministic):
- **Members:**
  - Prize Pack rows `en:PPS<n>-<CODE>-<NUM>`: 983 rows.
  - Stamped rows whose `variants_json` names a `printed_set` and a `stamp` (Trick or Trade 2022–2024): 89 rows.
- **Base:** the regular row with the same number in the set that `<CODE>` stands for. A code maps to the English set where the most members find a row of the same name at the same number. It is used only when at least 80% do; 50 of 51 codes map.
- **Join:** a member joins its base only if the names are equal (case and punctuation ignored) and the art is the same.
  - Same art means a cosine of at least 0.70 between the two catalogue vectors.
  - Every pair between 0.70 and 0.88 was checked by eye on contact sheets (39 pairs). All are the same art; the stamp lowers the score.
  - The next pairs down, 0.38–0.43, are rows whose reference image is a card back.
- The family id is the base row's id. Any other row is its own family.

**Results:**
- 991 members joined (Prize Pack 916, stamped 75) into 749 families: 523 of 2 rows, 210 of 3, 16 of 4.
- Cosine median 0.968, lowest 0.736.
- 81 members were left out, each with a reason in `docs/printing-families-20261114-left-out.tsv`:
  - 61 have no base set: the basic energies `SVE`, and the Trick or Trade copies of `SWSH10`, whose names agree with the base set at the same number too rarely.
  - 16 have no base row with the same name.
  - 4 have a card-back image: `en:PPS2-BRS-064`, `en:PPS3-LOR-118`, `en:PPS3-LOR-119`, `en:PPS3-SVI-076`. Their reference image and vector are a card back; see "Not done".
- Japanese rows have no Prize Pack or Trick or Trade copies in the catalogue, so all their families are single rows.

**Storage:**
- **Catalogue:** the reference_metadata record `printing-families` holds `{card_id: family_id}` for the 1,740 rows in a family, with the rule. Every release builder copies it. The API loader does not read it, so recognition and answers cannot change.
- **Phone index:** a new last column, `printing_family`, filled from that record (`export_index.py --families`).
- **API:** exposing the family needs a code change that is not deployed. Staging runs `main`.

## 3. zh-tw rows

- **Recognition:** 7,436 `zh-tw` catalogue rows, 2,260 with a vector.
  - No `zh-tw` vector equals a `ja:` vector: the highest cosine to any `ja:` row is below 0.999 for every one.
  - The median is 0.971: same artwork, but the card text is Chinese.
  - So none is a duplicate in the sense of the 561 unprefixed rows, and all 2,260 stay in recognition. They are distinct images, marked `row_kind=language` in the phone index.
- **Start Deck 100 links:** 59 `zh-tw:SI-*` rows hold the Cardmarket page of Start Deck 100 (`sI100<NNN>`).
  - Each matching `ja:SI-<NNN>` row exists and has no link. The recovery held them because the URL was already on a catalogue card.
  - The request named 4 links, but the catalogue has 59.
  - **Checked in the owner's Chrome** (the owner cleared Cardmarket's human check). The Start Deck 100 list view (150 rows) gives product id = 587710 + number with no exception. All 59 product photos were looked at by eye: each is the Japanese print (katakana name) of the same card. Three printed numbers were zoomed on (129, 173, 174 of 414). Decisions: `zh-tw-links-decisions-20261114.json` in the sessions' shared notes.
  - **Moved in LINKS3:** each `ja:SI-<NNN>` gets the page and product id (`cardmarket_verified=1`, provenance `cardmarket-start-deck-100-photo-check-20261114`), and the `zh-tw` row's link is cleared. This also settles `ja:SI-169`, `-174`, `-301` and `-310`, which were held in batch K.
- **Other links:** 38 other `zh-tw` rows carry a Cardmarket link from the `helper-expansion` provenance.
  - 5 point to the same card on a Japanese product (`SK-008` Crobat V, `SLD-008` Darkrai VSTAR, `SLL-005` Lucario VSTAR, `SP6-004` Zacian VSTAR, `SP6-006` Zamazenta VSTAR). The catalogue has no `ja:` row for these prints, so the links are cleared.
  - 33 point to a different card. Examples:
    - `zh-tw:S10D-032` 怪力V → ADV Donphan
    - `zh-tw:S4a-124` → Iono SVP124

    These 33 are cleared.
- **LINKS3 in numbers:**
  - 156 card rows updated (59 links added, 97 cleared). No `zh-tw` row keeps a link.
  - The builder (`prepare_sql_fixes.py`) now frees a cleared link before another row of the same batch takes it.
  - The guard confirmed no new shared Cardmarket page.
  - The 97 `cardmarket_url_helpers` rows of these `zh-tw` cards are kept as the history of where the old links came from, as in earlier link batches. The API does not read that table.
  - All 97 links and their actions are in `docs/zh-tw-links-worklist-20261114.tsv`.

## Gate

1,891 photos replayed against each candidate (local docker, image `scanapp-api-staging:24856ba9`, 3 lanes), scored
against K3's accepted run with `score_gate.py`, the same baseline as the clean-up release.

**LINKS1 (7,681 names): failed.** Right first dev 637 → 634, dev3 938 → 936; dev3 wrong first 0 → 1; one right card no
longer offered (`sealedF-ja-promo-065`); cells lower `dev:unnumbered_vintage:ja`, `dev3:promo:ja`,
`dev3:unnumbered_vintage:ja`. Nine right-first losses:
- Seven Base Set photos (`ja:PMCG1-013`, `-020`, `-034`, `-050`, `-057`, `-058`) went to the CP6 reprint, which now
  shared the original's Japanese name.
- `sealedF-ja-promo-065` (`ja:SMP-179`) and `sealed-ja-promo-045` (`ja:DPP-113`) went to `ja:DP2-002` and
  `ja:DPtS-007`: the SMP and XYP Pikachu promos were renamed, the DP-era ones kept `Pikachu`.

The five photos not plainly explained were re-run alone on LINKS1 and on CLEANUP1: the same answers both times, so load
was not the cause. NAMES2/LINKS2 (CP6 held only) were built but not replayed. Rules 5 and 6 above came from this.

**LINKS3 (3,660 names): passed.**

| Panel | Photos | Right first | Wrong first | Right offered | Wrong-first upper bound |
|---|---:|---|---|---|---:|
| dev | 681 | 637 → 637 | 4 → 4 | 663 → 663 | 1.5% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.4% |

Right → wrong: 0. Right no longer offered: 0. Cells lower: none. All eleven lanes exited 0 with every row.

96 answers changed against K3, and each was looked at. No card shown first changed:
- 16 went to `matched` with the same right card (15 from `uncertain`, 1 from `printing_ambiguous`), 9 of them
  Japanese promos.
- 14 changed only because an old id became its `en:` twin (the clean-up release).
- 11 changed only the order of their alternatives.
- 55 changed which alternatives are offered; in 51 of them a renamed row entered or left. None lost the right card.

## Phone index

| Item | Value |
|---|---|
| Before | `d40042cbb35dc7f8a8a021ffa67b7bf2af6875ffa499769d52ea6780ebf121f1` (still valid after the switch: same ids and vectors) |
| Now | `07e3a028571c086d8b3a4fd6d2c7cc4e067065a863bef8a52f1a884cef7e9adb`, 48,934 rows |
| Same as before | ids file and float16 vectors byte for byte; only `card_index.meta.tsv` and the version file differ |
| Meta | 2,509 rows have their Japanese `name` (no other of the first eight columns changed); `alt_name` filled on 15,968 rows; `printing_family` on 1,740 rows |
| Rollback record | `/etc/scanapp-staging/catalogue-rollback/phone-index-names-links-20261115/ACTIVE.before` |
| Check | manifest 200 inside the container and from `staging-scan.pokesingle.com`; the meta, ids and version files download with the manifest's sha256; a ranged request on the vectors returns 206 and the whole file matches |

Built from a local snapshot export of LINKS3 (read-only role) with this branch's `export_index.py --families`. Its ids
and vectors files are byte-identical to the CLEANUP1 export. `export_exceptions.json` only shrank: Latin-only Japanese
names 10,274 → 7,765; unprefixed ids stay 2.

## Going back

On the staging host, from the code directory:

```
CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-names-links-20261115 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback
```

Then write `d40042cbb35dc7f8a8a021ffa67b7bf2af6875ffa499769d52ea6780ebf121f1` to `/data/phone-index/ACTIVE.next` and
rename it to `ACTIVE`. Going back to CLEANUP1 keeps the same ids and vectors, so either phone index would pass the
manifest check; `d40042cb` is the one whose names match CLEANUP1.

## Not done

- **Japanese names for the 6,505 rows with no Limitless list.** These are the DP, Platinum, LEGEND, ADV, PCG and `jr-*` sets. Bulbapedia's card pages state the Japanese name, and the saved set lists link each set number to its card page. A follow-up can fetch those pages (MediaWiki API, 50 per request) and apply the same check.
- **The 4,026 held names** (no-split rule and CP6). They can be applied once their whole name group has a
  source, which mostly means the Bulbapedia step above, and once the server's printing tie-break no longer
  depends on the shared name. Each needs its own gate.
- **The 247 review rows** need a look: XY Mega EX, and deck sets numbered differently on Limitless.
- **4 Prize Pack rows with a card-back image:** `en:PPS2-BRS-064`, `en:PPS3-LOR-118`, `en:PPS3-LOR-119`, `en:PPS3-SVI-076` need their real image and vector.
- ~~`ja:SMP-104`'s scraped `view_title`~~: done with 127 other scraped titles in TITLES1, switched on staging
  2026-11-15 with phone index `e19e142e…` (`docs/catalogue-titles-20261115.md`).
- **Schemas `…_names1`, `…_links1`, `…_names2`, `…_links2`** are inactive and unused. Dropping a schema is permanent;
  it waits for the owner.
- **API exposure of `printing_family`, and the app using it** to count printings once.
