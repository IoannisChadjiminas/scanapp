# Delta Reign rarities: catalogue RAR1 (2026-11-27)

Delta Reign (`en:me06`, 141 cards, added on 13 November in second batch I) had no rarity on any
card, so the app's rarity filter for that expansion was empty. TCGdex has every card's rarity
(its rows were updated on 2026-11-08); the batch builder had stored `rarity = NULL` for every new
card (`prepare_sql.py`), so the 13 November rows never carried it. RAR1 fills the 141 rarities and
is served on staging. Production is not touched.

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-RAR1-20261127`, schema `pokesingle_completion_20261127_rar1` |
| Parent served before | `PS-CATALOGUE-EN-JA-DISP1-20261120` (`pokesingle_completion_20261120_disp1`, unchanged) |
| Cards digest | `9c85e3324cdfbb004c00e69abb1e38cb` → `cfb62e61c601fc4d330e3f799e6441e4` (62,091 rows; the old value was reproduced first with the loader's hashing) |
| Reference features | `20261120-img2` → `20261127-rar1`, manifest `83434222…` → `a8fc5241e32928168d9590d2d701fe1e5bc70a7450a789498bc81398624b9785` |
| Artwork bundle, vectors | unchanged (`20261120-img2`); rarity is not an input to either |
| Code staging runs | main `5e00dce` |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/catalogue-rar1-20261127` (returns to DISP1) |
| Switch | FORWARD OK, healthy, restarts 0, OOM false, `catalogue corrections applied=0` |
| Run folder | `data/catalogue-gaps/rar1-20261127` (TCGdex rows, SQL, feature build, replay results, score) |

## What changed

- **Rarities.** All 141 rows set from `https://api.tcgdex.net/v2/en/cards/me06-NNN`, only where the
  row still held NULL. Each card's name and number were checked against the TCGdex row first; all
  141 agreed. Labels are written as TCGdex writes them, the same as `me05`: Common 50, Uncommon 33,
  Ultra Rare 17, Illustration rare 14, Rare 10, Double rare 10, Special illustration rare 6,
  Mega Hyper Rare 1.
- **Reference features.** The feature bundle is signed over every card's id, image path and rarity,
  and a full-art rarity picks the full-art box. The 37 full-art cards (Ultra Rare, Illustration
  rare, Special illustration rare) were rebuilt with the full-art box
  (`api/scripts/ja_set_recovery/rebuild_features.py`, in `scanapp-api-staging:24856ba9`, whose
  processing contract equals the served bundle's); the other 55,654 files are hard links to
  `20261120-img2`, whose files and manifest were checked unchanged on the Mac and on the staging
  volume. New catalogue signature `d5130e2d…`.
- **Import manifest.** Target schema, import id, cards digest, `reference_feature_manifest_sha256`,
  parent and `rebuilt_from` updated; a `corrections` entry and `delta_reign_rarities` appended.
  SQL from `prepare_sql_rarity.py`, applied with a 1 h admin role in one guarded transaction
  (parent manifest md5 checked before and after, counts, the 141 changed rows, the validated import).

## Gate (1,891 photos, against IMG2's accepted run)

Local docker, image `scanapp-api-staging:24856ba9`, code of the IMG2 gate, the same replay
settings and shards, 3 lanes; each lane loads the catalogue once (`replay_lane.py`), so one 1 h
read role covered the run. Scored with `score_gate.py` and the corrected labels; scoring IMG2's
run against itself reproduced IMG2's recorded gate exactly.

| Panel | Photos | Right first | Wrong first | Right offered | Upper bound |
|---|---:|---|---|---|---|
| dev | 681 | 636 → 636 | 3 → 3 | 663 → 663 | 1.3% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.4% |

No answer changed in any field (status, best, suggestions, alternatives, printings). No panel
photo is a Delta Reign card; two photos offer Delta Reign cards as look-alike alternatives, as on
IMG2 (see second batch J), and those are unchanged. So the panels show the release does not
disturb other cards; they do not test the 37 rebuilt full-art features on a Delta Reign photo.

## After the switch

`/api/v1/search-options?set=en:me06` returns the eight rarities with the counts above;
`/api/v1/cards/en:me06-104` (Masquerain) returns `Illustration rare`; `me05` still has 8.

## Not verified

A camera photo of a Delta Reign full-art card; the app (it reads rarities from the API, no app
change); the phone index (not rebuilt; its build scripts do not read rarity).

## Builder fix

`prepare_sql.py` wrote `category`, `rarity` and `illustrator` as NULL for every batch card. Now
`fill_tcgdex_fields.py` adds them to a batch's TCGdex rows, `prepare_cards.py` carries them and
refuses a TCGdex row without a rarity, and `build_release.py` and `prepare_sql.py` use that rarity
for the stored row, the feature art box and the feature signature alike.

Other batch-built rows still have no rarity: second batch A1–K (Start Deck 100, the starter
products, 30th Celebration, promos, energies) and the Japanese recovery. Their sources are mostly
Limitless and official lists, not TCGdex, so each needs its own source before a release like this
one.

## Going back

`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-rar1-20261127 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
