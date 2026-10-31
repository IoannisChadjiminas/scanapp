# Resolve Japanese Cardmarket collection routes

Updated 30 October 2026. This supplements the [execution handoff](japanese-set-recovery-agent-handoff-20261029.md) and supersedes its older two-pilot/334-unmapped counts. Collection stays on the owner's Mac, followed by one combined vector job and release. No staging deployment is needed for discovery or acquisition.

## Current evidence and counts

The local scraper read Cardmarket's [master expansion index](https://www.cardmarket.com/en/Pokemon/Expansions): 800 observed expansion links. All 336 audit groups were checked against that snapshot, including explicit title aliases. This added **198 collection routes**, increasing the seed list from **78 to 276**. These are URLs to collect and reconcile, not 276 completed card inventories or verified printing mappings.

| Routing state | Groups | Next operation |
|---|---:|---|
| Observed collection route in `listing-seeds.json` | 276 | Listing traversal complete; verify codes, numbers, images and variants |
| Subgroup of a shared Cardmarket listing | 36 | Shared pools collected; partition candidates using checklists and exact printing evidence |
| Checklist combines several Cardmarket listings | 3 | Child listings collected; reconcile the union and deduplicate printings |
| Candidate in broader promo, energy or deck pools | 20 | Compare individual cards; pool membership is not established for the whole group |
| No confirmed Cardmarket route after this pass | 1 | 25th Anniversary Creatures Deck: individual product research remains open |
| Total | 336 | No group is classified as unfindable |

The 60 review groups have a dedicated row in `review/remaining-group-routing.csv`. All 59 with candidate pools remain outside the automatic seed list. The review queue contains **29 distinct observed URLs**, of which **16 were already in the 276-route queue**; the other **13 have now been collected**, with pagination. Reuse all cached pages; do not fetch the same listing again for each subgroup.

## Execution status at 29 October 2026

- The local Mac collector has traversed all **276/276** seeded groups: **13,875** group/product records. This is listing acquisition, not verified card coverage.
- The shared-pool collector has traversed **29/29** sources and recorded **1,826** candidate products. Shared-pool rows retain `membership_verified: false`.
- The recovery checklist ledger has **336 complete / 0 pending** checklist jobs (checklist capture stage complete; exact image reconciliation remains a separate stage). Recent checklists include Premium Trainer Box (SMB 18-card list and candidates; six scans acquired, 12 unavailable and /15 source label conflict documented), Sun & Moon Starter Set (59 SMA scans and Cardmarket candidates; PokeNin image alt denominator /68 conflicts with independent /059 checklists), Rockruff Full Power Deck (13 SMP1 cards/20 deck copies; scans 002–013 acquired and 001 image source found but unavailable locally), Tapu Bulu-GX Enhanced Starter Set (21 SMC scans and candidates; 18 Basic Energy copies tracked separately), Ash vs Team Rocket Half Decks (26 SMD scans; 4 unnumbered Energy candidates; duplicate Switch/Poké Ball printings and source metadata discrepancies documented), Solgaleo-GX & Lunala-GX Legendary Starter Set (21 SME cards/scans and Cardmarket candidates; 16 Psychic Energy copies tracked as unnumbered deck contents), Ultra Sun & Ultra Moon Deck Build Boxes (41 SMG candidates; scans 001–012 acquired, 013–041 unavailable from current CDN), GX Starter Decks (131 SMH cards and scans; nine deck pools share the numbered roster), Flareon-GX, Vaporeon-GX & Jolteon-GX Starter Sets (38 SMI scans; Eevee GX art variants kept distinct), TAG TEAM GX Premium Trainer Box (35 SMJ scans; separate Basic Energy inclusions require printing research), Trainer Battle Decks (31 SMK scans; 2 common Energy contents separately recorded), TAG TEAM GX Deck Build Box (29 SMN scans and candidates aligned by code; 9 common Energy types tracked separately), Sun & Moon Family Pokémon Card Game (51 SML scans and candidates aligned by code), TAG TEAM GX Starter Sets (31 SMM scans and candidates aligned by code), Extra Regulation Box (48 numbered candidates aligned; reference scans unavailable from current endpoint; 9 common Energy types held separately), Sword & Shield Premium Trainer Box (24 SB scans), Zacian + Zamazenta Box (7 SP1 scans; 15 common unnumbered Metal Energy contents tracked separately), VMAX Special Set (4 SP2 numbered scans plus 4 foil Energy checklist rows without matching scans), V Starter Decks (127 SD scans; eight cached Cardmarket candidates in the broad pool, exact variants unverified), Venusaur Starter Set VMAX (21 SEF scans), Blastoise Starter Set VMAX (20 SEK scans), Single Strike & Rapid Strike Premium Trainer Boxes (33 SF scans, two box variants need separation), Silver Lance & Jet-Black Spirit Jumbo Pack Set (6 SP3 scans; exact Jumbo product match pending), Inteleon VMAX High-Class Deck (23 SGI scans, one unnumbered), Gengar VMAX High-Class Deck (20 SGG scans, one unnumbered), Eevee Heroes VMAX Special Set (8 product rows, 4 unique numbered scans), Sword & Shield Family Pokémon Card Game (53 unique SH scans, 19 extra numbered candidates, 6 unnumbered Energies), V-UNION Special Card Sets (13 SP5 candidates/scans, quarter-card mapping pending), Zacian & Zamazenta vs Eternatus Special Deck Set (30 SJ scans), 25th Anniversary Golden Box (16 candidates, 15 numbered, no source-specific scans; standard S8a reuse held), Start Deck 100 broad pool (300 products, 299 numbers, 298 scans; per-deck inclusion unverified), VSTAR Premium Trainer Box (30 numbered SK scans, eight unnumbered Energy candidates), Lucario Starter Set VSTAR (22 candidates, 21 SLL scans, one unnumbered), Darkrai Starter Set VSTAR (21 candidates, 20 SLD scans, one unnumbered), Start Deck 100 CoroCoro Comic Version (25 candidates, 24 SN scans, one unnumbered; exact inclusion pending), Zeraora VSTAR & VMAX High-Class Deck (21 candidates, 20 SPZ scans, one unnumbered), Deoxys VSTAR & VMAX High-Class Deck (21 candidates, 20 SPD scans, one unnumbered), VSTAR Special Set (6 SP6 candidates/scans), Charizard VSTAR vs Rayquaza VMAX Special Deck Set (32 candidates, 30 SO scans, 2 unnumbered), Pokémon VS (143 TCGdex records, 151 Cardmarket rows with code conflicts, no scans), Pokémon Web (48 WEB candidates, no independent checklist/scans), ADV Expansion Pack (55 ADV1 candidates, TCGdex metadata only; scans not located), Miracle of the Desert (53 ADV2 candidates; TCGdex lacks card records, scans not located), Rulers of the Heavens (54 ADV3 candidates; TCGdex lacks card records, scans not located), Undone Seal (83 candidates vs TCGdex metadata count 80, no item records/scans), World Champions Pack (108 WCP candidates, no independent roster/image source), SoulSilver Collection (71 L1SS candidates, no roster/image source located), HeartGold Collection (79 L1HG candidates, no checklist/image source found), Reviving Legends (81 L2 candidates; reference scans not found), Lost Link (40 LL candidates, TCGdex confirms count but exposes no cards; scans not found), Clash at the Summit (81 L3 candidates; TCGdex reports 70 but has no records, no scans found), Black & White Promos (248 cached candidates, 229 unique number scans; code gaps #025–031; broad pool still unverified), Reshiram-EX Battle Strength Deck (20 candidates, 18 numbered scans, 2 unnumbered rows; exact image matches pending), Dark Rush (76 candidates, 69 scans; #070–076 unavailable; exact Cardmarket images pending), Dragon Selection (20 Cardmarket DRS candidates, 20 DS scans; roster and exact-image matching pending), White Kyurem-EX Battle Strength Deck (20 candidates, 18 numbered scans, 2 unnumbered rows; exact image matches pending), Black Kyurem-EX Battle Strength Deck (20 candidates, 18 scans, 2 unnumbered rows; roster validation pending), Everyone’s Exciting Battle (72 candidates, 47 unique numbered codes/scans; 25 unnumbered rows remain unresolved), Shiny Collection (25 SHC candidates, 20 scans; #021–025 unavailable; exact Cardmarket imagery unverified), Megalo Cannon (86 candidates, 76 scans; #077–086 unavailable, roster validation pending), XY Beginning Set (51 cached products, 39 numbered candidates/scans; 12 product rows have no parsed HXY code; roster validation pending), Wild Blaze (90 candidate numbers, 87 scans; #088–090 unavailable; independent checklist validation pending), Rising Fist (105 candidate numbers, 103 scans; #104–105 unavailable; independent checklist validation pending), Phantom Gate (97 candidate numbers, 95 scans; #096–097 unavailable; independent checklist validation pending), Emerald Break (91 candidate numbers, 89 scans; #090–091 unavailable; independent checklist validation pending), Bandit Ring (97 candidate numbers, 95 scans; #096–097 unavailable; independent checklist validation pending), M Master Deck Build Box Speed Style (49 cached candidates indexed, Japanese checklist/images still to be sourced), M Master Deck Build Box Power Style (49 cached candidates indexed, Japanese checklist/images still to be sourced), Rage of the Broken Heavens (89 numbered candidates, 88 scans; #089 unavailable), Awakening Psychic King (88 numbered candidates/scans except #088 unavailable; exact Cardmarket images unverified), Strength Expansion Pack Sun & Moon (68 Japanese entries, 58 Limitless scans; #059–068 unavailable), Tag All Stars (226 numbered entries, 210 reference scans acquired; #211–226 unavailable from TCGdex image CDN, Cardmarket image matches unverified), Sword & Shield Promos (300 cached Cardmarket rows indexed provisionally; authoritative Japanese roster not located, no membership verified), VSTAR Universe (258 Japanese entries, all 258 numbers have provisional Cardmarket code candidates, no images yet), Scarlet & Violet Promos (288 Japanese promo checklist entries, 284 provisional Cardmarket code candidates; four checklist numbers lack a candidate, and artwork/finish matching remains open), Islands Await You (62 numbered candidates; TCGdex omits #062, corroborated by independent checklists and the matching Cardmarket candidate; scans #001–055 acquired, #056–062 unavailable), Beyond a New Challenge (65 numbered candidates, four unnumbered Energies, 57 scans; extra #066 candidate held for conflicting scope evidence), Ultradimensional Beasts (62 candidates; scans #001–055 acquired, #056–062 unavailable), Ultra Force (63 codes and Cardmarket candidates; reference image source still pending), Explosive Walker (86 numbered candidates; scans #001–078 acquired, #079–086 unavailable), S8a-P Promo Card Pack 25th Anniversary Edition (25 numbered candidates/scans, all have the confetti-holo finish), 25th Anniversary Collection (30 numbered candidates, 29 scans acquired; #030 unavailable, plus eight unnumbered Energies), VMAX Climax (285 numbered cards, 277 scans acquired; #278–285 unavailable from the current scan source, plus eight unnumbered Energies), Pokémon GO (93 numbered cards/scans plus eight unnumbered Energies), the three Pokémon Card Game Classic decks (32 numbered cards plus two unnumbered energies each; all 34 candidates present by name, but Cardmarket suffix numbers differ from Japanese numbering and no images have been matched), Shiny Treasure ex (360 numbered cards/scans; 300 cached Cardmarket candidate numbers and 60 gaps), Battle Academy (66 numbered scans plus eight unnumbered Basic Energy candidates), Chien-Pao ex Battle Master Deck (19), Mewtwo ex and Skeledirge ex Terastal Starter Sets (20 each), four paired ex Starter Sets (21 or 23 each), Premium Trainer Box ex (28), and the 30 numbered cards in the World Championships 2023 Yokohama Deck: Pikachu (with its two unnumbered basic Energy products tracked separately). Duplicate Cardmarket product variants are retained as unresolved candidates rather than guessed. Earlier reviewed groups and unresolved source-copy-count conflicts remain documented in their individual checklist summaries.
- Downloaded **5129 Japanese reference scans** across 96 groups, associated by printed set number from documented card indexes and scan sources. All manifest file paths are unique and present, and all recorded SHA-256 hashes currently match. PNG dimensions are populated for all scans. Forty-four checklist/source display-name differences are recorded in `review/image-acquisition-summary-20261029.json` for review. Reference scans establish roster identity but have not been compared with Cardmarket product images; exact Cardmarket links and catalogue mappings remain unverified/not started.
- Exact printing inventory, verified Cardmarket links, vector generation, and publication remain at **zero / not started**. No catalogue mappings have been promoted.
- The 1-second local navigation interval is the current approved operating setting; challenges remain owner-cleared in the same visible Chrome session.

Evidence lives under `data/catalogue-gaps/ja-set-recovery-20261029-v3/`:

- `source-pages/cardmarket-master-index.html` and `.json`: observed local browser content and parsed links. JSON SHA-256: `f71b677bdbe85c7bd160929aa5c40c9439648d8b40502a6e8713382aabda54a5`.
- `listing-seeds.json`: 276 unambiguous collection targets, each with source provenance. Original 78 preserved; backup under `refresh-backups/`.
- `seed-discovery-review.json`: one decision per audit group, including aliases and candidate URLs.
- `shared-listing-review-queue.json`: 29 unique review-pool URLs and their related group IDs; **not an approved exact-print mapping manifest**.
- `review/remaining-group-routing.csv`: all 60 review cases and next actions.
- `review/provider-code-observations.csv`: reference code versus the provider's preview-image path code, where available. Preview-path codes are provider taxonomy, not proof of the physically printed code.
- `review/additional-source-checks.json`: targeted research, sealed-product pitfalls and the unusual Entry-Pack-DP route.
- `listing-progress.json`, `listing-report.json`, `cardmarket-products.jsonl`: complete 276-group traversal and product records. Discovery does not verify catalogue mappings.
- `shared-listings-progress.json`, `shared-listings-report.json`, `shared-listings-products.jsonl`: 29 completed shared sources and unverified candidate products.

## Verified naming and scope examples

- The Japanese 20th Anniversary Starter Pack is listed as [BREAK Starter Pack](https://www.cardmarket.com/en/Pokemon/Products/Singles/BREAK-Starter-Pack). The listing shows `20th` card codes. This is a confirmed title alias for collection, not a substitute for checking individual variants.
- Sun & Moon Enhanced Expansion Pack appears as [Strength Expansion Pack Sun & Moon](https://www.cardmarket.com/en/Pokemon/Products/Singles/Strength-Expansion-Pack-Sun-Moon), with `sm1+` products.
- `Entry-Pack-DP` is an unsafe slug to interpret by name. Live collection returned 19 **MSM** products, including Sea's Manaphy, matching the index title “Movie Commemoration VS Pack: Sea's Manaphy”. Keep that route with the Manaphy group. The generic Entry Pack checklist remains a card-level review case; do not assign it this URL.
- The three Battle Strength subdecks share “Battle Strength Decks”; the three VMAX starter groups share “VMAX Starter Decks”. A provider listing can span more than one audit group.
- Neo Premium File products exist as **sealed Box Sets**, but that does not establish singles URLs. An individual [Feraligatr](https://www.cardmarket.com/en/Pokemon/Products/Singles/Unnumbered-Promos/Feraligatr-UNP) and the starter species occur in the broader Unnumbered Promos pool. Confirm every exact artwork/finish before linking.
- The miscellaneous-decks checklist has Gym-deck routes, including [Brock's Zubat](https://www.cardmarket.com/en/Pokemon/Products/Singles/Nivi-City-Gym/Brocks-Zubat-CGN) and [Sabrina's Jynx](https://www.cardmarket.com/en/Pokemon/Products/Singles/Yamabuki-City-Gym/Sabrinas-Jynx-CGY). These examples do not prove coverage of all 73 checklist cards.
- Annual energy groups remain separate from the broad “Unnumbered Energies” pool until era, design, stamp and finish are checked. Do not merge cards by energy type alone.

## Sun & Moon Promos checklist progress (2026-10-30)

- Built `review/sun-moon-promos-checklist.csv` with all 449 TCG Collector entries: 408 numbered SM-P cards and 41 additional promo entries (`No. 409–439`, `No. 443–448`, `No. 452–454`, and `No. 456`). Card names are populated for all entries; the detail page for Water Energy 184 timed out, so its name is taken from the observed card URL.
- Cached Cardmarket data has 297 numbered candidate rows across 296 SM-P numbers. These remain candidate associations only: no membership or exact printing is verified, and no reference scans have been acquired for this group.
- See `review/sun-moon-promos-reconciliation-summary.json`. The checklist job is complete. Reference images and exact candidate membership remain for the separate image-reconciliation stage.

## The Best of XY checklist progress (2026-10-30)

- Created `review/the-best-of-xy-checklist.csv` with all 188 itemized card numbers: 001–171 plus secret numbers 172–188. MyTCGValue’s summary says 187 cards, while its list enumerates 188; BinderBoss also reports 188, so the discrepancy is recorded for follow-up.
- Cached Cardmarket products yielded 227 name-based candidate rows across 185 checklist cards. All remain unverified; image comparison and exact printing membership are pending.
- See `review/the-best-of-xy-reconciliation-summary.json`.

## Cruel Traitor checklist progress (2026-10-30)

- Created `review/cruel-traitor-checklist.csv` with 59 itemized rows, numbers 001–059; the source reports a 54-card main set with five entries above 054.
- All 59 cached Cardmarket products have an XY11 code-number candidate. Exact printing, finish, image identity and membership remain unverified; no reference scans have been acquired.
- See `review/cruel-traitor-reconciliation-summary.json`.

## Fever-Burst Fighter checklist progress (2026-10-30)

- Created `review/fever-burst-fighter-checklist.csv` with 59 itemized rows, numbers 001–059; the source reports 54 main-set cards plus five secret entries.
- All 59 cached Cardmarket products have an XY11 code-number candidate. Exact printing, finish, image identity and membership remain unverified; no reference scans have been acquired.
- See `review/fever-burst-fighter-reconciliation-summary.json`.

## Premium Champion Pack CP4 checklist progress (2026-10-30)

- Created `review/premium-champion-pack-cp4-checklist.csv` with 140 entries: 131 numbered CP4 cards and nine unnumbered Energy printings.
- All 140 cached Cardmarket products have a code or Energy-name candidate. Exact printing, artwork and finish remain unverified; reference-image acquisition is pending.
- See `review/premium-champion-pack-cp4-reconciliation-summary.json`.

## M Audino-EX Mega Battle Deck checklist progress (2026-10-30)

- Created `review/m-audino-ex-mega-battle-deck-checklist.csv` with 26 numbered XYH cards and a separate Fairy Energy candidate row. The set registry says 27, while the numbered checklist has 26; whether Fairy Energy belongs in this deck remains unresolved.
- All 26 numbered Cardmarket candidates align by XYH code number but remain unverified against exact printings and images. No reference scans have been acquired.
- See `review/m-audino-ex-mega-battle-deck-reconciliation-summary.json`.

## Zygarde-EX Perfect Battle Deck checklist progress (2026-10-30)

- Created `review/zygarde-ex-perfect-battle-deck-checklist.csv` with 19 numbered XYG cards and a separate Fighting Energy candidate row. MyTCGValue lists 19, while PokeNin and the run registry indicate 20 total; Energy inclusion remains unresolved.
- All 19 numbered Cardmarket candidates align by XYg code, but exact printing and image membership remain unverified.
- See `review/zygarde-ex-perfect-battle-deck-reconciliation-summary.json`.

## BREAK Starter Pack 20th checklist progress (2026-10-30)

- Created `review/break-starter-pack-20th-checklist.csv` with 84 entries: 77 20th-coded cards and seven unnumbered Basic Energy entries. House of Cards reports a printed denominator of 072; the five 073–077 entries need exact printing verification.
- All 84 cached Cardmarket rows are recorded as candidates. Exact printing, finish and membership remain unverified; reference-image acquisition is pending.
- See `review/break-starter-pack-20th-reconciliation-summary.json`.

## Golduck BREAK + Palkia-EX Combo Deck checklist progress (2026-10-30)

- Created `review/golduck-break-palkia-ex-combo-deck-checklist.csv` with 16 numbered XYF cards and one unnumbered Basic Water Energy entry.
- All numbered Cardmarket candidates align by XYf code. Exact printing, Energy finish and image membership remain unverified.
- See `review/golduck-break-palkia-ex-combo-deck-reconciliation-summary.json`.

## Blue Shock checklist progress (2026-10-30)

- Created `review/blue-shock-checklist.csv` with 65 entries: 59 main-set cards and six secret entries numbered 060–065.
- All 65 cached Cardmarket rows have XY8b code-number candidates. Exact printing, finish and image membership remain unverified; reference-image acquisition is pending.
- See `review/blue-shock-reconciliation-summary.json`.

## Noivern BREAK Evolution Pack checklist progress (2026-10-30)

- Created `review/noivern-break-evolution-pack-checklist.csv` with all ten numbered cards, 001–010.
- All ten cached Cardmarket candidates align by SNPn code. Exact printing/finish and image membership remain unverified.
- See `review/noivern-break-evolution-pack-reconciliation-summary.json`.

## Raichu BREAK Evolution Pack checklist progress (2026-10-30)

- Created `review/raichu-break-evolution-pack-checklist.csv` with all ten numbered cards, 001–010.
- All ten cached Cardmarket candidates align by SNPr code. Exact printing/finish and image membership remain unverified.
- See `review/raichu-break-evolution-pack-reconciliation-summary.json`.

## Red Flash checklist progress (2026-10-30)

- Created `review/red-flash-checklist.csv` with 65 entries: 59 main-set cards and six secret cards numbered 060–065.
- All 65 cached Cardmarket candidates align by XY8r code number. Exact printing, finish and image membership remain unverified.
- See `review/red-flash-reconciliation-summary.json`.

## Emboar-EX vs Togekiss-EX Battle Starter Set checklist progress (2026-10-30)

- Created `review/emboar-togekiss-battle-starter-set-checklist.csv` with 22 numbered XYe cards plus four separate unnumbered Energy candidate types. Cached Cardmarket data has 32 product rows, including duplicate numbered candidates.
- Exact printing/finish, Energy inclusion and copy counts remain unresolved; the Cardmarket pool is not treated as deck proof.
- See `review/emboar-togekiss-battle-starter-set-reconciliation-summary.json`.

## M Rayquaza-EX Mega Battle Deck checklist progress (2026-10-30)

- Created `review/m-rayquaza-ex-mega-battle-deck-checklist.csv` with 18 numbered XYD cards and separate Fire and Lightning Energy candidate rows.
- All numbered Cardmarket candidates align by XYd code. Energy inclusion/copies, exact printing and image membership remain unverified.
- See `review/m-rayquaza-ex-mega-battle-deck-reconciliation-summary.json`.

## Gaia Volcano checklist progress (2026-10-30)

- Created `review/gaia-volcano-checklist.csv` with all 80 itemized rows: 70 main-set cards plus ten above-denominator entries.
- The source renders row 079 as 079/080, while neighboring codes use /070. It is provisionally normalized to 079/070 and held for source confirmation. All 80 cached Cardmarket products have XY5g code candidates, still unverified by image.
- See `review/gaia-volcano-reconciliation-summary.json`.

## Tidal Storm checklist progress (2026-10-30)

- Created `review/tidal-storm-checklist.csv` with 80 itemized rows: 70 main-set cards plus ten above-denominator cards.
- All 80 cached Cardmarket rows have XY5t code candidates. Exact printing and image membership remain unverified.
- See `review/tidal-storm-reconciliation-summary.json`.

## Xerneas-EX & Yveltal-EX Super Legend Set checklist progress (2026-10-30)

- Created `review/xerneas-yveltal-super-legend-set-checklist.csv` with 23 numbered XYC cards plus Darkness and Fairy Energy candidate rows.
- All numbered Cardmarket candidates align by XYc code. Energy inclusion, exact printing and image membership remain unverified.
- See `review/xerneas-yveltal-super-legend-set-reconciliation-summary.json`.

## Dialga-EX + Aegislash-EX Hyper Metal Chain Deck checklist progress (2026-10-30)

- Created `review/dialga-aegislash-hyper-metal-chain-deck-checklist.csv` with 19 Xyb card entries (including 019/018) plus an unnumbered Metal Energy candidate.
- Numbered Cardmarket candidates align by XYb code. Exact printing/variant and Energy inclusion remain unverified.
- See `review/dialga-aegislash-hyper-metal-chain-deck-reconciliation-summary.json`.

## M Charizard-EX Mega Battle Deck checklist progress (2026-10-30)

- Created `review/m-charizard-ex-mega-battle-deck-checklist.csv` with 21 numbered XYa cards plus Fire and Darkness Energy candidate rows.
- Numbered Cardmarket candidates align by XYa code. Energy inclusion/copies, exact printing and image membership remain unverified.
- See `review/m-charizard-ex-mega-battle-deck-reconciliation-summary.json`.

## Xerneas Half Deck checklist progress (2026-10-30)

- Created `review/xerneas-half-deck-checklist.csv` with 14 numbered X30 cards and a separate Fairy Energy candidate row.
- Numbered Cardmarket candidates align by X30 code. Energy inclusion/copy count, exact printing and image membership remain unverified.
- See `review/xerneas-half-deck-reconciliation-summary.json`.

## Yveltal Half Deck checklist progress (2026-10-30)

- Created `review/yveltal-half-deck-checklist.csv` with 14 numbered Y30 cards and a separate Darkness Energy candidate row.
- Numbered Cardmarket candidates align by Y30 code. Energy inclusion/count, exact printing and image membership remain unverified.
- See `review/yveltal-half-deck-reconciliation-summary.json`.

## Collection X checklist progress (2026-10-30)

- Created `review/collection-x-checklist.csv` with all 63 entries: 60 within the printed denominator plus three above-denominator entries.
- All 63 numbers have cached Cardmarket XY1x candidates (64 rows due to one duplicate candidate); exact printing and image membership remain unverified.
- See `review/collection-x-reconciliation-summary.json`.

## Collection Y checklist progress (2026-10-30)

- Created `review/collection-y-checklist.csv` with all 63 entries: 60 within the printed denominator plus three above-denominator entries.
- All 63 cached Cardmarket products have XY1y code candidates. Exact printing and image membership remain unverified.
- See `review/collection-y-reconciliation-summary.json`.

## XY Promos checklist progress (2026-10-30)

- Created `review/xy-promos-checklist.csv` and `review/xy-promos-tcgcollector-checklist.json` with all 453 TCG Collector entries: 298 explicit `NNN/XY-P` entries and 155 `No. N` source catalog entries. The `No. N` values are not treated as printed card codes.
- Recorded 268 cached Cardmarket candidates across 260 numbered checklist rows by XY-P code. Candidate membership remains unverified; no reference images or catalogue mappings were added.
- See `review/xy-promos-reconciliation-summary.json`. Checklist acquisition is complete; image comparison remains pending.

## EX Battle Boost checklist progress (2026-10-30)

- Created `review/ex-battle-boost-checklist.csv` with 99 numbered entries: 001–093 and six secret rares, 094–099. Mirror Holo finish variants are excluded from this 99-entry checklist total.
- All 99 cached Cardmarket products have matching EBB number candidates. These remain unverified until exact printing and image comparison.
- See `review/ex-battle-boost-reconciliation-summary.json`. Reference-image acquisition and catalogue mapping remain pending.

## Blastoise + Kyurem-EX Combo Deck checklist progress (2026-10-30)

- Created `review/blastoise-kyurem-ex-combo-deck-checklist.csv` with the 18 numbered cards from MyTCGValue, plus one unnumbered Water Energy candidate observed in the cached Cardmarket deck listing.
- All 18 numbered rows have K+K code candidates. Water Energy membership is held pending independent deck-content evidence. All candidates remain unverified pending images.
- See `review/blastoise-kyurem-ex-combo-deck-reconciliation-summary.json`.

## Spiral Force checklist progress (2026-10-30)

- Created `review/spiral-force-checklist.csv` with all 58 entries: 001–051/051 and seven secret entries, 052–058/051. MyTCGValue and Pooka both report 58.
- All 58 cached Cardmarket BW8s candidates align by number only and remain unverified pending exact-print image review.
- See `review/spiral-force-reconciliation-summary.json`; reference images and catalogue mappings remain pending.

## Thunder Knuckle checklist progress (2026-10-30)

- Created `review/thunder-knuckle-checklist.csv` with 58 entries: 001–051/051 and seven secret entries, 052–058/051. MyTCGValue and House of Cards both report 58.
- All 58 cached Cardmarket BW8t candidates align by number only and remain unverified pending exact-print image review.
- See `review/thunder-knuckle-reconciliation-summary.json`; images and catalogue mappings remain pending.

## Team Plasma Battle Gift Set checklist progress (2026-10-30)

- Created `review/team-plasma-battle-gift-set-checklist.csv` with 16 numbered PBG cards plus two unnumbered Basic Energy candidates. MyTCGValue provides the numbered checklist; PokeDataVault describes the 18-card set and identifies the Psychic and Darkness Energy inclusions.
- All 18 cached Cardmarket candidates are recorded. The two Energy rows remain held for exact-print and image review; all membership fields remain unverified.
- See `review/team-plasma-battle-gift-set-reconciliation-summary.json`.

## Team Plasma's Powered Half Deck checklist progress (2026-10-30)

- Created `review/team-plasma-powered-half-deck-checklist.csv` with 17 numbered cards plus unnumbered Basic Psychic and Metal Energy candidates.
- TCG Stats identifies 19 product entries; all 19 cached Cardmarket candidates are recorded. Energy variants and exact membership remain unverified pending images.
- See `review/team-plasma-powered-half-deck-reconciliation-summary.json`.

## Cold Flare checklist progress (2026-10-30)

- Created `review/cold-flare-checklist.csv` with 65 entries: 001–059/059 and six secret entries, 060–065/059. JapanesePokemonCards independently reports 65.
- All 65 cached Cardmarket BW6c candidates align by number only; exact printing and image verification remain pending.
- See `review/cold-flare-reconciliation-summary.json`.

## Freeze Bolt checklist progress (2026-10-30)

- Created `review/freeze-bolt-checklist.csv` with 65 entries: 001–059/059 and six secret entries, 060–065/059.
- All 65 cached Cardmarket BW6f candidates align by number only. Exact printing and image verification remain pending.
- See `review/freeze-bolt-reconciliation-summary.json`.

## Keldeo Battle Strength Deck checklist progress (2026-10-30)

- Created `review/keldeo-battle-strength-deck-checklist.csv` with 15 MyTCGValue numbered rows and three unnumbered Energy candidates.
- PokeDataVault describes 18 entries but has inconsistent totals and a #013 Eviolite versus `028018 T SHINKANOKISEKI` variant conflict. This is recorded for image review.
- All 18 cached Cardmarket products remain unverified candidates. See `review/keldeo-battle-strength-deck-reconciliation-summary.json`.

## National Beginning Set checklist progress (2026-10-30)

- Created `review/national-beginning-set-checklist.csv` with 34 numbered HSZ cards and six unnumbered Energy candidates, matching the 40-card total reported in Bulpex and the registry.
- Four numbered rows have multiple cached Cardmarket variant candidates. PokeDataVault's conflicting 48-card roster remains unresolved; no candidate membership was verified.
- See `review/national-beginning-set-reconciliation-summary.json`.

## Dragon Blade checklist progress (2026-10-30)

- Created `review/dragon-blade-checklist.csv` with all 55 entries: 001–050/050 and five secret entries, 051–055/050.
- All 55 cached Cardmarket BW5e candidates align by number only and remain unverified pending exact-print image comparison.
- See `review/dragon-blade-reconciliation-summary.json`; reference images and catalogue mappings remain pending.

## Dragon Blast checklist progress (2026-10-30)

- Created `review/dragon-blast-checklist.csv` with all 55 entries: 001–050/050 and five secret entries, 051–055/050.
- All 55 cached Cardmarket BW5t candidates align by number only and remain unverified pending exact-print image review.
- See `review/dragon-blast-reconciliation-summary.json`.

## Garchomp Half Deck checklist progress (2026-10-30)

- Created `review/garchomp-half-deck-checklist.csv` with 15 numbered cards plus unnumbered Basic Fighting, Water, and Lightning Energy candidates.
- All 18 cached Cardmarket products are recorded as unverified candidates pending exact-print image review.
- See `review/garchomp-half-deck-reconciliation-summary.json`.

## Hydreigon Half Deck checklist progress (2026-10-30)

- Created `review/hydreigon-half-deck-checklist.csv` with 15 numbered cards plus unnumbered Basic Grass, Psychic, and Darkness Energy candidates.
- All 18 cached Cardmarket products remain unverified pending exact-print image comparison.
- See `review/hydreigon-half-deck-reconciliation-summary.json`.

## Beginning Set Pikachu checklist progress (2026-10-30)

- Created `review/beginning-set-pikachu-checklist.csv` with all 40 TCG Collector entries: numbered cards 001–034/034 and six Energy entries 035–040/034.
- Recorded 48 cached Cardmarket candidates, including duplicate Trainer variants. All remain unverified pending exact-print image comparison.
- See `review/beginning-set-pikachu-reconciliation-summary.json`.

## Thundurus vs Tornadus Battle Gift Set checklist progress (2026-10-30)

- Created `review/thundurus-vs-tornadus-battle-gift-set-checklist.csv` with 20 numbered cards plus six unnumbered Basic Energy candidates.
- All 32 cached Cardmarket products are recorded, including multiple Trainer variants. Exact membership and images remain unverified.
- See `review/thundurus-vs-tornadus-battle-gift-set-reconciliation-summary.json`.

## Zekrom-EX Battle Strength Deck checklist progress (2026-10-30)

- Created `review/zekrom-ex-battle-strength-deck-checklist.csv` with 18 numbered cards plus unnumbered Basic Grass and Lightning Energy candidates.
- All 20 cached Cardmarket products remain unverified pending exact-print image comparison.
- See `review/zekrom-ex-battle-strength-deck-reconciliation-summary.json`.

## Hail Blizzard checklist progress (2026-10-30)

- Created `review/hail-blizzard-checklist.csv` with 57 entries: 001–052/052 and five secret entries, 053–057/052.
- All 57 cached Cardmarket BW3h candidates align by number only and remain unverified pending exact-print image comparison.
- See `review/hail-blizzard-reconciliation-summary.json`.

### Psycho Drive checklist update

Recorded all 57 MyTCGValue entries (52 main-set cards and five secret entries) and matched 57 Cardmarket product candidates by numeric suffix. The provider code `BW3p` differs from the registry code `BW3-Bp`; candidate membership and exact-print image matches remain unverified. Image reconciliation is still pending. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/psycho-drive-checklist.csv` and its reconciliation summary.

### Beginning Set + checklist update

Recorded the TCG Collector 40-row checklist: 34 numbered entries and six unnumbered Basic Energy inclusions. Card names omitted from the TCG Collector page were filled from the set deck lists. The 48 Cardmarket product candidates use `HSPL`, while the registry code is `HS+`; all candidate membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/beginning-set-plus-checklist.csv` and its reconciliation summary.

### Victini Battle Theme Deck checklist update

Recorded 21 numbered entries and three unnumbered Energy inclusions. The TCG Collector checklist provides the count; Bulbapedia deck lists identify Fire, Lightning, and Psychic Energy. Cardmarket candidates remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/victini-battle-theme-deck-checklist.csv` and its reconciliation summary.

### Black Collection checklist update

Recorded 56 MyTCGValue rows: 53 main-set entries plus three secrets. All 56 have numeric-suffix candidates among 58 Cardmarket product rows, but exact membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/black-collection-checklist.csv` and its reconciliation summary.

### White Collection checklist update

Recorded 56 entries. MyTCGValue exposes 55 through Zekrom 055/053; TCG Collector adds Pikachu 056/053, corroborated by Cardmarket product BW1w 056. All rows have numeric-suffix candidates, still unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/white-collection-checklist.csv` and its reconciliation summary.

### Beginning Set checklist update

Recorded 43 TCG Collector entries: 37 numbered cards and six Basic Energy items listed as No. 038–043. There are 57 Cardmarket candidate product rows; number and energy candidates remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/beginning-set-checklist.csv` and its reconciliation summary.

### Journey Partners checklist update

Recorded nine MyTCGValue checklist entries and nine Cardmarket CS1 numeric-suffix candidates. All remain unverified pending image comparison. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/journey-partners-checklist.csv` and its reconciliation summary.

### Battle Starter Deck (Blastoise) checklist update

Recorded ten numbered MyTCGValue entries. All ten have BSDb number-suffix Cardmarket candidates, still unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/battle-starter-deck-blastoise-checklist.csv` and its reconciliation summary.

### Battle Starter Deck (Magmortar) checklist update

Recorded nine numbered MyTCGValue entries. All nine have BSDm number-suffix Cardmarket candidates, still unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/battle-starter-deck-magmortar-checklist.csv` and its reconciliation summary.

### Battle Starter Deck (Raichu) checklist update

Recorded 11 numbered MyTCGValue entries, each with a BSDr suffix candidate. Membership and image matches are unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/battle-starter-deck-raichu-checklist.csv` and its reconciliation summary.

### Battle Starter Deck (Torterra) checklist update

Recorded ten numbered MyTCGValue entries, each with a BSDt Cardmarket suffix candidate. Membership and image matches are unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/battle-starter-deck-torterra-checklist.csv` and its reconciliation summary.

### Leafeon vs Metagross Expert Deck (Leafeon) checklist update

Recorded 15 MyTCGValue entries and LED numeric candidates. The route family may include the paired Metagross deck; exact membership remains unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/leafeon-vs-metagross-expert-deck-leafeon-checklist.csv` and its reconciliation summary.

### Leafeon vs Metagross Expert Deck (Metagross) checklist update

Recorded 14 MyTCGValue entries and MED number-suffix candidates. The paired deck uses a distinct provider code; candidate matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/leafeon-vs-metagross-expert-deck-metagross-checklist.csv` and its reconciliation summary.

### LEGEND Promos checklist update

Recorded 79 named L-P cards from MyTCGValue and 12 TCG Collector rows labeled No. 500–511 as unresolved extras. The 82 Cardmarket products provide numeric candidates for the 79 named entries only; all remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/legend-promos-checklist.csv` and its reconciliation summary.

### Advent of Arceus checklist update

Recorded all 90 MyTCGValue entries and 90 Cardmarket Pt4 number-suffix candidates. Exact product membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/advent-of-arceus-checklist.csv` and its reconciliation summary.

### Arceus LV.X Deck: Grass & Fire checklist update

Recorded 17 MyTCGValue entries and 17 numeric Cardmarket candidates. Cardmarket uses AGF while the registry code is DPt4-Sgf; these matches are unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/arceus-lv-x-deck-grass-fire-checklist.csv` and its reconciliation summary.

### Arceus LV.X Deck: Lightning & Psychic checklist update

Recorded 17 MyTCGValue entries and 17 numeric Cardmarket candidates. Cardmarket uses ALP while the registry code is DPt4-Slp; all matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/arceus-lv-x-deck-lightning-psychic-checklist.csv` and its reconciliation summary.

### Mewtwo LV.X Collection Pack checklist update

Recorded 12 MyTCGValue entries and 12 Cardmarket PtM numeric candidates. Membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/mewtwo-lv-x-collection-pack-checklist.csv` and its reconciliation summary.

### Regigigas LV.X Collection Pack checklist update

Recorded 12 MyTCGValue entries and 12 Cardmarket PtR numeric candidates. Membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/regigigas-lv-x-collection-pack-checklist.csv` and its reconciliation summary.

### Shaymin LV.X Collection Pack checklist update

Recorded 12 MyTCGValue entries and 12 Cardmarket PtS numeric candidates. Membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/shaymin-lv-x-collection-pack-checklist.csv` and its reconciliation summary.

### Beat of the Frontier checklist update

Recorded 100 MyTCGValue entries and 100 Cardmarket Pt3 numeric candidates. Exact membership and artwork matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/beat-of-the-frontier-checklist.csv` and its reconciliation summary.

### Garchomp vs Charizard SP Deck Kit (Charizard) checklist update

Recorded 16 MyTCGValue entries and 16 numeric Cardmarket candidates. Product names use PtC codes while the URLs use PtS; matches to the Charizard deck remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/garchomp-vs-charizard-sp-deck-kit-charizard-checklist.csv` and its reconciliation summary.

### Garchomp vs Charizard SP Deck Kit (Garchomp) checklist update

Recorded 16 numbered entries from the Bulbapedia deck list because the first MyTCGValue response omitted three entries. Sixteen PtG numeric Cardmarket candidates are retained, unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/garchomp-vs-charizard-sp-deck-kit-garchomp-checklist.csv` and its reconciliation summary.

### Bonds to the End of Time checklist update

Recorded 90 MyTCGValue entries and 90 Cardmarket Pt2 numeric candidates. Membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/bonds-to-the-end-of-time-checklist.csv` and its reconciliation summary.

### Infernape vs Gallade SP Deck Kit (Gallade) checklist update

Recorded all 18 TCG Collector entries because the first MyTCGValue response exposed only 12. Eighteen Cardmarket PtGL numeric candidates are present, still unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/infernape-vs-gallade-sp-deck-kit-gallade-checklist.csv` and its reconciliation summary.

### Infernape vs Gallade SP Deck Kit (Infernape) checklist update

Recorded all 18 TCG Collector entries and 18 Cardmarket PtI numeric candidates. Membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/infernape-vs-gallade-sp-deck-kit-infernape-checklist.csv` and its reconciliation summary.

### DPt Gift Box (Chimchar) checklist update

Recorded 13 MyTCGValue entries and 13 Cardmarket PtCH numeric candidates. Membership and image matches remain unverified. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/dpt-gift-box-chimchar-checklist.csv` and its reconciliation summary.

### DPt Gift Box (Pikachu) checklist update

Recorded all 15 numbered cards (001–015) from two independent full-list sources. Cardmarket has PtPK candidates for all 15; Pikachu 004 has two product variants, so exact printing is unresolved. MyTCGValue currently returns only 10 entries despite a 15-card denominator. No source images have been acquired. See `data/catalogue-gaps/ja-set-recovery-20261029-v3/review/dpt-gift-box-pikachu-checklist.csv` and its reconciliation summary.

### Giratina vs Dialga Deck Kit (Dialga) checklist update

Recorded all 14 numbered entries with deck copy counts and 14 cached DHD candidates. Unnumbered Lightning/Metal Energy are noted separately. Exact printing/image matching remains open. See `review/giratina-vs-dialga-deck-kit-dialga-checklist.csv` and its summary.

### Giratina vs Dialga Deck Kit (Giratina) checklist update

Recorded all 14 numbered entries with deck copy counts and 14 cached GHD candidates. Unnumbered Grass/Psychic Energy are noted separately. Exact printing/image matching remains open. See `review/giratina-vs-dialga-deck-kit-giratina-checklist.csv` and its summary.

### Intense Fight in the Destroyed Sky checklist update

Recorded all 92 numbered cards from a complete checklist cross-checked against independent set sources. All 92 have cached IFDS suffix candidates; exact finish and printing matches remain open. No source images acquired. See `review/intense-fight-in-the-destroyed-sky-checklist.csv` and its summary.

### Cry from the Mysterious checklist update

Recorded 65 distinct card names from the complete MyTCGValue list, consistent with independent 65-card set counts. The checklist has no printed collector numbers, so those fields remain blank. All 65 cached DP5c products match by normalized name only; exact printing/image matching remains open. No images acquired. See `review/cry-from-the-mysterious-checklist.csv` and its summary.

### Heatran vs Regigigas Deck Kit checklist update

Recorded the 24 unique named products from the union of the two half-decks, summing overlapping item copy counts. The registry says 22; MyTCGValue says 23 and omits Energy Switch; Cardmarket lists all 24 products. This count conflict remains documented. Numbered/energy details and exact printing/image matches remain open. See `review/heatran-vs-regigigas-deck-kit-checklist.csv` and its summary.

### Temple of Anger checklist update

Recorded 65 distinct cards from a full checklist, cross-checked against independent 65-card counts. Printed numbers are unavailable in the chosen sources. All 65 Cardmarket DP5c products are associated by name only; exact printing/image matching remains open. See `review/temple-of-anger-checklist.csv` and its reconciliation summary.

### Entry Pack '08 checklist update

Recorded the 42 observed names and matching Cardmarket products. Bulbapedia distinguishes standard Entry Pack ’08 from Entry Pack ’08 DX, which adds a Raichu deck; the scope of this registry group remains unresolved. Printed numbers are absent and no deck membership/copy counts are asserted. See `review/entry-pack-08-checklist.csv` and its reconciliation summary.

### Additional checklist recovery (30 October 2026)

- **Dawn Dash (DP4):** recorded the 70-card base checklist and joined 70 cached Cardmarket DP4d products by name. TCGventory and Cardtracker support the 70-card count; MyTCGValue lists 65, and an index includes additional Energy variants. The roster sequence is not represented as printed DPBP numbers; exact variant and image matching remain pending.
- **Magmortar vs Electivire Deck Kit:** recorded TCG Collector’s 25 numbered entries and joined 28 cached Cardmarket product rows. Bulbapedia documents deck contents and additional holo/non-holo Magmortar/Electivire printings beyond that 25-entry index. Deck-copy and print-variant reconciliation remain open.
- **Moonlit Pursuit (DP4):** recorded Pooka’s numbered 001–070 roster and matched all 70 names to cached DP4m Cardmarket candidates. TCGventory and MyTCGValue also report 70 cards; printing and image associations remain unverified.
- **Dialga LV.X Constructed Standard Deck:** recorded 18 non-Energy unique entries and deck-copy quantities; the 24 Basic Energy cards are separately noted. All 18 names have cached DP3d candidates, with two Dialga products requiring variant review.
- **Palkia LV.X Constructed Standard Deck:** recorded 18 non-Energy entries and deck-copy quantities; 24 Basic Energy cards are separately noted. All entries have cached DP3p candidates, with two Palkia products requiring variant review.
- **Shining Darkness (DP3):** recorded the English numbered 001–119 roster and joined all 119 cached Cardmarket DP3 candidates by name. Exact printing and image association remain pending.
- **Bastiodon the Defender Half Deck:** recorded 16 tracked unique non-basic-Energy entries, preserving deck-copy counts; the basic Fire and Metal Energy quantities are noted separately. All 16 names have cached Cardmarket candidates.
- **Rampardos the Attacker Half Deck:** recorded 16 tracked unique non-basic-Energy entries and deck-copy counts; basic Lightning and Fighting Energy are separately noted. All 16 names have cached Cardmarket candidates.
- **Secret of the Lakes (DP2):** recorded the English numbered 001–123 roster and joined all 123 cached Cardmarket DP2 products by name as candidates. Exact print and image matching remain pending.
- **Diamond & Pearl Promos (DP-P):** recorded the 127-numbered Japanese promo checklist and joined all 127 cached Cardmarket products by explicit DP-P number. Repeated Pokémon names remain separate promo entries; exact printing, artwork, and image associations remain pending.
- **Space-Time Creation (DP1):** recorded 122 numbered entries from TCG Collector and joined all 122 cached Cardmarket products by normalized English name. TCG Collector and Dex report 122; MyTCGValue and CardPrice report 121. Exact print and image verification remain pending.
- **Entry Pack:** recorded 32 unique non-Energy entries from TCG Collector, retaining DP1 card numbers and joining cached DP1 Cardmarket candidates by name. Bulbapedia documents three decks of 28/30/32 cards; deck copies and Energy are separate. PokeDataVault reports 38 with a broader Energy scope. Entry Pack no-rarity print distinctions and exact images remain unverified.
- **Imprison! Gardevoir ex Constructed Standard Deck:** recorded 24 numbered non-Energy entries and deck copy counts from Bulbapedia; joined all 24 cached Cardmarket products by `pcgS` number. The 9 Fire and 7 Psychic Energy copies are noted separately; exact image/finish matching remains pending.
- **Shockwave! Tyranitar ex Constructed Standard Deck:** recorded 24 numbered entries and quantities from Bulbapedia; joined all 24 cached Cardmarket products by `pcgR` number. The 9 Lightning and 7 Fighting Energy copies are noted separately; image/finish matching remains pending.
- **Earth's Groudon ex Constructed Starter Deck:** recorded 16 numbered entries with deck quantities from Bulbapedia; joined all 16 cached Cardmarket products by `pcgQ` number. Unnumbered Grass, Lightning, and Fighting Energy quantities are separately noted; image/finish matching remains pending.
- **Ocean's Kyogre ex Constructed Starter Deck:** recorded 16 numbered entries and quantities from Bulbapedia; joined all 16 cached Cardmarket products by `pcgP` number. Unnumbered Fire, Water, and Psychic Energy are separate; exact image/finish matching remains pending.
- **Holon Research Tower Fire Quarter Deck:** recorded 15 numbered entries from Bulbapedia, preserving the four numbered Fire Energy rows, and joined all 15 Cardmarket candidates by `pcgM` number. Exact print and image association remain pending.
- **Holon Research Tower Lightning Quarter Deck:** recorded 15 numbered rows, including four Lightning Energy and Great Ball at 008, and joined all cached products by `pcgO` number. MyTCGValue/CardPrice report 14 by omitting one row; count discrepancy and pending image verification are documented.
- **Holon Research Tower Water Quarter Deck:** recorded 15 numbered rows, including four Water Energy entries, and joined all cached products by `pcgN` number. Exact image/finish associations remain pending.

## Efficient execution order

1. **Freeze and retain the source snapshot.** The reproducible matcher is `api/scripts/ja_set_recovery/discover_seeds.py`. It uses observed URLs, exact normalized titles and explicit reviewed title aliases. It does not manufacture slugs or automatically approve fuzzy matches. `--apply` backs up and preserves existing seeds. Shared listings, combined checklists and broader pools are held separately.
2. **Keep the completed route acquisition checkpoint.** The 276-group queue is complete and resumable. Rerun only if a saved page is demonstrably incomplete or a newly observed route is added. Use one visible local browser, the dedicated persistent profile, the existing checkpointed collector, and the current one-second navigation interval. Do not fetch live offer pages merely to enumerate singles.
3. **Reconcile source checklists and images.** Reuse official Pokémon, TCG Collector and historical caches. Record printed codes/fractions, language, set/product identity, artwork, rarity, finish and variant markers independently of Cardmarket's abbreviations. Actual printed-code conflicts stay held; a matching title or preview-path abbreviation cannot override them.
4. **Keep the completed shared-pool checkpoint.** All 29 sources and observed pagination are collected. Raw products remain keyed by provider listing and `membership_verified: false`; related group IDs are candidate associations, not card-membership assertions.
5. **Resolve the 60 cases by exact printing.** For the 36 shared groups, partition candidates by authoritative checklist/card numbers; where a card belongs to more than one group, keep one printing and multiple membership edges. Candidate checklists now exist for the three combined groups (Dialga/Palkia decks, Bastiodon/Rampardos decks, and Moonlit Pursuit/Dawn Dash), but their exact images/printings remain unverified. For the 20 broader-pool groups, require individual card evidence rather than treating a pool URL as full coverage.
6. **Research Creatures Deck independently.** No dedicated title was found in the observed 800-row index. The cached 75,066-product file contains no product-name hit for `History Gate`, `Creatures` or `Beta Chansey`; new exact-title web searches on 29 October 2026 also found no confirmed Cardmarket product URL. This is limited negative evidence, not proof of absence. Compare all 30 stamped printings against the [PSA checklist](https://www.psacard.com/psasetregistry/tcg/company-sets/2021-pokemon-card-game-25th-anniversary-creatures-deck-corporate-history-1995/composition/22539) and observed individual pages. Never reuse a normal reprint's URL merely because its art or number matches. If a link remains unverified, retain an explicit unresolved/reference-only exception under the existing release policy.
7. **Finish the global acquisition report before vectors.** Report groups with routes, groups traversed, checklist reconciliation, valid images, verified exact-print links, and held/unavailable cases separately. Neither a discovered URL nor a completed listing traversal establishes catalogue completeness. Then run one bulk vector/feature job and prepare one combined regression-tested release and phone index. No per-set publication.

## Existing commands

From the scanapp repository root, start the local listener if not already running:

```bash
.venv-scraper/bin/python api/scripts/ja_set_recovery/local_scraper.py
```

Run the global mapped queue in another terminal. The page budget is a resumable checkpoint limit, not a release boundary:

```bash
.venv-scraper/bin/python api/scripts/ja_set_recovery/collect_listings.py \
  --manifest data/catalogue-gaps/ja-set-recovery-20261029-v3/listing-seeds.json \
  --max-pages 10000
```

A human challenge stops navigation immediately. Keep the same tab/profile; the owner clears any checkbox manually. The collector checks that same page every second, then confirms the observed catalogue content and continues automatically. If the collector exited earlier, rerun the same command with `--confirm` after manual clearance. The collector prioritizes the paused group even if new higher-priority seeds were added while it waited. Never reset a genuinely challenged session merely to make the queue appear idle.

The mapped 276-route traversal and 29-source review-pool traversal are complete locally. Reference-image acquisition has begun for nine checklists; exact-print linking, catalogue image verification, vectors and release gates remain separate work.

The review-pool adapter is available for a deliberate refresh only; its current 29-source checkpoint is complete:

```bash
.venv-scraper/bin/python api/scripts/ja_set_recovery/collect_shared_listings.py \
  --queue data/catalogue-gaps/ja-set-recovery-20261029-v3/shared-listing-review-queue.json \
  --max-pages 10000
```

It writes `shared-listings-progress.json`, `shared-listings-report.json`, and `shared-listings-products.jsonl`. Its CLI shares the mapped collector's process lock and supports the same manual, same-tab confirmation flow if a challenge interrupts the pool lane.

Rebuild the discovery proposal from the frozen index and refresh the acquisition summary:

```bash
.venv-scraper/bin/python api/scripts/ja_set_recovery/discover_seeds.py
.venv-scraper/bin/python api/scripts/ja_set_recovery/recovery.py report
```

Regression checks cover index extraction, excluded foreign/sealed links, ambiguous titles, aliases, held pool scopes, and confirmation after the manifest changes:

```bash
.venv-scraper/bin/python -m pytest scraper \
  api/scripts/ja_set_recovery/test_collect_listings.py \
  api/scripts/ja_set_recovery/test_discover_seeds.py -q
```

- **Mirage's Mew Constructed Starter Deck:** recorded 16 numbered entries and quantities from Bulbapedia; joined all 16 cached Cardmarket products by `pcgK` number. Unnumbered 5 Lightning, 5 Psychic, and 1 Rainbow Energy copies are noted separately; exact image/finish matching remains pending.
- **Feraligatr Constructed Starter Deck:** recorded 16 numbered entries and quantities from Bulbapedia; joined all 16 cached Cardmarket products by `pcgJ` number. Unnumbered Water and Lightning Energy quantities are noted separately; exact image/finish matching remains pending.
- **Meganium Constructed Starter Deck:** recorded 16 numbered entries and quantities from Bulbapedia; joined all 16 cached Cardmarket products by `pcgH` number. Unnumbered Grass and Psychic Energy quantities are noted; the roster says Unown without a letter while Cardmarket labels the candidate Unown [X]. Image and finish matching remain pending.
- **Typhlosion Constructed Starter Deck:** recorded 16 numbered entries and quantities from Bulbapedia; joined all 16 cached Cardmarket products by `pcgI` number. Unnumbered Fire and Fighting Energy are noted; Unown's letter and exact image/finish matching remain pending.
- **Black Deck Kit:** recorded both Bulbapedia half-deck rosters, preserving 26 card-membership rows across 20 distinct numbered `pcgD` products. Separate deck quantities and Energy counts are documented; exact print/image matching remains pending.
- **Silver Deck Kit:** recorded both Bulbapedia half-deck rosters, retaining 27 membership rows across 20 distinct numbered `pcgE` products. Energy is noted per half deck; Dark Dragonite 013/014 map to separate candidates but finish matching remains pending.
- **Deoxys Constructed Starter Deck:** recorded 15 numbered entries and quantities from Bulbapedia; joined all 15 cached Cardmarket products by `pcgB` number. Multi, Grass, Psychic and Fighting Energy quantities are noted separately; image/finish matching remains pending.
- **Rayquaza Constructed Starter Deck:** recorded 15 numbered entries and quantities from Bulbapedia; joined all 15 cached Cardmarket products by `pcgC` number. Multi, Fire, Water and Lightning Energy quantities are noted separately; image/finish matching remains pending.
- **Venusaur/Charizard/Blastoise Random Constructed Starter Decks:** recorded the 52-number union pool from Bulbapedia and joined all cached Cardmarket candidates by `pcgA` number. Per-deck inclusion and copies remain conditional because the contents are randomized. Exact print/image association remains pending.
- **PCG-P Promotional cards:** recorded all 154 numbered entries and joined cached candidates by PCG-P number. Repeated names, stamps and finish variants remain unresolved; the Cardmarket labels are candidate data only.
- **Metagross Constructed Starter Deck:** recorded all 19 numbered entries (one copy each) and joined cached Cardmarket products by `advJ` number. Unnumbered Psychic, Fighting and Metal Energy are noted separately; exact image/finish matching remains pending.
- **Gift Box (Latias):** recorded the 18 numbered Latias half-deck entries (one copy each) and joined cached Cardmarket products by `advH` number. Unnumbered Energy counts are noted; the separate Latios half deck is outside this registry group. Exact image/finish matching remains pending.
- **Gift Box (Latios):** recorded the 18 numbered Latios half-deck entries (one copy each) and joined cached Cardmarket products by `advI` number. Unnumbered Energy counts are noted; the separate Latias half deck is outside this registry group. Exact image/finish matching remains pending.
- **Aqua Deck Kit:** recorded both Bulbapedia half-deck rosters, preserving 36 membership rows across 33 distinct `advG` products. Energy quantities and distinct-number repeated Pokémon are retained; the non-holo Walrein and other exact print/image matching remain pending.
- **Magma Deck Kit:** recorded both Bulbapedia half-deck rosters, preserving 36 membership rows across 33 distinct `advF` products. Energy is noted per half deck; Aggron 017/018 have V1/V2 candidate slugs and finish matching remains pending.
- **Magma VS Aqua: Two Ambitions:** recorded the numbered 001–080 Japanese roster and joined all 80 cached products by `ADVex1` number. Registry count 88 conflicts with the Japanese numbered set size and is documented for scope reconciliation; foil/image matching remains pending.
- **Flygon Constructed Starter Deck:** recorded 19 numbered entries (one copy each) and joined cached Cardmarket products by `advD` number. Unnumbered Grass, Lightning and Rainbow Energy are noted; exact image/finish matching remains pending.
- **Salamence Constructed Starter Deck:** recorded 19 numbered entries (one copy each) and joined cached Cardmarket products by `advE` number. Unnumbered Fire, Water and Rainbow Energy are noted; exact image/finish matching remains pending.
- **Mudkip Constructed Starter Deck:** recorded 19 numbered entries and aligned all cached `advC` candidates; documented three Energy categories (11 unnumbered Energy copies). Exact image/finish matching remains pending.
- **Torchic Constructed Starter Deck:** recorded 19 numbered entries and aligned all cached `advB` candidates; documented 5 Fire, 5 Lightning and 1 Darkness Energy. Exact image/finish matching remains pending.
- **Treecko Constructed Starter Deck:** recorded 19 numbered entries and aligned all cached `advA` candidates; documented 5 Grass, 5 Fighting and 1 Rainbow Energy. Exact image/finish matching remains pending.
- **ADV-P Promotional cards:** recorded all 63 numbered entries and aligned a cached Cardmarket candidate to each number. Repeated names stay separate; exact promo art, stamps and finishes remain pending.
- **J Promotional cards:** recorded both jumbo promo entries and aligned cached Cardmarket candidates by number. Jumbo dimensions and exact image/finish remain unverified.
- **P Promotional cards:** recorded all 47 numbered entries and aligned a cached Cardmarket candidate to each number. Exact promo artwork and e-Reader finishes remain pending.
- **Intro Pack Neo (Chikorita):** recorded the numbered 30-card half deck and 10-card unnumbered side deck, aligning all 40 roster rows to cached candidates. Exact card-face/finish matching remains pending.
- **Intro Pack Neo (Totodile):** recorded the numbered 30-card half deck and 10-card unnumbered side deck, aligning all 40 roster rows to cached candidates. Exact card-face/finish matching remains pending.
- **Neo Premium File 3:** recorded its nine-card roster and linked name-level candidates in the shared Cardmarket promo pool. Exact prints and finishes remain pending.
- **Neo Premium File 2:** recorded its nine-card roster and linked name-level candidates in the shared Cardmarket promo pool. Exact prints and finishes remain pending.
- **Neo Premium File 1:** recorded its nine-card starter evolution roster with broad name-level Cardmarket candidates. Exact print variants remain pending.
- **Intro Pack (Bulbasaur):** recorded 40 numbered cards and the unnumbered Venusaur holo, linking all 41 cached candidates. Exact card-face/finish remains pending.
- **Intro Pack (Squirtle):** recorded 40 numbered cards and the unnumbered Blastoise holo, linking all 41 cached candidates. Exact card-face/finish remains pending.
- **Guren Town Gym Deck:** recorded 26 roster rows covering 64 physical cards. The registry says 25; six names lack candidates in the observed Cardmarket group, and repeated Pokémon variants remain unresolved.
- **Yamabuki City Gym Deck:** recorded 27 roster rows covering 64 physical cards. The registry says 26; candidate gaps and repeated Abra/Gastly variants remain unresolved.
- **Kuchiba City Gym Deck:** recorded 26 roster rows covering 64 physical cards. The registry says 25; common card candidate gaps and repeated variants remain unresolved.
- **Tamamushi City Gym Deck:** recorded 30 roster rows covering 64 physical cards. The registry says 28; common Trainer/Energy candidates and repeated variants remain unresolved.
- **Hanada City Gym Deck:** recorded 25 roster rows covering 64 physical cards. The registry says 24; common Energy/Potion candidate gaps and repeated variants remain unresolved.
- **Nivi City Gym Deck:** recorded 27 roster rows covering 64 physical cards. The registry says 25; Energy candidates and repeated Geodude/Onix assignments remain unresolved.
- **Movie Commemoration Random Pack:** recorded 22 numbered candidates and eight unnumbered Energy types. Number candidates align; Energy routes and exact special foil variants remain pending.


## Checklist recovery completion (30 October 2026)

- Completed the final six checklist jobs; the ledger now reports **336/336 checklist jobs complete**.
- McDonald's Pokémon-e Minimum Pack: 18 numbered Pokémon plus six Basic Energy types with holofoil/non-holofoil variants (30 checklist printing rows). Cardmarket has 24 candidate products; Energy finish associations remain unverified.
- T Promos: all 24 numbered cards listed by Bulbapedia; 24 Cardmarket candidates retained for later exact-print review.
- Tropical Mega Battle: transcribed the 23 entries shown on TCG Collector. Its source roster combines Pokémon VS cards, six VS Energy entries and Tropical Breeze, so historical set membership needs independent reconciliation.
- Southern Islands: recorded 18 Japanese cards and name-level candidates from its 18-product Cardmarket listing; no printed card numbers are asserted.
- Miscellaneous Decks: recorded names for all 73 TCG Collector index entries. Miscellaneous Promos: recorded names for all 298 indexed entries. Both remain aggregate source buckets, with release-level membership and Cardmarket printing identity unresolved.
- Review artifacts: `review/mcdonalds-pokemon-e-minimum-pack-checklist.csv`, `review/t-promos-checklist.csv`, `review/tropical-mega-battle-checklist.csv`, `review/southern-islands-checklist.csv`, `review/miscellaneous-decks-checklist.csv`, and `review/miscellaneous-promos-checklist.csv`, each with a companion `-summary.json`.
- Next phase: image reconciliation is still pending for all **336 groups**. The recovery report still shows **0 verified links, 0 valid images, 0 exact printing mappings, and 0 eligible vectors**. Build exact-print associations before generating the combined vectors.

## Image-source correction (30 October 2026)

- Cardmarket is a product identity and candidate-link source only; do not use its listing thumbnails as production vector imagery.
- Prefer high-resolution card-face assets from the Japanese Pokémon Card Game official card database when available. Pilot check for Mega Gengar ex MBG 003/021: the official detail page identifies the set number and links a 868 × 1212 JPEG. The downloaded Limitless reference scan for the same card is 274 × 381; Limitless states its Japanese card images/text come from pokemon-card.com.
- Keep original source URLs, dimensions, hashes and card-number evidence. Do not upscale low-resolution scans and label them high quality.
- At the time of the initial audit, reuse was held pending permission. On 30 October 2026 the user confirmed that approval to use these images is in place; the audited official images below were then acquired for local catalogue recovery work.

## Official image URL pilot (30 October 2026)

- Implemented a source-only pilot against the official Japanese card-search API using the product filters already exposed by its search page. Each card detail record confirms its Japanese card name, printed set number and `/card_images/large/` URL; rows were joined to the existing checklists by printed number.
- Pilot coverage: Mega Gengar Starter Set **22/22** numbered checklist printings; Mega Diancie Starter Set **22/22**; Battle Partners Deck Build Box **45/45** (53 official product records across two result pages, including eight Basic Energy records); Eevee ex Starter Set ex **20/20**. No official image files were copied.
- Detailed URL evidence is in `review/official-image-source-audit-index.json` and its four group audit files. One MBG 003 official image was measured at **868 × 1212**, compared with the existing 274 × 381 Limitless reference scan.
- This establishes a high-resolution source path. The user's 30 October approval removed the image-use gate for this work; no image was downloaded until after that confirmation.

## Alternative high-resolution source lead (30 October 2026)

- TCGdex documents Japanese-language card data and a `high` image variant at 600 × 825, versus its 245 × 337 `low` variant. This is a stronger resolution lead for vector input than Cardmarket thumbnails and the current Limitless reference scans.
- TCGdex describes its card database as community maintained and invites image contributions. The repository's code/data licence is not evidence that Pokémon card artwork itself is licensed for redistribution, model/vector use, or commercial production. Treat the high-resolution image endpoint as a discovery lead only until the asset reuse terms are confirmed.
- References: https://tcgdex.dev/assets ; https://tcgdex.dev/fr/faq ; https://github.com/tcgdex/cards-database
- The TCGdex API returned HTTP 404 from this workstation during a direct probe. It is not used in the acquisition below; the approved official card database images are the source for this pilot.

## Approved image acquisition and vector pilot (30 October 2026)

- The user confirmed approval to use the images. Downloaded all 120 audited official JPEGs (the 109 checklist-matched records plus 11 unnumbered/basic-Energy or other product records) to `data/catalogue-gaps/ja-set-recovery-20261029-v3/images/official/`. All files passed JPEG signature validation and measured 868 × 1212; total size is 51,381,125 bytes. The download manifest records source URL, card ID, group, number, dimensions, byte size, and SHA-256 for every asset.
- Built an isolated DINOv2-small `pad` review bundle with the existing model revision `ed25f3a31f01632728cabb09d1542f84ab7b0056`: 120 normalized 384-dimensional vectors, including 109 checklist-matched records. The vector IDs use the Japanese set code and collector number where available, with group-scoped keys for unnumbered energy; all 120 are unique and none collide with IDs in the local catalogue preview. The bundle manifest records image/model/vector hashes.
- Files: `images/official/download-manifest.json`, `vectors/official-source-pilot-v2/manifest.json`, and `api/scripts/ja_set_recovery/embed_official_images.py`. The first pilot bundle in `vectors/official-source-pilot/` is superseded by v2, which uses catalogue-style candidate IDs.
- This is a reproducible local review bundle, not an active app catalogue update. The four product groups do not currently exist as exact set/number rows in the local catalogue snapshot, so the new images/vectors are not yet merged into the searchable production index. The next integration step is to add exact printing records and validated catalogue IDs, then build a separate catalogue snapshot for review before any activation or publication.
