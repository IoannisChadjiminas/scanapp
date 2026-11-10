# Phase E catalogue release

Everything needed to put the English and Japanese catalogue release that runs on staging onto
another deployment with one command, and to take it back with one command.

Nothing here switches production. Production is switched by the owner, once, with the command
under "Switch".

## What the release is

`catalogue-release.env` in this directory is the whole release. It holds no secrets.

| Part | Value |
| --- | --- |
| Catalogue schema | `pokesingle_completion_20261110_jarec15` (PlanetScale `pokesingle-db`, branch `main`) |
| Import id | `PS-CATALOGUE-EN-JA-REC15-20261110` |
| Reference features | `/data/reference-features/20261109-ja-recovery-img6` |
| Artwork vectors | `/data/artwork/20261110-ja-recovery-vec15` |
| Recognition flags | 20, all code defaults: 16 since PR 117, and the four footer-evidence flags of PR 119 |
| Phone index version | `63a3707111add1d751949858766dd479d60d7f248367a389173f110d3842bbdf` (en 25,430, ja 23,741, zh-tw 2,260 rows) |

The artifact manifest (sha256 of every file under the two artifact directories and `models`,
112,478 lines, paths relative to the data volume) is too large for git. It is on the staging host
at `/etc/scanapp-staging/release-manifests/phase-e-20261110.sha256`; its own sha256 is
`c8a6ed5d949aa16205a6eb1be4af5576fcfda8b9e55931c7b9d338f6ce1e2d51`. Copy it to the target host
with the artifacts and pass it as `MANIFEST`.

## Switch

Run on the host that runs the deployment, from a checkout of this repository at the released
commit:

```bash
RELEASE_FILE=docs/release/phase-e/catalogue-release.env RELEASE_NAME=phase-e-20261110 PROJECT=<compose project> MANIFEST=/etc/scanapp-production/release-manifests/phase-e-20261110.sha256 scripts/catalogue-release-switch.sh apply
```

`apply` saves the release in use, writes the rollback file, checks the host (preflight), installs
the release, recreates only the API container, waits for health and checks that the API reports
this import id and every flag. If any of that fails it rolls back by itself and exits non-zero.

## Roll back

```bash
RELEASE_NAME=phase-e-20261110 PROJECT=<compose project> scripts/catalogue-release-switch.sh rollback
```

The rollback file is the release that ran before, with every flag this release adds set to
`false`. It is written to `<CONFIG_DIR>/catalogue-rollback/phase-e-20261110/` before anything is
changed. On a first start (nothing ran before) rollback stops the API and removes the release
file.

## Preflight checklist

`scripts/catalogue-release-switch.sh preflight` checks the items marked (script). The others are
the owner's.

1. The deployment's code is at the released commit, and that commit's defaults include all 20
   flags (`api/tests/test_five_flag_defaults.py`, `api/tests/test_footer_evidence.py`).
2. (script) `<CONFIG_DIR>/planetscale.env` exists: a read role on `pokesingle-db` for the schema
   above. The role must not expire; staging's replay roles do.
3. (script) The compose file is present in the code directory.
4. (script) The data volume exists and holds the two artifact directories and `models`.
5. (script, with `MANIFEST`) Every artifact file matches the manifest.
6. (script) Memory: 3,072 MB available for a first start, the API container's limit in the
   compose file.
7. Production only: `PORTFOLIO_DATABASE_URL` and `SCANAPP_SERVICE_TOKEN` are set in Dokploy;
   `docs/production-single-server.md` lists the rest of the provisioning.
8. The phone index the app downloads is the version above, or `CARD_INDEX_PUBLISH` stays `false`
   (production's default) until it is.
9. Image delivery is unchanged by this release (`docs/card-image-cdn.md`): no Cardmarket product
   photo and no listing photo is mirrored.

## Staging and production configuration

Production is not provisioned (`auctaro-prod` has no `/etc/scanapp-production`). The release file
is the same on both; the differences are in the compose files:

| Setting (compose default) | Staging (`compose.dokploy.yaml`) | Production (`compose.dokploy.production.yaml`) |
| --- | --- | --- |
| Config directory | `/etc/scanapp-staging` | `/etc/scanapp-production` |
| `PORTFOLIO_DATABASE_URL`, `SCANAPP_SERVICE_TOKEN` | optional | required, deployment fails without them |
| `APP_SLAB_DETECTION` | `false` | `true` |
| `GRADING_REQUIRES_CLIENT_HINT` | `false` | `true` |
| `CARD_INDEX_PUBLISH` | `true` | `false` |
| `STORE_CAPTURES` | `true` | `false` |
| `SCAN_WAIT_LIMIT` | `6` | `2` |
| `SCAN_LANES` | not passed (code default 1) | `1` |
| `PRICE_GUIDE_ENABLED`, `TCGDEX_PRICES_ENABLED` | not passed (code default `true`) | `false` |
| `STAGE1B_FRAME_FALLBACK`, `STAGE1_FAMILY_VECTOR`, `STAGE1_TWIN_GUARD` | `true` | `false` |
| `STAGE1_EARLY_EXIT`, `STAGE1_BACKGROUND_CHECK`, `STAGE1B_TEXT_VERIFY`, `STAGE1B_SERVER_FRAME`, `STAGE1_SET_TOTALS`, `STAGE1_NORMALIZE_DUPLICATES`, `STAGE1_PRINTING_GROUPS`, `STAGE1_PROMO_NUMBERS`, `STAGE1_DIAGNOSTICS` | `true` | not passed (code default `false`) |
| `STAGE1_REQUIRE_CONFIRMATION`, `STAGE1_SAMPLE_RATE`, `STAGE1_CHECK_PHONE_INPUTS`, `STAGE1_FUZZY_NAME` | passed with the code default | not passed (same value) |
| `APP_CLIENT_EMBEDDING`, `APP_CLIENT_LABEL`, `APP_CLIENT_QUALITY` | `true` | not passed (code default `false`) |
| `APP_FINDER_FRAMES` and its three limits | passed with the code default | not passed (same value) |

The API memory limit is 3,072 MB in both files.

With these defaults production does not answer from the phone fast path at all
(`STAGE1_EARLY_EXIT` is off): every scan runs the full pipeline, which is what the proof panel
measures. Turning the fast path on in production is a separate decision with its own settings.

## What was measured

See `docs/release/phase-e/RESULTS.md`.
