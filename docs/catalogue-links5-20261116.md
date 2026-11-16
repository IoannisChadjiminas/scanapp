# LINKS5 to 5F: Cardmarket links for Japanese rows, and 12 crossed links fixed (2026-11-16)

Of the 2,966 Japanese rows without a Cardmarket link on IMG1, 1,245 get one (799 in LINKS5, 127 more in LINKS5B, 267 in LINKS5C, 52 in LINKS5D),
plus the English `en:mep-120`
held over from EN1 (`docs/catalogue-en1-findings-20261116.md` on `claude/image-batch-20261116-ffd17e`). The
owner asked for "Japanese links" after IMG1. Staging only. Only link columns change: no vector, image,
feature or artwork record, so IMG1's bundles are reused.

## How the links were found

Offline, from the crawl of Cardmarket expansion pages already in the catalogue (`cardmarket_products`,
crawled 2026-09-18/19), with `api/scripts/ja_set_recovery/match_crawl_links.py`:

- A set's Cardmarket expansion is the one its already-linked rows point to (71 sets have such an expansion
  and a match).
- A crawled product counts as free when no row links its page.
- **Numbered products (290 rows):** the product's printed number, e.g. `(XY-P 170)`, equals the row's number,
  and the product's English name equals the row's English title, with exactly one such product.
- **Unnumbered products (509 rows, mostly DP1-DP3, Temple of Anger, Cry from the Mysterious, Entry Pack 08):**
  the English name, ignoring `Lv.`, is unique among the expansion's free products and among the set's unlinked
  rows. This applies only when no other of our sets links into the same expansion (the vending machine series
  share `Expansion-Sheet`, so they are left out).
- A page that two rows would take is dropped.

**LINKS5B: the full promo lists.** Cardmarket's list pages stop at 300 results, so the stored crawl held only 300
products of each of the big promo expansions. With the owner's Chrome (the owner passed the Cloudflare check;
2026-11-16), every list page of XY Promos, Sun & Moon Promos, Sword & Shield Promos and Scarlet & Violet Promos
was read twice, sorted by number ascending and then descending, which together reach up to 600 results. The
four lists came out at 412, 422, 354 and 304 products, all under 600, so each is complete. Pages were read
about 1.2 s apart. Cardmarket answered 429 at the end of the Shiny Treasure ex list, and the read stopped there.
Shiny Treasure ex (10 rows) and Start Deck 100 (2 rows) were not read. Saved as `crawl-promos-20261116.json`
and given to the matcher as its third argument. This added 127 links (95 Sun & Moon promos, 32 XY promos).
It also cleared the LINKS5 link of `ja:XYP-065` Hawlucha: the full list has two Hawlucha (XY-P 065) products
(`Hawlucha-V1`, `-V2`), so the match was not unique.

**LINKS5C: sets with no link yet, mapped by hand.** 37 sets (1,026 rows) had no linked row, so no expansion to
search. The owner asked to map them ("ok lets do", 2026-11-16). Cardmarket's own expansion list (794
expansions, read from the Singles page's expansion menu: `cm-expansions-20261116.json`) gave these pairings
(`set-map.json`). The full list pages of each were read the same way (`crawl-products-20261116.json`).

| Our sets | Cardmarket expansion | Linked |
|---|---|---:|
| `SD` V Starter Decks | V Starter Decks | 115 |
| `jr-heatran-vs-regigigas-deck-kit` | Heatran vs Regigigas Deck Kit | 20 |
| `jr-dialga-lv-x-constructed-standard-deck`, `jr-palkia-...` | Dialga / Palkia LV.X Constructed Standard Deck | 15 + 15 |
| `jr-mew-lucario-gift-box-*` (5 decks) | Gift Box Mew • Lucario | 60 |
| `jr-master-kit-*` (3 decks) | Master Kit | 42 |

Matched with `api/scripts/ja_set_recovery/match_mapped_sets.py`: same English name (Lv. ignored), exactly one
product. For the starter decks, gift box and master kit, whose numbers are the printed deck positions, the
product's number must also agree (Mew and Mightyena share the `M` suffix on Cardmarket; name plus number tells
them apart). A product two rows would take is dropped.

Not linked, with the reason:
- `jr-miscellaneous-decks` (73) duplicates the six Kanto gym deck sets (`jr-nivi-city-gym-deck` ...), whose rows
  already hold those products. Likely duplicate rows, like the moonlit-pursuit set was.
- Pikachu World Collection, Scarlet & Violet Energies, Mega Evolution Energies: Cardmarket lists several products
  with the same name and number, so nothing is unique.
- `jr-miscellaneous-promos` (298) spreads over many promo expansions with our own numbering.
- The yearly energy sets `EN*`, the Neo Premium Files, the Quick Starter Gift Sets, Tropical Mega Battle and the
  original Entry Pack: no matching expansion on Cardmarket. The combined half-deck and deck-kit sets duplicate
  their halves.

**LINKS5D: same number, spelling differs.** The owner asked to add these ("Yes, add them"). With
`api/scripts/ja_set_recovery/match_spelling_links.py`, the products with the row's printed number are taken, and
exactly one must have the same name after spelling is evened out: `M Rayquaza-EX` = `MRayquaza EX`,
`Basic Fire Energy` = `Fire Energy`, `NidoranF` = `Nidoran [F]`, the movie mark `[M]` and `Lv.` ignored, our
`(Vaporeon artwork)` / `(Normal Forme)` notes ignored. All 57 pairs were read by eye: M-EX cards, the L-P basic
energies, the Movie Commemoration Random Pack, the DPt-P `[GL]` / `[FB]` cards, the Eevee GX artworks and the
Sky-Splitting Deoxys formes.
- 5 were left out: `ja:XY3-012`, `-014` and `ja:XY9-001` to `-003`. Their Japanese products (`Rising-Fist/Torchic`,
  `Rage-of-the-Broken-Heavens/Chikorita`, ...) are held by the English rows `en:xy3-12`, `en:xy3-14` and
  `en:xy9-1` to `-3`.
- Pairs that differ in more than spelling were not taken: `Mewtwo` against `MMewtwo EX`, `Shaymin` against
  `Shaymin EX`, `Golbat` against `Zubat`, `Professor's Research` against a named professor.

**LINKS5E and 5F: the owner asked to "finalize with all the links", everything possible.**

- **Several versions with the same number (98 rows).** Cardmarket lists deck-kit cards once per deck (`V1`, `V2`, ...)
  with the same name and number. The gallery view of each list gives every product's image, read in the owner's
  Chrome (`crawl-gallery-20261116.json`; Cardmarket's images load only in the browser and were viewed there, not
  saved).
  - 22 rows by the deck letter in the product code: Quick Construction Packs `pcgGF` / `GR` / `GG` / `GL` / `GP` / `GW`
    = Fighting / Fire / Grass / Lightning / Psychic / Water; Emerald gift box `pcgFD` / `FR` = Deoxys / Rayquaza
    (`version-picks-code.json`).
  - 76 rows by eye, each against our own reference image (`docs/catalogue-links5-version-picks-20261116.txt`, one line per row with what
    decided it): the deck mark's colour or number (Battle Gift Set gold/grey, Beginning Set green/red/blue and deck
    numbers, Family Pokémon Card Game Pikachu mark, Everyone's Exciting Battle silhouettes, Emboar/Togekiss marks),
    holo against non-holo where Cardmarket's second version is its "Holo Version", and promo stamps (XY campaign,
    Pokémon Pan).
  - Left without a link: rows our image cannot decide (`BTV-006`, `BTV-011`, `XYE-017`, `XYE-018`, `XYP-064`), rows
    without a reference image (`HSP-30`, `HSP-34`), and `HSp-030` (the only shown version has another deck mark).
- **Shiny Treasure ex (10 rows):** read again in full; each has one product with its number and name.
  The 2 Start Deck 100 rows' products are already held by other rows and were left.
- **The 12 crossed links.** LINKS5E clears all 12, and the Japanese `ja:XY3-012`, `-014`, `ja:XY9-001` to `-003`
  take the Japanese products the English rows held. LINKS5F then links 7 of the cleared rows to their own
  language's product: `ja:M3-061` Meowth ex (Nihil Zero, m3 061), `ja:M6-107`, `-109`, `-110` (Storm Emeralda,
  m6 107/109/110), and `en:swsh10.5-015` to `-017` (Pokémon GO, PGO 015-017). The 5 English BREAKpoint and Furious
  Fists rows stay without a link: their English products have two versions each, and Cardmarket answered 429 when
  their images were read.

**Found on the way: links crossed between languages** (fixed by LINKS5E and 5F, above). Six Cardmarket expansions are linked from both English and
Japanese rows. Eight English rows hold Japanese-set products: `en:xy3-12`, `-14` (Rising Fist), `en:xy9-1` to
`-3` (Rage of the Broken Heavens), and 3 in Pokémon GO Enhanced Expansion Pack. Four Japanese rows hold
English-set products: 1 in Roaring Skies, 1 in Flashfire, 2 in MEP Black Star Promos. These are fixed by LINKS5E and 5F.

Each link is URL-only, as 142 links already were, with provenance
`verified-cardmarket-firstparty-crawl-exact-expansion-number-name-links5`.

## Build

| Item | Value |
|---|---|
| LINKS5 | `pokesingle_completion_20261116_links5`, `PS-CATALOGUE-EN-JA-LINKS5-20261116`, parent IMG1; `prepare_sql_fixes.py`, 800 cards, SQL sha256 `e89b42170675d6b9b3ab7f7e44f0e4d05e9150345cf5e2f5aba83cbc2ed4b7dc`; links 48,310 -> 49,110 |
| LINKS5B | `pokesingle_completion_20261116_links5b`, `PS-CATALOGUE-EN-JA-LINKS5B-20261116`, parent LINKS5; 128 cards (127 links, 1 cleared), SQL sha256 `f19e87b2eead99c3562bf8d3c4addb5c6a56b9ed80905faa5a7892da7c2f47f5`; links 49,110 -> 49,236 |
| LINKS5C | `pokesingle_completion_20261116_links5c`, `PS-CATALOGUE-EN-JA-LINKS5C-20261116`, parent LINKS5B; 267 cards, SQL sha256 `d1bda60a696ecfd5917867e2a577fab0d8a3ce4db554a159a7dd91a7bc4ef45f`; links 49,236 -> 49,503 |
| LINKS5D | `pokesingle_completion_20261116_links5d`, `PS-CATALOGUE-EN-JA-LINKS5D-20261116`, parent LINKS5C; 52 cards, SQL sha256 `532b68af5104376140164188c1c60b8fd9fd5a6cf2bc779dc9e5997b0d5771bc`; links 49,503 -> 49,555 |
| LINKS5E | `pokesingle_completion_20261116_links5e`, parent LINKS5D; 125 cards (12 cleared, 113 linked), SQL sha256 `c4a6a75a60b2a1a999c8351169c9c36577446d7e58875cafb2b1ac4feb0b932a`; links 49,555 -> 49,656 |
| LINKS5F (served candidate) | `pokesingle_completion_20261116_links5f`, `PS-CATALOGUE-EN-JA-LINKS5F-20261116`, parent LINKS5E; 7 cards, SQL sha256 `6c0bc7da6b5f94c37198d83abf1daa9a2a5e46cd870e28db44cd83b45856a38f`; links 49,656 -> 49,663 |
| Read back | all six validated, inactive |
| Bundles | features `20261116-img1`, artwork `20261116-img1` (unchanged) |

Work files: `data/catalogue-gaps/ja-links-20261116/` (`matches.json`, `fixes.json`, `sql/`, `run_gate.sh`, `out/`).

## Still without a link (1,721 Japanese rows after LINKS5D)

Counts from the matcher's run with the full promo lists:

| Why | Rows |
|---|---:|
| Sets with no linked row that could not be mapped or matched (see LINKS5C above) | 759 |
| No product with that number and name in the expansion (after LINKS5D: 316 have no product with the number at all; the rest differ in more than spelling) | 645 |
| Name-only in an expansion shared by several of our sets (vending machine series, deck-kit halves) | 156 |
| Several products fit (Cardmarket versions `V1`..`V5` with the same number) | 121 |
| The set's rows link to several expansions | 41 |

The rows with several
fitting versions need someone to tell the versions apart on Cardmarket.
