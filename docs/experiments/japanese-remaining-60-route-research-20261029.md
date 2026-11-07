# Remaining 60 Japanese groups — route research, 29 October 2026

The completed mapped queue remains 276 groups. This pass does not add group memberships or mark any held group collected. It verifies collection entrances and makes the remaining work explicit.

| Route scope | Groups | Result |
| --- | ---: | --- |
| Shared collection | 36 | Observed shared route; partition by checklist before mapping |
| Combined collections | 3 | Observed child routes; union and deduplicate printings |
| Broad candidate pools | 20 | Pool route exists; individual membership remains unverified |
| No confirmed route | 1 | Creatures Deck remains unresolved |

## Evidence acquired

All 13 previously uncached expansion entrances were checked in the visible browser. Each has an observed Singles link. The other 16 sources are fully traversable from existing cached English page evidence; translated pagination aliases are normalized before lookup. Existing source files and the mapped queue were not rewritten. These 16 sources contain 662 product rows across their source inventories; counts do not prove subgroup coverage.

| Newly checked entrance | Advertised cards | Japanese badge |
| --- | ---: | --- |
| [Battle Strength Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Battle-Strength-Decks) | 42 | Yes |
| [VMAX Starter Decks](https://www.cardmarket.com/en/Pokemon/Expansions/VMAX-Starter-Decks) | 61 | Yes |
| [Sword & Shield Starter Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Sword-Shield-Starter-Decks) | 117 | Yes |
| [Mewtwo vs Genesect Deck Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Mewtwo-vs-Genesect-Deck-Kit) | 34 | Yes |
| [Gift Box Mew • Lucario](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Mew-Lucario) | 62 | Yes |
| [Master Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Master-Kit) | 42 | Yes |
| [Quick Construction Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) | 91 | Yes |
| [Gift Box Emerald](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Emerald) | 38 | Yes |
| [Base Expansion Pack](https://www.cardmarket.com/en/Pokemon/Expansions/Base-Expansion-Pack) | 157 | Yes |
| [Unnumbered Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos) | 213 | Yes |
| [Expansion Sheet](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Sheet) | 125 | Yes |
| [Unnumbered Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) | 80 | Not shown |
| [Expansion Pack](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Pack) | 102 | Yes |

Advertised counts describe the provider expansion. They are not reconciliation counts. Expansion entrances were checked, not all listing pages under the 13 sources. The Unnumbered Energies page does not show a Japanese badge and cannot certify the annual Japanese energy groups. Preserve language/design/year/stamp/finish distinctions.

## Creatures Deck

Cardmarket’s own search for [History Gate](https://www.cardmarket.com/en/Pokemon/Products/Search?category=-1&searchString=History+Gate&searchMode=v2) and [Creatures](https://www.cardmarket.com/en/Pokemon/Products/Search?category=-1&searchString=Creatures&searchMode=v2) returned “Sorry, no matches for your query”. The [PSA checklist](https://www.psacard.com/psasetregistry/tcg/company-sets/2021-pokemon-card-game-25th-anniversary-creatures-deck-corporate-history-1995/composition/22539) supplies the distinctive card identity. Targeted web searches and the cached official 75,066-product file also did not establish a matching route. This is limited negative evidence: preserve unresolved status, never substitute normal reprint URLs for corporate-history stamped printings.

## Reproducible outputs and next collection

The ignored run directory contains `review/remaining-route-live-checks.json`, `review/remaining-route-acquisition-audit.json`, and its 60-row CSV. Rebuild the latter with:

```sh
.venv-scraper/bin/python api/scripts/ja_set_recovery/audit_remaining_routes.py
```

The audit is offline, reuses existing evidence and never asserts card membership. Its regression check passes for translated pagination aliases and missing pages. The shared-pool runner had an indentation error in its waiting-for-owner branch; that indentation was repaired and compilation now passes. The wider mapped-collector regression run still has two failing challenge-resume tests (4 passing); this pass does not claim those behaviors verified.

Use the existing many-group review queue for collection, not the one-group seed list. Reuse the 16 cached sources and traverse the 13 other sources once each with observed pagination. After acquisition, partition the 36 subgroups, union the three combined groups and reconcile individual printings for the 20 pool cases. No vectors, images, live databases or staging deployment were changed.

## Every held group

| Group | Scope | Collection sources |
| --- | --- | --- |
| Cobalion Battle Strength Deck | shared_collection_route | [Battle-Strength-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Battle-Strength-Decks) |
| Terrakion Battle Strength Deck | shared_collection_route | [Battle-Strength-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Battle-Strength-Decks) |
| Virizion Battle Strength Deck | shared_collection_route | [Battle-Strength-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Battle-Strength-Decks) |
| 25th Anniversary Creatures Deck | no_confirmed_route | Unresolved |
| Charizard Starter Set VMAX 2 | shared_collection_route | [VMAX-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/VMAX-Starter-Decks) |
| Charizard Starter Set VMAX | shared_collection_route | [VMAX-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/VMAX-Starter-Decks) |
| Grimmsnarl Starter Set VMAX | shared_collection_route | [VMAX-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/VMAX-Starter-Decks) |
| Fighting Starter Set V | shared_collection_route | [Sword-Shield-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Sword-Shield-Starter-Decks) |
| Fire Starter Set V | shared_collection_route | [Sword-Shield-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Sword-Shield-Starter-Decks) |
| Grass Starter Set V | shared_collection_route | [Sword-Shield-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Sword-Shield-Starter-Decks) |
| Lightning Starter Set V | shared_collection_route | [Sword-Shield-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Sword-Shield-Starter-Decks) |
| Water Starter Set V | shared_collection_route | [Sword-Shield-Starter-Decks](https://www.cardmarket.com/en/Pokemon/Expansions/Sword-Shield-Starter-Decks) |
| Mewtwo vs Genesect Deck Kit (Genesect) | shared_collection_route | [Mewtwo-vs-Genesect-Deck-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Mewtwo-vs-Genesect-Deck-Kit) |
| Mewtwo vs Genesect Deck Kit (Mewtwo) | shared_collection_route | [Mewtwo-vs-Genesect-Deck-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Mewtwo-vs-Genesect-Deck-Kit) |
| Heatran vs Regigigas Deck Kit (Heatran) | shared_collection_route | [Heatran-vs-Regigigas-Deck-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Heatran-vs-Regigigas-Deck-Kit) |
| Heatran vs Regigigas Deck Kit (Regigigas) | shared_collection_route | [Heatran-vs-Regigigas-Deck-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Heatran-vs-Regigigas-Deck-Kit) |
| Magmortar vs Electivire Deck Kit (Electivire) | shared_collection_route | [Magmortar-vs-Electivire-Deck-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Magmortar-vs-Electivire-Deck-Kit) |
| Magmortar vs Electivire Deck Kit (Magmortar) | shared_collection_route | [Magmortar-vs-Electivire-Deck-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Magmortar-vs-Electivire-Deck-Kit) |
| Dialga & Palkia LV.X Constructed Standard Decks | combined_collection_routes | [Dialga-LVX-Constructed-Standard-Deck](https://www.cardmarket.com/en/Pokemon/Expansions/Dialga-LVX-Constructed-Standard-Deck); [Palkia-LVX-Constructed-Standard-Deck](https://www.cardmarket.com/en/Pokemon/Expansions/Palkia-LVX-Constructed-Standard-Deck) |
| Bastiodon the Defender & Rampardos the Attacker Constructed Half Decks | combined_collection_routes | [Bastiodon-the-Defender](https://www.cardmarket.com/en/Pokemon/Expansions/Bastiodon-the-Defender); [Rampardos-the-Attacker](https://www.cardmarket.com/en/Pokemon/Expansions/Rampardos-the-Attacker) |
| Entry Pack | candidate_pool_only | [Space-Time-Creation](https://www.cardmarket.com/en/Pokemon/Expansions/Space-Time-Creation) |
| Mew • Lucario Gift Box (Crawdaunt) | shared_collection_route | [Gift-Box-Mew-Lucario](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Mew-Lucario) |
| Mew • Lucario Gift Box (Lucario) | shared_collection_route | [Gift-Box-Mew-Lucario](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Mew-Lucario) |
| Mew • Lucario Gift Box (Mew) | shared_collection_route | [Gift-Box-Mew-Lucario](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Mew-Lucario) |
| Mew • Lucario Gift Box (Mightyena) | shared_collection_route | [Gift-Box-Mew-Lucario](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Mew-Lucario) |
| Mew • Lucario Gift Box (Pokémon ☆) | shared_collection_route | [Gift-Box-Mew-Lucario](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Mew-Lucario) |
| Master Kit (Bulbasaur) | shared_collection_route | [Master-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Master-Kit) |
| Master Kit (Side Deck) | shared_collection_route | [Master-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Master-Kit) |
| Master Kit (Torchic) | shared_collection_route | [Master-Kit](https://www.cardmarket.com/en/Pokemon/Expansions/Master-Kit) |
| Fighting Quick Construction Pack | shared_collection_route | [Quick-Construction-Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) |
| Fire Quick Construction Pack | shared_collection_route | [Quick-Construction-Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) |
| Grass Quick Construction Pack | shared_collection_route | [Quick-Construction-Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) |
| Lightning Quick Construction Pack | shared_collection_route | [Quick-Construction-Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) |
| Psychic Quick Construction Pack | shared_collection_route | [Quick-Construction-Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) |
| Water Quick Construction Pack | shared_collection_route | [Quick-Construction-Packs](https://www.cardmarket.com/en/Pokemon/Expansions/Quick-Construction-Packs) |
| Emerald Gift Box (Deoxys) | shared_collection_route | [Gift-Box-Emerald](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Emerald) |
| Emerald Gift Box (Rayquaza) | shared_collection_route | [Gift-Box-Emerald](https://www.cardmarket.com/en/Pokemon/Expansions/Gift-Box-Emerald) |
| Leaders' Pokémon: Movie Limited Edition | candidate_pool_only | [Pokemon-CardVS](https://www.cardmarket.com/en/Pokemon/Expansions/Pokemon-CardVS) |
| Pokémon-e Starter Deck | candidate_pool_only | [Base-Expansion-Pack](https://www.cardmarket.com/en/Pokemon/Expansions/Base-Expansion-Pack) |
| Neo Premium File 3 | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos) |
| Neo Premium File 2 | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos) |
| Neo Premium File 1 | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos) |
| Quick Starter Gift Set (Green) | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos); [Expansion-Sheet](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Sheet) |
| Quick Starter Gift Set (Red) | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos); [Expansion-Sheet](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Sheet) |
| Vending Machine Series 3 (Green) | shared_collection_route | [Expansion-Sheet](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Sheet) |
| Vending Machine Series 2 (Red) | shared_collection_route | [Expansion-Sheet](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Sheet) |
| Vending Machine Series 1 (Blue) | shared_collection_route | [Expansion-Sheet](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Sheet) |
| 2021 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2019 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2018 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2016 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2015 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2013 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2012 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2009 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| 2006 Energies | candidate_pool_only | [Unnumbered-Energies](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Energies) |
| Moonlit Pursuit & Dawn Dash | combined_collection_routes | [Moonlit-Pursuit](https://www.cardmarket.com/en/Pokemon/Expansions/Moonlit-Pursuit); [Dawn-Dash](https://www.cardmarket.com/en/Pokemon/Expansions/Dawn-Dash) |
| Tropical Mega Battle | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos) |
| Miscellaneous Decks | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos); [Nivi-City-Gym](https://www.cardmarket.com/en/Pokemon/Expansions/Nivi-City-Gym); [Guren-Town-Gym](https://www.cardmarket.com/en/Pokemon/Expansions/Guren-Town-Gym); [Yamabuki-City-Gym](https://www.cardmarket.com/en/Pokemon/Expansions/Yamabuki-City-Gym); [Kuchiba-City-Gym](https://www.cardmarket.com/en/Pokemon/Expansions/Kuchiba-City-Gym); [Tamamushi-City-Gym](https://www.cardmarket.com/en/Pokemon/Expansions/Tamamushi-City-Gym); [Hanada-City-Gym](https://www.cardmarket.com/en/Pokemon/Expansions/Hanada-City-Gym); [Expansion-Pack](https://www.cardmarket.com/en/Pokemon/Expansions/Expansion-Pack) |
| Miscellaneous Promos | candidate_pool_only | [Unnumbered-Promos](https://www.cardmarket.com/en/Pokemon/Expansions/Unnumbered-Promos) |
