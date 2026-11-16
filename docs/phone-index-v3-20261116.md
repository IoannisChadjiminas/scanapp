# On-phone card index v3 (2026-11-16): new columns, Japanese names, 13 more cards

A new phone index release built on top of the staging index for FIXES1R. **Built locally only: not
published, not deployed.** The phone app is not changed.

| Item | Value |
|---|---|
| Folder | `data/catalogue-gaps/phone-index-v3-20261116/release/e3563816939bf5d83a76055025402e8518c67650fe9621f29372f13c7b43981c` |
| Version | `e3563816939bf5d83a76055025402e8518c67650fe9621f29372f13c7b43981c` (sha256 of the identity, in `card_index.version.json`) |
| Rows | **48,883** = 48,870 base rows + 13 added |
| Base | `c7bdbcae8bb22f6f2683fa10db1deeb498577d8a750296f0c6e1797631f4768f`, the index published with FIXES1R (`docs/catalogue-fixes1-20261116.md`) |
| Model and vectors | Unchanged: same DINOv2-small model, 384 dims, float16. Base vectors are byte-for-byte the base file; no existing row was re-embedded |
| Row order | `card_index.f16.bin`, `card_index.ids.txt` and `card_index.meta.tsv` have the same order; the base rows come first unchanged, the 13 added rows at the end |

Built with `api/scripts/on_phone_index/extend_index.py` from `columns.json` (`phone_columns.py`) and
`names.json` (`build_phone_names.py`); tests in `api/tests/test_phone_index_extend.py`.

## Format

`card_index.meta.tsv` keeps its ten columns in place (the first six, `id name number printed_number set_total
language`, exactly as before) and appends five:

`id name number printed_number set_total language promo_code row_kind alt_name printing_family` +
**`release_year hp printing reprint_of name_en`**

Current app builds read the first six columns and ignore the rest. Only two existing columns change value:
`name` (Japanese names, below) and `set_total` (filled where it was empty), and `alt_name` follows `name`.

| Column | en (22,694 rows) | ja (23,929) | zh-tw (2,260) | Source |
|---|---:|---:|---:|---|
| `set_total` | 99.0% | 82.0% (was lower: 3,871 filled) | 100% | Unchanged, plus Japanese totals read from the cards' own reference images (OCR, two agreeing reads, no conflicting read) |
| `release_year` | 94.6% | 77.5% | 0% | TCGdex set release dates; Limitless for Japanese sets TCGdex lacks. Empty for multi-year promo sets |
| `hp` | 79.0% | 43.9% | 0% | TCGdex card HP, Pokémon only (Trainers and Energies stay empty) |
| `printing` | 100% | 100% | 100% | regular 42,834, promo 4,245, prize_pack 983, other 732, stamped 89 |
| `reprint_of` | 4.4% | 0.0% | 0% | For prize_pack and stamped rows: the regular card of the printing family |
| `name_en` | (name is English) | 100% | 0% | The catalogue's English title |

## 1. Names

`name` now carries the Japanese name for Japanese rows, with English in `name_en` (and `alt_name`):
Japanese-script names 92.1% of Japanese rows.

| Rule | Rows | What |
|---|---:|---|
| Held names | 2,600 | Japanese names matched by NAMES3 but held back from the server catalogue (the server's printing tie-break needs them held; the phone does not) |
| Species fill | 3,224 | Latin-only name whose English title is one species (with at most one prefix/suffix such as `ex`, `V`, `わるい`): built from the official species table |
| Plainly wrong names fixed | 504 | Machine transliterations in e-Card, neo, PCG, VS and web sets, e.g. `ja:neo3-044` 猟犬 -> ヘルガー, `ja:E1-065` 金星 -> フシギバナ |
| Kept for review | 54 | Japanese name fails the species check but cannot be rebuilt safely (owners, forms, tag teams, delta species): unchanged, listed in `names.json` |
| Latin kept | 1,883 | Trainers, Energies and titles that are not one species: no source for a Japanese name |

## 2. The 13 added Japanese cards

Each was in the catalogue with an image but out of the index as a printing alternative: its pad cosine to an
already indexed card is at least 0.95, the rule that keeps near-identical reprints from competing on the server.
The phone index carries them so it can name the exact printing; their vectors were embedded from the stored
reference image with the same model (`added/embed_added.py`, which reproduces existing catalogue vectors exactly).

| Added | Nearest indexed twin | Cosine |
|---|---|---:|
| `ja:S6a-047` Umbreon V | `ja:S8b-100` | 0.987 |
| `ja:SM10a-032` Garchomp & Giratina GX | `ja:SM12a-099` | 0.984 |
| `ja:S1W-054` Ordinary Rod | `ja:S8b-139` | 0.982 |
| `ja:S5a-007` Blaziken V | `ja:S8b-019` | 0.985 |
| `ja:S4a-108` Crobat V | `ja:S8b-099` | 0.985 |
| `ja:S1a-070` Twin Energy | `ja:S7D-067` | 0.992 |
| `ja:XY1-By-014` Blastoise EX | `ja:XYP-076` | 0.959 |
| `ja:XY1-Bx-022` Pikachu | `ja:MMBS-011` | 0.999 |
| `ja:S5a-044` Kubfu | `ja:S8b-091` | 0.975 |
| `ja:BW5-Brn-037` Rayquaza EX | `ja:MDB-025` | 0.967 |
| `ja:BW1-Bw-037` Zoroark | `ja:MDB-023` | 0.957 |
| `ja:SP-125` Pikachu | `ja:SM9a-014` | 0.958 |
| `ja:SMP-179` Pikachu | `ja:SMP-044` | 0.957 |

## 3. Cards absent from the index

| Language | Absent | Why |
|---|---:|---|
| English | 2,480 | Pokémon TCG Pocket (digital): out of recognition by owner decision (2026-11-14) |
| English | 35 | No image. 34 duplicate rows that already have an image and vector; `en:det1-25` has no English print |
| English | 15 | Image but no vector: printing alternatives of indexed cards |
| Japanese | 4,311 | Image but no vector: printing alternatives (pad cosine >= 0.95 to an indexed card) and older-era cards held from the index; they keep features for printing choices on the server |
| Japanese | 297 | No image anywhere we may use (`docs/catalogue-missing-cards-20261116.md`); an image batch (IMG1) is finding images for part of them |

Chinese rows: zh-tw is in the index marked `language`; zh-cn has no images.

## 4. Japanese set totals

3,871 Japanese rows got a `set_total`: 184 sets whose total was read on the cards' own reference images
(server OCR; a total is accepted only when at least two reads whose numerator is the card's own number agree and
none disagrees). 13 sets had conflicting reads and were left empty (e.g. `HSp`, `SVI`, several deck kits).
Promo sets stay without a total.

## 5. The `held_from_index_v2` marker (198 photos)

198 test photos carry the label `held_from_index_v2: older-era or Charizard reprint; replay 2026-11-07 showed
vintage photo regressions` next to their expected card. It dates from the second Japanese recovery release
(JAREC2, 2026-11-07), which held older-era cards out of the server index because a replay showed vintage photos
getting worse; the marker told the gate that a photo of such a card could not be matched then. The held cards
were given vectors in later releases (JAREC6b onward): today 198 of their 200 expected cards are in this index.
The two that are not, `ja:XY-012` (photo `dev2-ja-modern-035`) and `ja:XYC-12` (`dev2-ja-modern-079`), are
printing alternatives of indexed twins. The marker is now history and could be dropped from the labels.

## Not done

- Not published or deployed, as asked. The staging manifest serves `c7bdbcae...` and would refuse this
  folder anyway: it has 13 rows that the server snapshot does not.
- 54 names are left for review (listed in `names.json`), and 13 sets have conflicting total reads.
