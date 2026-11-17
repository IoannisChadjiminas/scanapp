# On-phone card index v4 (2026-11-17): printing alternatives, prints.tsv, set codes

A phone index for the plan to recognise cards on the phone without the server. **Built locally only:
not published, not deployed; staging is unchanged.** The phone app is not changed.

| Item | Value |
|---|---|
| Folder | `data/catalogue-gaps/phone-index-v4-20261117/release/cbc610a7533050ec17156352cf87956bd1c1b4238a2682134bf13e967108dcee` |
| Base | `32f22e3fa19e49e43c0d2f940ff00c03b2a5201e0ae8d4bd9de57e54ac3bda0b`, the index staging serves (IMG1 to LINKS5J), 48,874 rows, unchanged byte for byte |
| Rows | **51,625** = 48,874 + 2,751 printing alternatives with their own vector |
| `card_index.prints.tsv` | 1,719 printing alternatives with no vector (new file, hashed in the version file) |
| Meta columns | v3's 15 (`id name number printed_number set_total language promo_code row_kind alt_name printing_family release_year hp printing reprint_of name_en`) + `set_code` |
| Files (sha256) | f16 `cb4f9724...`, ids `2b6d0a3d...`, meta `0241f5c0...`, prints `931410d4...`, version `e287c673...` |

The staging manifest would refuse this folder: it has rows the server snapshot does not.

## Printing alternatives

4,470 catalogue cards have an image but no vector: the server keeps them out of its index because
their picture is at least 0.95 similar to an indexed card, and uses their features to choose the
printing. 4,455 are Japanese, 15 English; all have a reference image.

Each was embedded from its reference image with the catalogue's model (re-embedding three indexed
cards gives cosine 1.000). `reprint_of` is the nearest indexed card of the same language when that is
at least 0.95 similar (4,090), otherwise the most similar indexed card with the same title (355), or
none (25). Same-title matches below 0.8 similarity (33) are left without `reprint_of`.

Cut-offs on the similarity to `reprint_of`, chosen from the cards classified with confidence:

| Confident group | Cards | Similarity |
|---|---:|---|
| Same image (pixel test: mean difference < 0.01, no 16-px block > 0.05) | 1,621 | 0.9504 to 1.0, median 0.993 |
| Visibly different, by eye (stamps, other art, changed promo text) | 36 | up to 0.9933 (34 with a reprint) |

So 0.994 (above every eye-checked difference) and 0.95 (below every identical image). The two groups
overlap between them: a stamp barely moves the picture vector.

| Band | Cards | Result |
|---|---:|---|
| 0.994 and above | 882 | prints.tsv |
| 0.95 to 0.994, image identical to the reprint's (pixel test) | 837 | prints.tsv (owner, 2026-11-17) |
| 0.95 to 0.994, other | 2,371 | own row and vector |
| Below 0.95, or no reprint found | 380 | own row and vector |

Contact sheets of the middle band (134 sheets): `phone-index-v4-20261117/middle-sheets/`. A sampled
sheet had 21 same-art pairs of 24; the rest are stamps. Band per card: `bands.json`.

Own rows carry `printing` (by the existing rules: 2,427 regular, 304 promo, 20 other) and
`reprint_of` (2,693 of 2,751; 58 empty as above). The existing rules do not mark Japanese stamped
cards as `stamped` (only English families do), so a stamped Japanese card shows `regular` with a
`reprint_of`.

`card_index.prints.tsv`: `id reprint_of printing number printed_number set_total set_code promo_code
release_year`, one row per card; every `reprint_of` is an index row.

## New column and fills

| Column | English | Japanese | Source |
|---|---:|---:|---|
| `set_code` (new) | 92.0% | 71.1% | English: TCGdex `abbreviation.official` (`PAL`), fetched 2026-11-17 (`tcgdex/en-abbrev.json`, 191 of 240 sets). Japanese: the Limitless code through NAMES3's set map, or the same code. Older Japanese sets print a symbol, not a code, and stay empty |
| `promo_code` (existing, filled where empty) | 5.7% | 8.1% | 1,292 English Black Star promos: SWSH, SM, XY, BW, DP, HGSS, SVP, MEP. Wizards and Nintendo promos print no prefix |

Names, set totals, years, HP and `name_en` are v3's rules on the new base (`names.json` rebuilt for the
added rows; identical to v3 on every row both cover).

## Picture-only test on the gate photos

1,892 photos: the 1,891 the gate replays plus `dev-en-vintage-073`. That photo was added to the dev
panel on 2026-11-09, after the replay batches were cut, so no batch held it; it is now in
`proof-panel-20261109/work/shards/dev9`. (The labels hold 1,991 dev/dev2/dev3 photos: the other 99 are
the sealed vintage half retired on 2026-11-10, kept out of the gate.)

Each photo was squared with the server's `detect_and_rectify` (card found in 1,360) and embedded as the
index was; the first answer is the top picture match. There is no text step, so right-first is far
below the server's; the comparison between the two indexes is what this measures.

| Panel | Photos | Right first | Wrong first | Right in top 5 | Twin first |
|---|---:|---|---|---|---|
| dev | 682 | 447 -> 442 | 235 -> 240 | 562 -> 561 | 9 -> 13 |
| dev2 | 238 | 160 -> 160 | 78 -> 78 | 206 -> 206 | 6 -> 7 |
| dev3 | 972 | 621 -> 620 | 351 -> 352 | 791 -> 793 | 36 -> 37 |

First answer changed on 36 photos; 35 of the new answers are added rows.

| Change | Photos |
|---|---:|
| Fixed (wrong -> right) | 4 |
| Right -> twin of the right card | 7 |
| Right -> another card that is not a twin (broken) | 3 |
| Wrong -> twin of the right card | 4 |
| Wrong -> another wrong card | 16 |
| Right -> another right card | 2 |

Twin: same printing family (`reprint_of`, `prints.tsv`, `families.json`) or a picture at least 0.95
similar to the right card. Broken: `en:dp1-109` -> `ja:jr-dpt-entry-pack-giratina-010` and `en:neo2-39`
-> `ja:jr-intro-pack-neo-totodile-u07` (English photos answered by a Japanese print), `ja:XY2-064` ->
`ja:CP4-093`.

Print sheet (top two matches a reprint pair within 0.05):

| Reprint pair means | Before | After |
|---|---:|---:|
| Linked in the index data (`reprint_of`, `printing_family`, prints.tsv), what the phone can see | 5 | 29 |
| Linked, or pictures at least 0.95 similar | 143 | 161 (20 new, 2 gone) |

`dev-en-vintage-073` (`en:base2-5`) ranks third by picture in both indexes.

## Files

Work folder `data/catalogue-gaps/phone-index-v4-20261117/`: `bands.json`, `add-ids.txt`,
`add-vectors.npy`, `prints-ids.txt`, `names.json`, `columns.json`, `phone-replay.json` (every changed
photo), `queries/` (photo vectors), `middle-sheets/`, and the scripts that made them
(`embed_alts.py`, `reprint.py`, `bands.py`, `fetch_abbrev.py`). In the repository:
`api/scripts/on_phone_index/phone_columns.py` and `extend_index.py` (set_code, promo fill,
prints.tsv), `embed_photos.py` and `phone_replay.py` (the test), tests in
`api/tests/test_phone_index_extend.py`.

## Not done

- Not published, not deployed, staging unchanged.
- The server gate does not run `dev-en-vintage-073` yet: `run_gate.sh` and `score_gate.py` (dev = 681)
  still list the old batches, and the accepted baselines lack it.
