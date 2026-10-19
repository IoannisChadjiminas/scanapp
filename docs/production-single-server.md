# ScanApp and PokeSingle API on one production server

Use one production host with two Dokploy Compose services: ScanApp and the
PokeSingle API. Routine checks use dedicated production test accounts. Develop
experimental matching changes locally; a shared production scanner deploy affects
every user. Keep public API hostnames distinct from any currently used staging
routes until their cutover has been verified.

## Prepared source

- ScanApp: select `compose.dokploy.production.yaml` only. It has production host
  paths, its own Compose-scoped persistent volumes, and no hardcoded Traefik domain.
  Add an HTTPS domain to service `web`, port `80`, in Dokploy. Suggested unused
  hostname for the first rollout: `scan-prod.pokesingle.com`.
- PokeSingle API: keep its own `compose.dokploy.production.yaml` service. Set
  `SCAN_API_BASE_URL=https://scan-prod.pokesingle.com/api/v1/`, including the final
  slash, after the new scanner route is healthy.
- Set the same fresh `SCANAPP_SERVICE_TOKEN` in both services. This private token
  authenticates `POST /api/v1/internal/portfolio/products`; no mobile client gets it.
  An absent token disables this route. A configured token shorter than 32 characters
  is rejected. Browser sessions and review credentials cannot authorize it.
- The internal route accepts `owner_key=user:<permanent-account-id>` and a complete
  list of Cardmarket Singles `url`/timezone-aware `opened_at` values. It opens an
  independent database connection and serializes replacements per owner. Repeating
  the same snapshot is safe; an empty list removes that owner's registrations.
  Browser session portfolios are outside the `user:` namespace.

## Host capacity

Inspect the actual server's RAM, swap, free disk, and current service usage before
building. The scanner's current Compose allowance is 3 GiB RAM plus up to 1 GiB
swap; the PokeSingle API allowance is 768 MiB. Dokploy, Docker, Caddy and the OS
need additional memory. A 2 GiB host cannot accommodate these limits safely.
For consolidation, budget 8 GiB RAM, especially if enabling the optional scraper
(another 1.5 GiB allowance). These are planning figures, not a measured load test.
Any resize and resulting billing change require the operator's decision.

Read-only host check on 19 October 2026: 1909 MiB RAM, no swap, about 29 GiB free
disk, and Dokploy itself using approximately 863 MiB. The scanner and product API
were not running on this host at that check. This host is not ready for the two
additional production services at its current size.

The default rollout creates no scraper process and disables background paid price
reads and price-guide import jobs. Enable them after their credentials, quotas and
database permissions have been verified. One recognition worker serializes scans;
the queue is bounded at two waiting requests by default. Run smoke tests when the
queue is quiet so testing does not consume the serving capacity.

## Databases and private files

1. Catalogue: use a dedicated **read-only** production role on the curated catalogue
   database `pokesingle-db/main`. A shared immutable public-card snapshot can serve
   both environments; no user holdings, results, or captures go in this connection.
   Existing validation requires read-only access and verified TLS. Put its
   `PLANETSCALE_DATABASE_URL` in root-owned mode-0600
   `/etc/scanapp-production/planetscale.env`.
2. Catalogue release: put the reviewed `PLANETSCALE_SCHEMA`, `PLANETSCALE_IMPORT_ID`
   and any required `ARTWORK_BUNDLE_DIR` / `REFERENCE_FEATURES_DIR` selectors in
   `/etc/scanapp-production/catalogue-release.env`. Do not rely on the code's old
   default import. Both files are required for Compose to validate.
3. Portfolio: issue a **separate ScanApp credential** on `pokesingle-product-prod/main`.
   Set `PORTFOLIO_DATABASE_URL` in ScanApp's Dokploy environment. Do not reuse the
   API's runtime or migration role. Provision/review the scanner-owned
   `portfolio_products` table and optional price-history tables before launch;
   these are separate from the API's Drizzle migration ledger. The prepared
   `docs/sql/scanapp-production.sql` creates the scanner tables/indexes and grants
   a pre-existing dedicated role access only to them. Review and apply it as a
   schema administrator against the named production DB, using a private libpq
   service definition rather than putting a connection URL into shell arguments:
   `PGSERVICE=scanapp-production-admin psql -v ON_ERROR_STOP=1 -v scanapp_role=<role-name> -f docs/sql/scanapp-production.sql`.
   The connector skips DDL when those objects exist, so the runtime role needs no
   CREATE or auth/user table access. Missing objects require administrator
   provisioning; do not solve that by granting broad privileges. Verify the role
   before deployment. The prepared schema includes the last-sync timestamp.
4. Copy `.env.production.example` to the ignored `.env-prod` for scanner service
   settings. The corresponding API `.env-prod` belongs to its own service.
   Keep both local files mode 0600. The scanner env must not contain Firebase Admin,
   OAuth, Better Auth, email or analytics secrets from the product API.

The new shared service token is prepared in both local `.env-prod` files. The
production portfolio URL is deliberately left for a dedicated scoped credential.

From the ScanApp checkout, check local configuration without displaying secrets
or contacting any database:

```sh
.venv/bin/python scripts/check-production.py --api-env-file ../pokesingle-api/.env-prod
```

On the production host, add `--host-files` after provisioning the catalogue files.
This check verifies configuration shape only; it cannot prove that a supplied role
has the right grants or that a hostname routes to the new production service.

## Recognition artifacts and storage

Create the production data volume independently. Seed the reviewed ONNX model
files under `/data/models` and the exact catalogue-bound artwork/reference bundles
selected by the release file. Use a reviewed catalogue export or an explicit
artifact allowlist. Do not copy the entire staging `/data` volume: it contains
sessions, user portfolios, scan results, review photos, helper credentials, queues
and budgets. Verify model and catalogue checksums on the destination.

Do not run the existing `offload-to-staging.sh` for production. The legacy
`offload-apply.sh` auto-discovers a ScanApp container and restarts it; it is unsafe
for a host with multiple deployments unless an exact target is supplied and the
bundle has been reviewed. Provision production artifacts before the first healthy
start; the runtime does not download a complete model set on demand.

User photos continue through the product API's private production R2 bucket.
`STORE_CAPTURES=false` prevents the scanner's optional on-disk review JPEG archive;
normal session/result metadata still uses the dedicated production volume. Review
and helper access remain separately configured. Protect and back up the operational
volume; never expose its database/files through the web service.

## Deployment and verification order

1. Record the current staging release, artifact manifest, volumes and backups.
   Measure host capacity and resolve the server resize before production builds.
2. Review and publish the prepared ScanApp branch. Authorize Dokploy to read the
   ScanApp repository (the existing GitHub App was limited to `pokesingle-api`).
3. Provision the production DB roles/schema, release files and model/reference
   artifacts. Create the ScanApp production Compose service, paste its own env,
   attach DNS/HTTPS for `web:80`, and deploy with one API worker.
4. Check `/api/v1/health`: catalogue backend/import and model readiness must match
   the reviewed release. Test scan/search with non-private test images.
5. Verify the internal route rejects no/wrong bearer credentials; register a
   dedicated test owner, retry its snapshot, then send an empty snapshot and verify
   removal. Confirm other owners and browser sessions remain unchanged. Verify
   the real production portfolio database uses a dedicated ScanApp role.
6. Update the product API's `SCAN_API_BASE_URL` to the new HTTPS base and the same
   service token, then deploy/restart it. Test member sync, account-cleanup jobs,
   price batch and opportunity lookups with dedicated test accounts. Observe job
   retries and the scanner queue; an HTTP health response alone does not prove the
   database writes or account cleanup work.
7. Build the mobile production profile against the verified API/scanner URLs and
   production Firebase providers. Keep production telemetry and notification
   scheduling gated until their separate delivery checks pass.
8. After both services and backups are verified, stop the old staging workloads.
   Server deletion/cancellation is a separate explicit action; do not delete a
   server while it contains the only copy of any catalogue artifact or user data.

No server resize, DNS cutover, live DB change, paid scraping or production
deployment is performed by preparing these files.

## Local verification

The service endpoint tests cover denied credentials, disabled configuration,
malformed input, independent owners, browser-session isolation, idempotent cleanup
and rollback. Optional real PostgreSQL tests also exercise the transaction lock,
failed replacements, and a runtime role without schema CREATE or auth-table access.
They accept only `SCANAPP_TEST_DATABASE_URL` pointing at a disposable loopback
database whose name ends in `_test`; they never load production credentials.
Run them with the API pytest configuration, for example:

```sh
.venv/bin/python -m pytest -c api/pytest.ini api/tests/test_internal_portfolio.py api/tests/test_internal_portfolio_postgres.py
```

The PostgreSQL cases skip when that explicit test-only URL is absent. Running
these tests against a live hosted database is refused.

Preparation results on 19 October 2026: 118 relevant tests passed, including the
real PostgreSQL cases. The prepared schema applied twice successfully in a local
disposable database, and its wrong-database guard refused the test DB. Both the
scanner API and static web Docker images built successfully for Linux amd64.
Compose validation passed with only API/web selected by default. None of these
checks proves production catalogue readiness or live delivery.

The web dependency audit also reports existing findings (10 excluding dev-only
dependencies, including a critical Next.js advisory). The final web image contains
Caddy and exported static files; it contains no Node/Next server or node_modules.
No dependency upgrades are bundled into this deployment change. Review/update
local development and build-tool dependencies separately, especially before
introducing any hosted Next.js server or dynamic rendering.
