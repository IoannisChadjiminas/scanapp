# Staging catalogue source

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
