# Phone index review: totals, promo codes, row kinds and export checks (2026-11-14)

An external review of the phone index served on staging (`dbce63d9…`, catalogue J vectors, 51,817 rows) found
wrong or missing set totals, digital and unsupported-language rows, and unprefixed duplicate ids. This record
covers what was changed, what was published on staging, and what is still open. Production is not touched;
the model and the vectors are unchanged.

## Published on staging

| Item | Value |
|---|---|
| Catalogue served | `PS-CATALOGUE-EN-JA-REC44-K-20261114` (schema `pokesingle_completion_20261111_jarec44`), unchanged |
| Phone index before | `dbce63d9a4790f299c4d2873727a6d749ce2463651ca829a7193d41e5b6016b8` (kept in `/data/phone-index/`) |
| Phone index now | `28eaa9f4b1513b280c7806e03e84a5169598db103f01952b5767871c1e94cfc9` |
| Rollback record | `/etc/scanapp-staging/catalogue-rollback/phone-index-totals-20261114/ACTIVE.before` |
| Published | `/data/phone-index/<version>/`, then `ACTIVE.next` renamed to `ACTIVE` |
| Check after publish | manifest 200 inside the container and from `staging-scan.pokesingle.com`; meta file downloads with the manifest's sha256; ranged request on the vectors 206 |

Same rows, same order, same ids file (`adfbf50c…`) and same float16 vectors (`c7132a63…`) as `dbce63d9`; only
`card_index.meta.tsv` (and so the version file) differs. Built with this branch's `export_index.py` from the
snapshot export of 2026-11-14 (`/root/pidx-printed-20261114/out/snapshot` on the staging host) and its
operational totals (`totals-v2.sqlite`). The old exporter on the same inputs reproduces `dbce63d9` byte for byte.
That export was taken under catalogue J; K is links-only, and a read-only query on `jarec44` gives the same
digest as the export over the columns the index uses (`id, name, collector_number, printed_collector_number,
language, set_id`: 62,784 rows, md5 `6ede892288ec9ad1be43e771ac5b7795`). No second catalogue-loading container
was started on the host (about 750 MB free next to the live API).

## 1. Totals and promo codes (exporter only)

`card_index.meta.tsv` gains two columns after the six the app reads: `promo_code` and `row_kind`. The app's
parser (`PhoneCardMeta.parse`, PokeSingle `lib/data/phone_provisional.dart`) needs at least six fields and reads
only the first six, so the published file works with the app as shipped.

`set_total` now follows what the card prints:

| Change | Rows | Example |
|---|---:|---|
| Filled from a printed fraction | 1,342 (991 en, 351 ja) | `en:PPS1-BST-006` `006/163` -> 163 |
| Filled from a fraction in the number (extra reference photos) | 3 | `extra-charmander-001-032` -> 32 |
| Printed total replaces the operational total | 145 | `ja:L2-040` `040/080`: 70 -> 80 (L2 61, L3 56, `en:ex10-unown-*` `A/28` 28) |
| Japanese promo: code, no total | 1,877 rows carry a code; 439 lose a total that is not printed on any card | `ja:SV-P-198`: 288 -> empty, code `SV-P` |

Promo codes: `SV-P`, `M-P`, `S-P` (set `SP`), `SM-P`, `XY-P`, `BW-P`, `DPt-P`, `DP-P`, `L-P`, and any printed
fraction whose denominator is a code (`ja:SP-u64` `002/S-P`). Sets that only look like promos but print a numeric
total (`S8a-P` `001/025`, `S10P`, `SM1p`..`SM5p`, `SV2P`) keep their totals. `ja:` rows with neither total nor
code: 8,151 -> 6,363 (sets with no printed total and no operational total).

Why it matters: the phone's provisional rule drops a candidate whose total differs from the total read on the
photo. With 70 for L2 and L3 the right card was dropped every time the phone read `/080`.

### Check (the gate for a meta-only change)

The server does not read this file, so the 1,891-photo server replay cannot change (same catalogue, same
vectors, same code). The phone rule was checked on the panel instead: 84 of 2,494 panel cases have an expected
card whose `set_total` changed. 39 gained the total printed on the card (L1HG/L1SS /070, S8a-P /025, MMBS /049,
BKW /018), 19 got a corrected one (L2/L3 /080), 26 are SV-P or M-P promo rows that lost a total. Looked at by eye:
`dev-ja-older-001` prints `040/080` (`ja:L2-040`) and `sealedT-ja-older-033` prints `078/080` (`ja:L3-078`).
A filled total can only drop a candidate whose printed total differs from the photo's; a cleared promo total
changes nothing, because a promo hint (`198/SV-P`) has no numeric total. Right -> wrong: none possible from this
change; L2/L3 photos read with `/080` go from "right card dropped" to "right card kept". Parity
(`check_compressed_index.py`) is unchanged: the vectors file is byte-identical.

## 2. Pocket and `zh-tw` rows

| Kind (`row_kind`) | Rows | What it is |
|---|---:|---|
| `digital` | 2,319 | Pokémon TCG Pocket (`en:A1`, `A1a`, ... `P-A`), the server's `app.physical_cards` rule |
| `language` | 2,260 | `zh-tw:` rows; the app does not support Chinese |
| `duplicate` | 561 | see 3 |
| `reference` | 6 | see 3 |

Decision: keep these rows out of the phone index with a **documented subset rule**, not by deleting them from
the server catalogue. `app/phone_index_subset.py` decides each row's kind from the snapshot ids alone. The
exporter's `--exclude digital,language,duplicate` leaves rows of those kinds out and records
`subset: {rule: phone-subset-v1, excluded, source_rows}` in the version file. The manifest route recomputes the
subset from the loaded snapshot and serves the index only when the row count, the ids file sha256 and the
float16 vectors sha256 equal what the rule gives for that snapshot (computed once per snapshot). A full index is
checked exactly as before.

Not yet in effect: staging runs `main`, whose manifest refuses any index whose rows differ from the snapshot.
After this PR is merged and staging is redeployed, a subset index can be exported and published. Which kinds to
leave out is a publish-time choice:
- `language` (zh-tw) and `duplicate`: ready; no server data changes.
- `digital` (Pocket): **waiting for the owner's decision**. The server already leaves Pocket rows out of scan and
  search answers, so leaving them out of the phone too would match the server.

Until then every published row carries its kind, so the app can skip `digital`, `language` and `duplicate` rows
in its shortlist (an app change in PokeSingle). Removing either group from the server catalogue still needs the
owner; nothing was removed.

## 3. The 567 ids without a language prefix

| Group | Rows | What they are |
|---|---:|---|
| `base1` 102, `swsh3` 201, `sv01` 258 | 561 | Rows of the first English pilot, from before ids carried a language. Each has an `en:` twin with the same name, set, number, Cardmarket page and TCGdex image (local copy at `/data/reference-images/<id>` instead of `/data/reference-images/en/<id>`). Their vectors equal the twins' (cosine 1.0000 for all 561). True duplicates. |
| `extra-*` | 6 | Extra reference photos added by hand: `extra-charmander-001-032` (ja CLL 001), `extra-lugia-v-326-s-p` (ja S-P 324), `extra-m-tyranitar-ex-089-081` (ja XY7, prints 090/081; nearest `ja:XY7-090` 0.98), `extra-mew-ex-205-metal` (en 151 UPC metal Mew; its vector equals `en:sv03.5-205`), `extra-pikachu-classic-clc008` (en CLC 008), `extra-pikachu-mcdonalds-2022-008-015` (en MCD 2022; nearest `en:2022swsh-7` 0.994). |

Two more unprefixed catalogue rows (`s8b`, `sm9`) have no vector. The app already treats `base1-1` and
`en:base1-1` as one card (`phoneCardCanonicalId`), and so does the gate scorer.

Marked now: `row_kind` `duplicate` (561) and `reference` (6). Dropping the 561 from the phone index is the
subset rule above (`duplicate`).

**Not done: dropping the 561 from the server's vectors through a catalogue release.** The release tooling here
adds rows and fixes labels or links (`prepare_sql.py`, `prepare_sql_fixes.py`); none removes vectors. A removal
release has to delete the 561 `card_embeddings` rows and rewrite the pad vector manifest (`indexed_ids`,
`indexed_count`, `ids_sha256`, `embeddings_sha256`, the 37 `retrieval_segments` offsets) and the import
manifest's vector count and aggregate md5, keep the card rows (saved collections may hold the old ids), check
the artwork index's known ids, then replay the 1,891 photos. Effect on the server: each duplicate holds a second
top-k slot for the same card; removing it lets one more card into the shortlist. Proposed as its own piece of
work. The 6 extra rows stay: four are the only vector of their print; for `extra-mew-ex-205-metal` (same image
as `en:sv03.5-205`) the owner should decide whether a metal print needs its own photo.

## 4. Plan: Japanese names and printing families

**Japanese names.** 10,273 `ja:` rows have an English name only: 9,048 have no category (TCGdex Japanese sets
without Japanese text), 1,107 Pokémon, 102 Trainer, 16 Energy; 370 sets, largest XYP 365, SMP 336,
jr-miscellaneous-promos 245, SP 221, S4a 180. This was an owner decision for the recovery (English checklist
name when no official Japanese name exists), so the plan adds a name, it does not replace one:
1. Catalogue: a nullable `name_ja` column (or alias rows), filled from a named source with provenance; `name`
   and `view_title` stay as they are.
2. First source: the species table the server already uses (`app/recognition/assets/ja_species_names.json`,
   1,011 species built from official modern Japanese rows). 6,382 of the 10,273 names are an exact species
   name; forms, owners and mechanics (`Dark`, `'s`, `ex`, `LV.X`) need the same reduction
   `build_species_names.py` uses, and every non-exact fill must be checked by eye on a sample.
3. Trainers, energies and the rest from official Japanese checklists, by set.
4. Phone: a `name_ja` column in the meta file; the provisional rule accepts a hint equal to `name` or `name_ja`.
   Until then a Japanese hint can never match these rows (`no_match`), which is safe but useless.

**Printing family.** One id for the printings a collector would call the same card: the regular print, its
Prize Pack copy (`en:PPS1-BST-006` of `swsh5-006`), stamped and staff prints. The server already groups
"artwork families" at scan time (`family_verify.py`: twin vectors, or same title and correlated artwork), but
that is per scan and spans languages. Plan: compute `printing_family` once per release from the same rules,
restricted to one language and one printed number + total, store it in the catalogue, check every family with
more than one member by eye on contact sheets, and export it as a meta column so the app's "printings of one
card are counted once" uses the family instead of the id prefix.

## 5. Export checks

`export_index.py` now fails the build on any row it cannot account for:

| Check | Rows today | Rule |
|---|---:|---|
| `unprefixed_id` | 567 | id without a language prefix |
| `latin_name_ja` | 10,276 | `ja` row whose name has no kana or kanji (10,273 `ja:` + 3 `extra-*` in Japanese) |
| `missing_total` | 0 | printed number or number carries a fraction but the row has neither total nor promo code |
| `digital_set` | 2,319 | Pocket row |

Today's rows are listed in `api/scripts/on_phone_index/export_exceptions.json` (catalogue K) and pass with
`--allow-exceptions`; any other row fails the build. A subset export that leaves out a kind no longer meets
those rows at all. `--report` writes the counts and ids.

## Going back
On the staging host write `dbce63d9a4790f299c4d2873727a6d749ce2463651ca829a7193d41e5b6016b8` to
`/data/phone-index/ACTIVE.next` and rename it to `ACTIVE` (it matches the same snapshot, so the manifest stays 200).
