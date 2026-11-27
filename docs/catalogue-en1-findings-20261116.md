# EN1 findings: English rows checked on IMG1 (2026-11-16)

EN1 is on hold: nothing was built or applied. The only change found is one link with no product id, which is not worth a 1,891-photo gate on its own, so it goes into the next batch. All checks were read against `pokesingle_completion_20261116_img1`.

## Yellow A Alternate rows (`en:xya-*`): duplicates, no image

None of the 6 rows is a separate printing. Each one duplicates an existing row that already has a TCGdex image, a vector and the same Cardmarket product:

| Row | Duplicate of | Cardmarket product |
|---|---|---|
| `en:xya-24a` M Manectric-EX | `en:xy4-24a` | Phantom-Forces/MManectric-EX-V2-PHF24a |
| `en:xya-28a` Jolteon-EX | `en:g1-28a` | Generations/Jolteon-EX-V2-GEN28a |
| `en:xya-54a` Zygarde-EX | `en:xy10-54a` | Fates-Collide/Zygarde-EX-V2-FCO54a |
| `en:xya-55a` M Lucario-EX | `en:xy3-55a` | Furious-Fists/MLucario-EX-V2-FFI55a |
| `en:xya-92a` Trainers' Mail | `en:xy6-92a` | Roaring-Skies/Trainers-Mail-V2-ROS92a |
| `en:xya-107a` Professor Sycamore | `en:xy9-107a` | BREAKpoint/Professor-Sycamore-V2-BKP107a (product 288282) |

I eye-checked all 6 twin images (`assets.tcgdex.net/en/xy/<set>/<n>a`). Each shows the yellow "A" circle next to the collector number: 24a/119, 28a/83, 54a/124, 55a/111, 92a/108 and 107a/122, all ©2017. So the Yellow A printing is already indexed. Five of the `xya` rows already carry the Cardmarket provenance `verified-identical-source-product-alias:en:<twin>`. `xya-28a` carries `exact_printed_artist_collector_yellow_a_verified_owner_alias_v1`. Giving the `xya` rows images would only add second copies of cards that are already indexed. They are left as they are.

## `en:mep-120` Celebratory Fanfare: link for the next batch

The row has an image and a vector but no Cardmarket link. `cardmarket_products` has an exact match on expansion, name and number, and no card is matched to it yet:

- url `https://www.cardmarket.com/en/Pokemon/Products/Singles/MEP-Black-Star-Promos/Celebratory-Fanfare-MEP120`
- expansion `MEP-Black-Star-Promos`, name `Celebratory Fanfare (MEP 120)`

The product id is unknown, so the link would be URL only (`cardmarket_id` NULL), set with `api/scripts/ja_set_recovery/prepare_sql_fixes.py`. The Celebratory Fanfare products in other expansions (M-P, SV-P, S-P, SEA, Thai, Indonesian, Radiant Energy) are different printings and are not used.

## `en:bwp-BW77` Pikachu, `en:bwp-BW78` Raichu: no Cardmarket product found

- Our crawl of `BW-Black-Star-Promos` (106 products) has BW70–BW76 and BW79, but neither BW77 nor BW78. No other expansion has a matching Pikachu or Raichu (the `BW-Promos` ones are Japanese BW-P cards).
- pokemontcg.io has no `cardmarket` mapping for `bwp-BW77` or `bwp-BW78`, though `bwp-BW76` has one. TCGdex has no pricing for any of the three.
- Price aggregators that show Cardmarket fields have no data for either card.
- Bulbapedia's search snippet says images of BW77 and BW78 only appeared on pokemon.com in July 2014, as previously unknown promos.
- `cardmarket.com` and `bulbapedia.bulbagarden.net` returned HTTP 403 to a plain fetch. I did not try to get past the bot check.

The links stay empty (provenance `none`). Someone with normal browser access to Cardmarket could check the BW Black Star Promos list by hand.

## Left alone

The 28 `en:exu-*` Unown rows are kept duplicates of `ex10-unown-*` and are hidden from lists on purpose.
