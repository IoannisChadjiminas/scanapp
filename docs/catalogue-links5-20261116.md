# LINKS5 to 5M: Cardmarket links for Japanese rows, and 12 crossed links fixed (2026-11-16, switched 2026-11-17)

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

**LINKS5G to 5J (2026-11-17): the owner asked to try again, then for a next round on the Japanese rows.** 261 links,
one line per row in `docs/catalogue-links5g-j-picks-20261117.txt`.

- **LINKS5G, the 5 English BREAKpoint and Furious Fists rows** (`en:xy3-12`, `-14`, `en:xy9-1` to `-3`). Read again in the
  owner's Chrome, one page at a time. Each has two versions on Cardmarket; `V2` carries a League, Championship or Staff
  stamp, `V1` is the plain set card, which is what our rows are (`"normal": true`, TCGdex set image). All five take `V1`.
- **LINKS5H, 118 Japanese rows whose product has a fuller name.** In the set's expansion, exactly one free product has the
  row's number, but its name differs in more than spelling: `Mewtwo` = `MMewtwo EX (CP4 051)`, `Burmy` =
  `Burmy Plant Cloak Lv.11`, `Boss's Orders` = `Boss's Orders - Ghetsis`, the V Starter Deck `V` cards, the Extra
  Regulation Box `EX` cards, the PLAY Gold Stars. Every pair was checked by eye against our own reference image (the
  card's name, form, professor or cloak on the picture). Rows with our own `u..` numbers were left out. All 118 agreed.
- **LINKS5I and 5J, 98 unnumbered XY promos** (`ja:XYP-299` onward carry our own numbers; Cardmarket lists them without a
  number, as `V1`, `V2`, ...). Matched by eye between Cardmarket's gallery pictures and ours: 46 promo energies (Lawson,
  Gym Events 2014 / 2015 / 2016, 20th Anniversary Festa, BREAK gold, Charizard Mega Battle), 15 Gym Badges (by gym
  leader), 9 Pikachu, 3 Victory Rings (Battle Festa, no year), 3 Champions Festival (Worlds 2014 / 2015 / 2016),
  2 Pitch's Pikachu, 2 Crobat BREAK (Gym stamp / Mega Battle stamp) and 18 one-of-a-kind promos.
- **LINKS5J, 40 Vending Machine Series cards.** The three series share Cardmarket's `Expansion-Sheet`. A card is linked
  when its name occurs once across our three vending sets and once on the sheet.

Left out on the way: `ja:XYP-299` (titled Team Flare Grunt, the image is Double Dragon Energy), `ja:XYP-362` (same image
as `-367`), `ja:XYP-323` (another Greninja than Cardmarket's), `ja:XYP-300` Inkay and `-347` Toys "R" Us Pikachu (Cardmarket's
products are oversized cards), and 12 vending cards with two versions each (Mewtwo, Graveler, Machoke, Omanyte, Kadabra,
Haunter): Cardmarket asked for its check on almost every page and they were not read.

**LINKS5K to 5M (2026-11-17): the 12 two-version vending cards, deck-kit halves and copy sets.** 115 links. Fix files
in `data/catalogue-gaps/ja-links-20261116/` (`fixes-vending-two-version-20261117.json`, `fixes-decks-20261117.json`,
`fixes-copies-decks-20261117.json`), each row with its evidence.

- **LINKS5K, the 12 vending cards with two versions** (Mewtwo, Graveler, Machoke, Omanyte, Kadabra, Haunter). Read in the
  owner's Chrome after they passed Cardmarket's check, one page about every 15-20 seconds. `V1` is the series 1 or 2 card,
  `V2` the series 3 card (told apart by the picture and the series mark): for example `Mewtwo-V1-EXS` -> `blue-u16`,
  `Mewtwo-V2` -> `green-u27`.
- **LINKS5L, 46 deck-kit cards.** Six expansion pages crawled the same slow way (160 products: Magmortar vs Electivire,
  Mewtwo vs Genesect, Entry Pack 08, Bastiodon the Defender, Rampardos the Attacker, McDonald's Original Minimum Pack).
  32 Mewtwo vs Genesect cards by number and half, 14 Magmortar vs Electivire half-deck cards whose name is unique in
  their half.
- **LINKS5M, 57 copy-set rows sharing a link.** Some of our sets hold the same cards as another set: a combined deck set
  and its own half decks. The owner approved on 2026-11-17 ("Yes, allow sharing") that such a copy may carry the link of
  the row it copies. A row takes the link only when its picture is at least 0.95 similar (DINOv2 pad) to an already
  linked row, the English titles are the same, every such twin carries the same single link, it is not a basic energy,
  and the pair is a combined set and its half decks: Dialga & Palkia LV.X combined (20), Bastiodon & Rampardos combined
  (19), Magmortar vs Electivire combined (10), Heatran vs Regigigas halves (7), Palkia LV.X deck (1). 146 rows passed
  the picture rule; the other 89 are reprints in a different product (Tropical Mega Battle against VS1, MMBP against
  HXY, `jr-miscellaneous-decks` against the gym decks) and were left out, since the link would show another product's
  price.
- `prepare_sql_fixes.py` now takes `shares_link_of`: a fix may reuse a link already in use only when it names the row
  that holds that same link (and that row is not in the same batch); the SQL then checks that each shared page gains
  exactly the approved rows. Tests in `api/tests/test_prepare_sql_fixes_shared.py`.

Cardmarket blocked the session twice: once after a few background page fetches ("Access denied"), once after quick
page loads (rate limit). Loading one page about every 15-20 seconds, in the owner's browser after they passed the
check, worked. No product photos were saved.

Titles found wrong (link columns only change, so not fixed here): `ja:SVM-042` / `-043` are Voltorb / Electrode (swapped),
`ja:XY-037` is Zubat (not Golbat), `ja:XY11-Br-030` is Spiritomb (not Lucario).

## Build

| Item | Value |
|---|---|
| LINKS5 | `pokesingle_completion_20261116_links5`, `PS-CATALOGUE-EN-JA-LINKS5-20261116`, parent IMG1; `prepare_sql_fixes.py`, 800 cards, SQL sha256 `e89b42170675d6b9b3ab7f7e44f0e4d05e9150345cf5e2f5aba83cbc2ed4b7dc`; links 48,310 -> 49,110 |
| LINKS5B | `pokesingle_completion_20261116_links5b`, `PS-CATALOGUE-EN-JA-LINKS5B-20261116`, parent LINKS5; 128 cards (127 links, 1 cleared), SQL sha256 `f19e87b2eead99c3562bf8d3c4addb5c6a56b9ed80905faa5a7892da7c2f47f5`; links 49,110 -> 49,236 |
| LINKS5C | `pokesingle_completion_20261116_links5c`, `PS-CATALOGUE-EN-JA-LINKS5C-20261116`, parent LINKS5B; 267 cards, SQL sha256 `d1bda60a696ecfd5917867e2a577fab0d8a3ce4db554a159a7dd91a7bc4ef45f`; links 49,236 -> 49,503 |
| LINKS5D | `pokesingle_completion_20261116_links5d`, `PS-CATALOGUE-EN-JA-LINKS5D-20261116`, parent LINKS5C; 52 cards, SQL sha256 `532b68af5104376140164188c1c60b8fd9fd5a6cf2bc779dc9e5997b0d5771bc`; links 49,503 -> 49,555 |
| LINKS5E | `pokesingle_completion_20261116_links5e`, parent LINKS5D; 125 cards (12 cleared, 113 linked), SQL sha256 `c4a6a75a60b2a1a999c8351169c9c36577446d7e58875cafb2b1ac4feb0b932a`; links 49,555 -> 49,656 |
| LINKS5F | `pokesingle_completion_20261116_links5f`, `PS-CATALOGUE-EN-JA-LINKS5F-20261116`, parent LINKS5E; 7 cards, SQL sha256 `6c0bc7da6b5f94c37198d83abf1daa9a2a5e46cd870e28db44cd83b45856a38f`; links 49,656 -> 49,663 |
| LINKS5G | `pokesingle_completion_20261116_links5g`, `PS-CATALOGUE-EN-JA-LINKS5G-20261116`, parent LINKS5F; 5 cards, SQL sha256 `ad5dbe92322de2c75987b4fd69982b6b5336adac3f8fa3be7ef8361a9c3ee364`; links 49,663 -> 49,668 |
| LINKS5H | `pokesingle_completion_20261116_links5h`, `PS-CATALOGUE-EN-JA-LINKS5H-20261116`, parent LINKS5G; 118 cards, SQL sha256 `8578c1dc6cd9a2b05ba71558aa9a8f32cb0e342e75ac71cd3e1650e91f993438`; links -> 49,786 |
| LINKS5I | `pokesingle_completion_20261116_links5i`, `PS-CATALOGUE-EN-JA-LINKS5I-20261116`, parent LINKS5H; 91 cards, SQL sha256 `b308d65dc4a4c6f82fcd06e0461e94610b7b736b3479f9e30979270934b7faa8`; links -> 49,877 |
| LINKS5J | `pokesingle_completion_20261116_links5j`, `PS-CATALOGUE-EN-JA-LINKS5J-20261116`, parent LINKS5I; 47 cards, SQL sha256 `3238fc047d5209e9524052527189d78c4c2dfb4defca222e6aefc759d09523a4`; links -> 49,924 |
| LINKS5K | `pokesingle_completion_20261117_links5k`, `PS-CATALOGUE-EN-JA-LINKS5K-20261117`, parent LINKS5J; 12 cards, SQL sha256 `5e41508e4f426d053a6d009c71bd07a56b8da332b9e532a38414a320a10afccf`; links -> 49,936 |
| LINKS5L | `pokesingle_completion_20261117_links5l`, `PS-CATALOGUE-EN-JA-LINKS5L-20261117`, parent LINKS5K; 46 cards, SQL sha256 `827b28bfa7dbb4bac43f7cbc3e336d49b998e809e83e9ab7036c261cfb830c2e`; links -> 49,982 |
| LINKS5M (served) | `pokesingle_completion_20261117_links5m`, `PS-CATALOGUE-EN-JA-LINKS5M-20261117`, parent LINKS5L; 57 cards (shared links), SQL sha256 `f7bdb7b97e027b254b4d5d640e1403446c543a6dd2911be6c2d3c6f2dc8d577b`; links -> 50,039; pages linked from more than one row 36 -> 93 |
| Read back | all validated, inactive |
| Bundles | features `20261116-img1`, artwork `20261116-img1` (unchanged) |

Work files: `data/catalogue-gaps/ja-links-20261116/` (`matches.json`, `fixes.json`, `sql/`, `run_gate.sh`, `out/`).

## Gate

LINKS5M: 1,891 photos replayed against LINKS5M (same setup), scored against LINKS5F's accepted run: every panel
unchanged (dev 636/3/663, dev2 232/0/238, dev3 938/0/963), 0 right -> wrong, 0 expected cards lost, 0 changed
answers; `gate.json` identical to LINKS5J's. The LINKS5K and 5L runs were stopped part-way when the next step was added.

LINKS5J: 1,891 photos replayed against LINKS5J (same setup), scored against LINKS5F's accepted run: every panel
unchanged (dev 636/3/663, dev2 232/0/238, dev3 938/0/963), 0 right -> wrong, 0 expected cards lost, 0 changed
answers. The LINKS5G and 5I runs were stopped part-way when the next step was added.

LINKS5F: 1,891 photos replayed against LINKS5F (local docker, image `scanapp-api-staging:24856ba9`, 3 lanes, features and
artwork `20261116-img1`), scored against IMG1's accepted run with `score_gate.py` and the corrected labels.

| Panel | Photos | Right first | Wrong first | Right offered |
|---|---:|---|---|---|
| dev | 681 | 636 -> 636 | 3 -> 3 | 663 -> 663 |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 238 -> 238 |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 963 -> 963 |

0 right -> wrong, 0 expected cards lost, 0 changed answers. Only link columns changed, so this was expected.
The gates on LINKS5 to 5D were stopped part-way when the next step was added; only LINKS5F, which holds all of
them, was replayed in full.

## Switch

LINKS5M, 2026-11-18: `catalogue-release-switch.sh apply`, `RELEASE_NAME=catalogue-links5m-20261117`, release file
`/root/catalogue-links5m-20261117.env` (only the schema and import lines changed, checked by diff). After: health ok,
ready, import LINKS5M, restarts 0, no OOM; all 115 new links read back from `/api/v1/cards/{id}`. Rollback
`/etc/scanapp-staging/catalogue-rollback/catalogue-links5m-20261117` (rollback file points to LINKS5J). Approval: the
owner asked for items 1 and 4 ("lets start with 1 ... and then do 4") and approved sharing ("Yes, allow sharing"), on the
plan to switch if nothing went from right to wrong.

LINKS5J, 2026-11-17: `catalogue-release-switch.sh apply`, `RELEASE_NAME=catalogue-links5j-20261117`, release file
`/root/catalogue-links5j-20261117.env` (only the schema and import lines changed, checked by diff). After: health ok,
ready, import LINKS5J, restarts 0, no OOM. Rollback `/etc/scanapp-staging/catalogue-rollback/catalogue-links5j-20261117`
(rollback file points to LINKS5F). Approval: the owner asked for the next round ("Yes, next round", then "proceed")
on the plan to switch if nothing went from right to wrong.

LINKS5F:

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-LINKS5F-20261116`, schema `pokesingle_completion_20261116_links5f`, features and artwork `20261116-img1` |
| Approval | the owner chose "Everything possible", then "one photo check and switch", and asked to "do everything and finalize it" |
| How | `catalogue-release-switch.sh apply`, `RELEASE_NAME=catalogue-links5-20261116`, release file `/root/catalogue-links5-20261116.env` (a copy of the live file with only `PLANETSCALE_SCHEMA` and `PLANETSCALE_IMPORT_ID` changed, checked by diff) |
| After | health ok, ready, import LINKS5F, restarts 0, no OOM |
| Rollback | `/etc/scanapp-staging/catalogue-rollback/catalogue-links5-20261116` (rollback file points to IMG1) |

## Phone index

LINKS5M: unchanged, v4 `0a46b0abe0f8db7db415ffef544a1249a295965fb0bd848bb06d26c8831478e2` (published on 2026-11-17,
`docs/phone-index-v4-20261117.md`), 51,625 rows, five files. The manifest answers 200 in public after the switch.

LINKS5J: unchanged, `32f22e3f...`. Only link columns changed (no vector, image or row); the server accepted the
index for the LINKS5J snapshot and the manifest answers 200 inside the container and in public. Not rebuilt
locally this time.

LINKS5F: unchanged: `32f22e3fa19e49e43c0d2f940ff00c03b2a5201e0ae8d4bd9de57e54ac3bda0b`, 48,874 rows. A local snapshot
export of LINKS5F (read-only role: 62,074 cards, 49,663 links) has the same pad vectors byte for byte, and
`export_index.py --families` on it rebuilt the same version with all four files identical. Cardmarket links are
not in the phone index. Nothing was published: the manifest kept answering 200 across the switch, the public
ids file matches, and a ranged request on the vectors returns 206.

## Going back

To LINKS5J, on the staging host, from the code directory:

```
CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-links5m-20261117 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback
```

Before LINKS5M:

```
CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-links5-20261116 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback
```

That goes back to LINKS5F. To go back further, run it again with `RELEASE_NAME=catalogue-links5-20261116` (to IMG1).
The phone index stays as it is: IMG1, LINKS5F and LINKS5J use the same one.

## Still without a link (1,238 Japanese rows after LINKS5M)

After LINKS5M: 1,238 Japanese rows without a link. Mostly: copies of cards in another product that were kept apart
(Tropical Mega Battle, MMBP, `jr-miscellaneous-decks`, `jr-entry-pack` against DP1), `jr-miscellaneous-promos` (298)
and `jr-miscellaneous-decks` (73), promo versions Cardmarket lists as `V1`.. (XYP 61, SMP 41, BWP 29, M-P 25),
basic energies, and sets Cardmarket does not list (quick starter gift sets, 64).

Japanese rows without a link: 1,609 on LINKS5F, 1,353 on LINKS5J (of 28,537). What is left after 5J: the 12
two-version vending cards and 5 XY promos above, `jr-miscellaneous-promos` (a grab-bag set with no matching
Cardmarket expansion), deck-kit halves (the combined sets are linked), and cards Cardmarket does not list.

The breakdown below is the matcher's run after LINKS5D (1,721 rows), kept for the reasons:

| Why | Rows |
|---|---:|
| Sets with no linked row that could not be mapped or matched (see LINKS5C above) | 759 |
| No product with that number and name in the expansion (after LINKS5D: 316 have no product with the number at all; the rest differ in more than spelling) | 645 |
| Name-only in an expansion shared by several of our sets (vending machine series, deck-kit halves) | 156 |
| Several products fit (Cardmarket versions `V1`..`V5` with the same number) | 121 |
| The set's rows link to several expansions | 41 |

The rows with several
fitting versions need someone to tell the versions apart on Cardmarket.
