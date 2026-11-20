# DISP1: display-only pictures for 27 Japanese rows without an image (2026-11-20)

Staging now serves `PS-CATALOGUE-EN-JA-DISP1-20261120` (schema `pokesingle_completion_20261120_disp1`), built on
LINKS5X. The owner asked for it on 2026-11-20 ("Do it here", then "Yes" to the switch). Production is not touched.

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-DISP1-20261120`, schema `pokesingle_completion_20261120_disp1` |
| Parent served before | `PS-CATALOGUE-EN-JA-LINKS5X-20261120` (record: `docs/catalogue-links5-20261116.md`, PR #131) |
| Built with | `prepare_sql_fixes.py`, fix type `display_image_url`; FIX_KEY `display_only_images`, provenance `display-only-images-20261120` |
| Prepared | cards_updated 27, provenance rows 27, cards_md5 `7207c79266a70ab038ee8cb37d7a722d`, sql_sha256 `500a7e0d…` |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/catalogue-disp1-20261120` (returns to LINKS5X) |
| Release file | `/root/catalogue-disp1-20261120.env` (copy of the live env, only PLANETSCALE_SCHEMA and PLANETSCALE_IMPORT_ID changed) |
| Switch | `scripts/catalogue-release-switch.sh apply`: FORWARD OK, healthy, restarts 0, OOMKilled false |
| Phone index | unchanged: the manifest answers 200 with version `1c75043b…` (51,625 rows) after the switch |

## What changed

Only `remote_image_url` on 27 rows that had `has_image = 0` and no remote address. `has_image` stays 0, so these rows
get no features, no vectors and no phone-index entry: recognition is unchanged. `display_image_url`
(`api/app/card_images.py`) hands a remote address out as `image_url` when the catalogue has no own copy, so the app
shows the picture instead of the placeholder. The addresses are the official pokemon-card.com card database; nothing
was added to the CDN mirror (`docs/card-image-cdn.md`).

| Rows | Picture | Why it is right for these rows |
|---:|---|---|
| 17 | pokemon-card.com DP-era basic energy art (`ENE/000001`..`000008`, one per type) | basic energies of the DP deck kits, constructed decks and half decks (Dialga & Palkia LV.X decks, Heatran vs Regigigas, Magmortar vs Electivire, Bastiodon & Rampardos); that product's energy is this print, the type matches (checked by eye) |
| 1 | `ENE/036465` basic Water Energy | Trainer Battle Decks (`ja:SMK-u02`), product list names this print |
| 8 | `DP3/003114`..`003145` | the Palkia LV.X Constructed Standard Deck Trainers 012-018: exact print, name read on the card |
| 1 | `HSPp/027730` | `ja:HSP-34` Poké Ball 034/034 of Beginning Set Pikachu: exact print |

Why display only: the energy rows share one picture per type (one image for several cards must not become a
recognition reference), and the DP3/HSPp images are 162 x 226 px, below what is used for vectors. Every picture was
opened and compared by eye with the row's name, type and product.

## Gate (1,891 photos)

Run by the clean-up session with the IMG2 feature and artwork bundles (`20261120-img2`), output
`data/catalogue-gaps/ja-links-20261116/out-disp1`, scored against the LINKS5W run with the corrected labels:

| Panel | Right first | Wrong first | Photos |
|---|---|---|---|
| dev | 636 | 3 | 663 |
| dev2 | 232 | 0 | 238 |
| dev3 | 938 | 0 | 963 |

Every panel unchanged, 0 right -> wrong, 0 expected cards lost. Checked again here: all 1,891 photos have the same
status and first answer as the LINKS5W run.

## Checked after the switch

`/api/v1/cards` returns the pokemon-card.com address as `image_url` for `ja:HSP-34`,
`ja:jr-palkia-lv-x-constructed-standard-deck-012`, `ja:jr-magmortar-vs-electivire-deck-kit-magmortar-u05` and
`ja:SMK-u02`; the HSP-34 file answers 200.

## Not included

- 11 rows whose exact picture exists only on Bulbapedia (Pikachu World Collection x9, `ja:SP-123` Lance's Charizard V,
  `ja:SMP-447` Zeraora and Friends). Bulbagarden refuses automated downloads, and handing out Bulbagarden hotlinks is
  not wanted; showing a stored copy without a vector would need a small change to `display_image_url`.
- The other Japanese rows without an image keep the placeholder: no confirmed picture of the exact print.
- No Cardmarket links changed: the deck energies have no Cardmarket product, and the Palkia deck Trainers were linked
  already.

## Going back

```
CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-disp1-20261120 PROJECT=scanapp-scanapp-z1mwj4 \
  COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback
```
returns staging to LINKS5X.
