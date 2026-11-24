# Cardmarket product numbers per card

The catalogue gives each card a Cardmarket product number, which the server uses to read the card's daily price from Cardmarket's price file. For 1,825 cards that number was shared with another card on a different Cardmarket page (the holo and non-holo of a name, a full art and its regular card, two promos), so one of them showed the other's price.

The catalogue is published separately and is not changed here. The server keeps its own answer in a local table and reads prices with that.

## What ships with the server

`api/app/cardmarket_card_products.csv` holds the reviewed product number for 1,821 of those cards. It is part of the server image.

| Column | Meaning |
|---|---|
| `card_id` | Catalogue card id |
| `product_id` | The card's own Cardmarket product |
| `previous_product` | The number the catalogue gives it (978 differ, 843 are the same) |
| `name`, `number`, `set` | For reading the list; not used by the server |
| `evidence` | How the number was established |

| Evidence | Cards | Strength |
|---|---|---|
| `read from Cardmarket` | 626 | Read from the card's page or its set listing on Cardmarket, 23–24 Nov 2026 |
| `attacks match one product` | 997 | The card's attacks match exactly one product name in Cardmarket's product list. 30 of 30 sampled matched their page |
| `page photo` | 114 | The product photo address stored for the card's page |
| `attacks plus a set or type tag` | 53 | As above, allowing one extra tag such as `BW` or `Prime` in the product name |
| `only free product with this name` | 31 | Trainer and energy cards matched by name. The weakest group; 2 were checked against Cardmarket |

## What production needs

Nothing by hand. Deploy a server version that contains this file.

At every start, after the catalogue is loaded, the server:

1. applies the file to `cardmarket_card_products` in `/data/catalog.sqlite` (source `review`);
2. marks any other card whose catalogue number is shared across different Cardmarket pages as not known (source `shared`), so it shows no daily price instead of another card's;
3. logs one line under `cardmarket.prices`: `shared product numbers reviewed_changes=<n> withheld cards=<n>`.

To confirm after a production deploy:

- The log line shows `reviewed_changes=1821` on the first start and `0` on later ones. `withheld cards` should be 4 with the catalogue import `PS-CATALOGUE-EN-JA-DISP1-20261120`.
- `GET /api/v1/cards/en:bw8-78` (Lucario 78, Plasma Storm) lists a Cardmarket trend from product 280818, not 280817.

A new catalogue import can introduce new shared numbers. They are withheld automatically; `withheld cards` in the log line says how many.

## Cards still without a number

Four Chinese cards share product 821707 and have no Cardmarket page in the catalogue: `zh-cn:SV9a-022`, `zh-cn:SV9a-071`, `zh-tw:SV9a-022`, `zh-tw:SV9a-071`. They show no daily Cardmarket price. They are left for a later phase.

## Changing the list

- **A correction:** edit the row in the CSV and deploy. The next start applies it.
- **A new card:** add a row with `card_id` and `product_id`. The other columns may be empty.
- **Without a restart:** `api/scripts/apply_card_products.py <csv> /data/catalog.sqlite`. The script is not in the image; pipe it to `python -` inside the API container.
- **From the app:** when a phone reads a withheld card's own Cardmarket page ("Check live offers"), the server records that page's product for the card (source `page`). A reviewed row always wins over a page read.

Removing a row from the CSV does not remove it from a server that already applied it. Delete the row from `cardmarket_card_products` on that server as well.
