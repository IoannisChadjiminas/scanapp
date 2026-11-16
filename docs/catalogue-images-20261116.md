# IMG1: reference images for image-less rows (2026-11-16)

Images for catalogue rows that had none, on top of FIXES1R. Staging only; production is not touched. The model is
unchanged and no existing vector was recomputed: 4 vectors were added, nothing else moved.
Per-card record (source, image URL, decision, or the reason a row has no image): `docs/catalogue-images-20261116.tsv`.

## Scope (counted on FIXES1R)

| Group | Rows | Imaged | No image |
|---|---:|---:|---:|
| Japanese, `has_image=0` | 297 | 135 | 162 |
| English, `has_image=0` (no Pocket) | 35 | 0 | 35 |
| **Total** | **332** | **135** | **197** |

Out of scope, as briefed: Pocket, zh-cn, zh-tw, and the 4,395 Japanese printing alternatives with an image but no vector.

English rows with an image but no vector (15): all are deliberate and stay as they are. `en:me06-132` is a printing
alternative (pad cosine >= 0.95); the 11 `en:mfb-*` rows and `en:svp-500` are display-only images of the source
releases (`verified_source_image_display_only`); `en:tk-ex-latia-8`, `-9` are the Latias-deck twins of the Latios deck
cards (printing alternatives); `extra-mew-ex-205-metal` lost its vector in CLEANUP1 (identical to `en:sv03.5-205`).

## What was added

| Source | Rows | Size | Covers |
|---|---:|---|---|
| pokemon-card.com (official card search) | 47 | 748 x 1044 or larger | SMB, SMN, SMC, MMBS, SP2 and SLL basic energies; SP-099 and the 12 S-P rows with a printed number (006, 008, 009-016, 032, 044) |
| Limitless JP | 4 | 736 x 1024 (HS-041, -042: the 460 x 640 copy, the large one fails the blur gate) | HS-040..043 Beginning Set energies (HS mark) |
| PokeDataVault | 53 | 286 x 400 | DP2-102, Entry Pack, Dialga and Palkia LV.X decks, Dialga & Palkia decks, Master Kits, Quick Starter sets, half decks, deck-kit energies, 2006 Energies |
| pooka.app | 22 | about 320 x 450 | DP3-015, DPP-109, Vending Machine 3 (LV.25/26/39/40 read on the card), Sky-Splitting Deoxys, gym-deck trainers, McDonald's holofoil energies, Misc. Promos 095-097 |
| BinderBoss | 9 | 246 x 341 to 734 x 1022 | Misc. Promos 168-170, 186, 187 (Battle Neo No. 1/2/3 Trainer), 231-233 (Victory Medal, Victory Ring), 296 (Zoroark and Legendary Pokemon) |

Every image was looked at by eye on contact sheets against the row's name and, where printed, its number or set mark
(by the acquisition workers and again by this session). No Cardmarket photo, no listing photo. Nothing is mirrored to
the CDN (the CDN is for TCGdex art only).

Treatment (`build_image_batch.py`, rules as in the earlier batches): **4 scannable** (`ja:SP-099` Detective Pikachu,
`ja:SP-u12` Eevee 044/S-P, `ja:SP-u63` Scorbunny 006/S-P, `ja:SP-u65` Sobble 008/S-P) and **131 printing
alternatives** (97 older era; 34 modern ones with pad cosine >= 0.95 to an indexed Japanese card, all energies and
`SP-u45` Morpeko -> `SAl-009` 0.957). Names and titles are not changed.

One image file serves one row. Where the same printed card sits in several products, the image went to one row and the
others are listed with "same printed card and image as ..." (energies: the `EN06` row; deck trainers: the Dialga deck /
first gym deck; SMK energies -> SMN).

## Rows still without an image (197)

| Reason | Rows |
|---|---:|
| English duplicates of rows that already have image and vector: `en:exu-*` = `en:ex10-unown-*` (28), `en:xya-24a/28a/54a/55a/92a/107a` = `en:xy4-24a`, `en:g1-28a`, `en:xy10-54a`, `en:xy3-55a`, `en:xy6-92a`, `en:xy9-107a` | 34 |
| Same printed card as another row in this batch (image went to that row) | 32 |
| Ambiguous print: the product has two or more prints with the same name and the row does not say which | 59 |
| No source shows the card for that product (plain energies of VS packs, gym decks, McDonald's non-holo; SMP-447/452/453/454; Extra Regulation Box; non-Japanese Pikachu World Collection prints; unnumbered BW promos), or the source blocked access (TCG Collector, Bulbagarden: Cloudflare, not bypassed) | 71 |
| `en:det1-25` Lt. Yoshida: no English print exists (English set has 18 cards); the card is `ja:SMP2-025` | 1 |

Ambiguous rows worth an owner decision (the two candidates are known):
`ja:SP-u01` Bede 027 or 056/S-P, `u31` Hop 005 or 058, `u49` Pikachu 001 or 024, `u52` Poke Ball 019 or 054, `u57` Potion
017 or 051; `ja:HSP-30` Potion and `HSP-34` Poke Ball (30/30a/30b, 34/34a/34b differ only by deck symbol).

## Catalogue issues seen (not changed here)

- `ja:SP-123` "Lance's Charizard V": S-P 123 is Pikachu VMAX; no Japanese Lance's Charizard V promo is known. Likely a bad row.
- `ja:DPP-109` "Giratina (Origin Forme)": the card at 109/DP-P is Real World's Giratina (Altered Forme art). Name needs fixing.
- `ja:jr-mega-evolution-energies-009..016`, `jr-scarlet-violet-energies-017..024`: Japanese SV/MEGA basic energies carry no
  number; these numbers look English, and their sibling rows `-001..016` carry English pokemontcg.io images.
- `en:det1-25`, the six `en:xya-*` and 28 `en:exu-*` rows are TCGdex duplicates; removing them needs the owner's OK.

## Build

| Item | Value |
|---|---|
| Parent | `pokesingle_completion_20261116_fixes1r`, `PS-CATALOGUE-EN-JA-FIXES1R-20261116` (features `20261116-fixes1r` `4e9d64ec...`, artwork `20261116-fixes1`) |
| Candidate | `pokesingle_completion_20261116_img1`, `PS-CATALOGUE-EN-JA-IMG1-20261116`, inactive |
| SQL | `prepare_sql_images.py`, 311 statements, sha256 `a602ea03c6d6d99ef2f978903cbe1497333b387c3f855c42f26a360358be17f5` |
| Images | `/data/reference-images/ja-20261116-img1` (135 JPEG q95) |
| Features | `/data/reference-features/20261116-img1`, manifest sha256 `d6a514059c6191e321e47f1ff865e96aa9082ec1360684449dc8c9e29404f6d5` (55,653 available of 62,074; same on this Mac) |
| Artwork | `/data/artwork/20261116-img1`, embeddings `27f5423b...`, records `580e0722...`, manifest `081e80f8...` (37,358 regions; same on this Mac) |
| Vectors | pad 48,870 -> 48,874 |
| Work files | `data/catalogue-gaps/images-20261116/` (worklist, source folders, `accepted.jsonl`, `release-img1-20261116/`, `run_gate.sh`) |

Script changes: `build_image_batch.py` takes each row's language from its id (one batch may mix `ja:` and `en:`; twins are
looked for within that language) and keeps a per-row `source_kind`; `prepare_sql_images.py` writes that per-row
`source_kind` and skips the provenance update for rows that have no completion-source row; new
`assemble_image_batch.py` turns accepted candidates into `fill.jsonl`, `set-registry.json` and signature rows.

## Gate

(pending: FIXES1R, the parent, is still gating)

## Switch

Not switched (as briefed). A switch changes these lines of `/etc/scanapp-staging/catalogue-release.env`:

```
PLANETSCALE_SCHEMA=pokesingle_completion_20261116_img1
PLANETSCALE_IMPORT_ID=PS-CATALOGUE-EN-JA-IMG1-20261116
REFERENCE_FEATURES_DIR=/data/reference-features/20261116-img1
ARTWORK_BUNDLE_DIR=/data/artwork/20261116-img1
```
