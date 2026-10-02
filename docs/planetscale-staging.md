# Staging catalogue source

## STAGING-ACCURACY-007/008 — 2026-10-01

User explicitly approved each change. Accuracy-007 added a card name/language
guard to owner-first URL resolution; its 215 unit tests passed, but live negative
verification still accepted the wrong Victini URL. That chain was halted.
Read-only catalogue inspection found the actual bypass: Arctibax's primary URL
is null, and the legacy unowned-SKU fallback returned before the read-only guard.

Accuracy-008 moves the read-only identity guard before that fallback. All 216
API tests pass, including the exact primary-null/grouped-listing regression.
Deployed only the API through the bounded SSH/Compose script. The live probe
returns 409 for Victini on Arctibax and confirms neither card nor URL was saved.
API container is `20e7f885389d`; web/scraper IDs remain unchanged. Runtime
`cardmarket.py` SHA-256 matches local source:
`20367845ccc41b485040411e31349350f4663886994f74dec4bbe147e7427b87`.
Health is ready with the same validated import, 48,652 cards and 37,755 vectors.
No PlanetScale data, credentials, thresholds, web or scraper were changed.
Both downloaded English Fuecoco V1/V2 photos passed the live Flutter finish
selection/confirmation/history/test-portfolio flow against accuracy-008.
Evidence is saved in the Flutter repository as
`docs/scan-variant-selection-accuracy-008.json` and
`docs/scan-variant-quarantine-live.json`.

The previous accuracy-007 image/source are retained as
`scanapp-staging-rollback:staging-accuracy-008` and
`/etc/scanapp-staging/rollback-staging-accuracy-008/`. Accuracy-007 has its own
matching rollback image/directory. Local deployment log:
`/tmp/scanapp-staging-accuracy-008-deploy.log`. Changes remain uncommitted/unpushed;
include the complete tested runtime changes before a future Git-triggered rollout.

## STAGING-ACCURACY-006 — 2026-10-01

User explicitly approved STAGING-ACCURACY-006 in this chat. Applied only to the
Scanapp staging API via SSH and `docker compose ... build api` followed by
`up -d --no-deps api`; no Git push/deployment hook was used. Web and scraper
container IDs remained `3dfcfe247c40` and `66b2a00e20b3`. API changed from
`61dd9b739ad1` to `284ea2331c99`; runtime checksums matched the local seven-file
patch. Health returned ready with the same validated PlanetScale snapshot.

Changes: bounded visual orientation fallback before OCR; gameplay-number
filtering (HP/level/Pokedex/weakness are not collector evidence); BASIC/STAGE name
boilerplate filtering; variant-title identity quarantine and a 409 rejection of
conflicting linked listings; ranking policy `rank-v5`. Good portrait crops need
one embedding; sideways crops try both portrait directions, weak portrait crops
try 180 degrees. Orientation changes require the existing visual floor and a
material improvement of at least the existing gap. OCR runs once after selection.

PlanetScale `pokesingle/pokesingle-db/main` remained read-only. No mappings,
vectors, credentials, thresholds or `ENABLE_MATCHED=false` were changed. The
bad Arctibax/Victini source linkage is quarantined, not erased from PlanetScale;
source-data correction still requires a separately reviewed snapshot change.

Validation before rollout: 214 API tests passed (one pre-existing Starlette
deprecation warning). Paired recognition on the same 36 stored diagnostic JPEGs,
using a separate process and in-memory result database, improved correct top
identities from 28/34 positive probes to 32/34. No previously correct identity
regressed; no hypothetical false confident acceptance occurred with automatic
matching enabled only in memory. Arctibax variant contamination disappeared.
These are stress probes, not a representative camera accuracy benchmark.

Rollback image: `scanapp-staging-rollback:staging-accuracy-006`.
Protected source archive, image name and before/after container inventory:
`/etc/scanapp-staging/rollback-staging-accuracy-006/`. The deployment script rolls
back its bounded source files and retags the preserved image if build/restart or
readiness verification fails. Proposed orientation source is moved into that
archive on rollback, not deleted. Preserve existing source edits to the variant
history endpoint/schema and generated Compose routing.

Runtime source was deployed without committing/pushing. A future Git rollout
must include these changes (and earlier staging variant/history changes) or it
can revert staging behavior. Live app and variant-feedback results are recorded
in the Flutter repository's `docs/scan-edge-case-fixes.md` after verification.

## Connection and operating model

The existing Dokploy Scanapp service uses `compose.dokploy.yaml`. Its API defaults
to `CATALOGUE_BACKEND=planetscale`; other Compose files and local development still
default to SQLite. Only the API receives database credentials, never the web build.

Create a dedicated `pokesingle-staging` user-defined role on `pokesingle-db/main`
with **only** `pg_read_all_data`. The loader rejects admin/write roles and requires
hostname-verified TLS. Save `PLANETSCALE_DATABASE_URL=<connection URL>` in a
root-owned mode-0600 file on the staging host:
`/etc/scanapp-staging/planetscale.env`. This is outside Dokploy's Git checkout;
automatic redeploys retain it. `PLANETSCALE_ENV_FILE` may select a different secret
file. Never commit the URL or put it in frontend variables or build arguments.

At API startup one read-only, repeatable-read transaction fetches the pinned
`PS-IMPORT-001-20261001` validated snapshot from schema
`pokesingle_import_20261001`. Catalogue and listing rows are checked against the
import digests and cached in an attached **in-memory** SQLite database for existing
FTS, mapping and variant logic. Every vector checksum and aggregate is checked,
and original manifest ID order is preserved. Vector arrays remain in memory;
old local catalogue rows and NPY bundles are not the recognition source.

All shared cache entry points, including cursor reads and cleanup, are
serialized with a reentrant lock. This prevents SQLite mutex/Python-authorizer
lock inversion across API and scan worker threads while keeping write protection.

Scan logs include a safe `X-Scan-Trace` correlation ID, upload byte count,
response status and stage timings. No request bodies, images, OCR text or
credentials are included. On Linux, `SIGUSR1` dumps thread stacks (not locals)
to API stderr for diagnosing a stall before restarting the service.

Restart the API to load a newly published snapshot, after explicitly updating
`PLANETSCALE_IMPORT_ID` if appropriate. This is a pinned snapshot cache, not a
live per-request database lookup. A cloud/model/checksum failure prevents startup;
there is no silent fallback to local catalogue data. Health exposes
`catalogue_backend` and `catalogue_import_id` for deployment verification.

Sessions, scan results, captures, helper credentials/jobs, scraper budgets, and
new price samples remain local operational data. Original image/model binaries
remain on the existing volume. Catalogue/mapping writes are blocked with a clear
409 response; already-linked listing/finish choices still work and are saved to
the scan without editing the cloud catalogue.

Rollback: preserve the previous API image and use `CATALOGUE_BACKEND=sqlite` in
Dokploy's environment, then redeploy the API. Existing local catalogue/vector
files are retained. No cloud schema changes or deletions are needed.
# Variant history deployment and catalogue correction — 2026-10-01

Approved changes `STAGING-VARIANTS-004` and `PS-FUECOCO-005`:

- Session history now includes the existing `chosen_cardmarket_url` column;
  no operational schema migration was needed. Flutter confirmation passes the
  chosen listing and history/portfolio preserve it.
- Corrected the English `en:sv01-036` URL and its helper in
  `pokesingle/pokesingle-db/main`, schema `pokesingle_import_20261001`, from
  Chinese promo `Fuecoco-V2-SV-PCS036` to English `Fuecoco-V1-SVI036`.
  The guarded MCP transaction recomputed the validated cards digest and
  recorded the old/new values in the manifest's `corrections` array.
  Digests: `f95b291e50ac3e28be12eec0fd4bd01d` →
  `9b9ae1b795960b24cc6a96bc6179ff42`. No vectors or IDs were deleted.
- The API alone was rebuilt/recreated using the existing Dokploy-generated
  compose file. Startup checksum verification passed with 48,652 cards and
  37,755 indexed pad references. Runtime PlanetScale access remains read-only.
- 204 API tests passed. Simulator UI confirmation/history/portfolio tests
  passed for both downloaded Fuecoco V1/V2 photos. Thresholds are unchanged.

API rollback image: `scanapp-staging-rollback:staging-variants-004`;
original runtime files/compose archive:
`/etc/scanapp-staging/rollback-staging-variants-004/code-before.tar.gz`.
The SQL correction and rollback are also archived with mode 0600 in that
same remote rollback directory. Runtime file checksums match the tested local
files. Source edits remain local/unpushed; a future Git-based deploy must
include these edits or it will revert the history-response improvement.
The separate guarded SQL correction/rollback files are preserved locally in
`/tmp/pokesingle-planetscale-import.RTbfND/fuecoco-correction.sql` and
`fuecoco-rollback.sql`. Database rollback requires explicit operator direction;
restoring the old API does not require reverting the corrected catalogue URL.
