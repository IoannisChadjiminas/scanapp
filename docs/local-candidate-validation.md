# Validating a catalogue candidate on the Mac

The staging host has 4 GiB of RAM and the live API already uses up to 2 GiB.
A second runtime for a candidate (the scan panel worker or the feature probe)
does not fit next to it, which is why the ENFIVE panel stopped at 1/5. These
checks now run on the Mac, against the same API image and settings staging
uses. Staging only receives the files once and the final switch.

## What stays identical to staging

- Image: `docker/api.Dockerfile`, built for `linux/amd64`. Reference-feature
  bundles record the CPU architecture and OpenCV build, so an arm64 build
  would reject the staging bundle.
- Settings: `docker compose -f compose.dokploy.yaml config` resolves every flag
  and default, and the API keeps the staging `mem_limit` (2 GiB) and swap.
  If staging's Dokploy `.env` overrides any flag, pass a copy of those
  non-secret values with `--compose-env`.
- Catalogue: the same PlanetScale schema and import, read with the read-only
  role and the same checksum checks as `load_cloud_catalogue`.

Local differences: prices, the scraper and the portfolio database are off;
the panel and probe run in a separate container with their own 4 GiB; timings
run under emulation and are not staging latency.

## Steps

Prepare once: a local copy of staging `/data` (models, reference images,
vectors, feature bundles) in `--data-dir`, the candidate and parent
`catalogue-release.env` files, and the read-only PlanetScale credentials.

```sh
python3 scripts/local_candidate.py up enfive \
  --release-env releases/enfive.env --planetscale-env ~/keys/ps-readonly.env \
  --data-dir data/staging-data
python3 scripts/local_candidate.py panel enfive --panel panel.json --photos-root photos
python3 scripts/local_candidate.py probe enfive --audit-dir audit/enfive
python3 scripts/local_candidate.py rollback enfive --parent-env releases/nativeprimary6.env
python3 scripts/local_candidate.py status enfive
python3 scripts/local_candidate.py down enfive
```

- `up` fails fast if the API runs out of memory while loading, reports a load
  error, or serves a different import than the release file names.
- `panel` resumes from the last finished scan, records the API's peak memory
  against the staging limit, and fails if the API was killed for memory.
- `probe` runs `staging_reference_feature_probe.py` (images versus features,
  grading equality, no reference-image reads) in its own container.
- `rollback` loads the parent release on the next port and confirms its import.

Results go to `.local-candidate/<name>/gates.json`, keyed by the release file,
feature manifest, API code and inputs. Running a passed check again with the
same key is skipped; `--force` repeats it. Change any input and the check runs.

## What still happens on staging

After the local gates pass and Ioannis approves activation: copy the files,
switch `catalogue-release.env`, recreate only the API, then one health read of
the served import and a short panel against the live API (one runtime, no
second worker). Rollback on staging is the archived release file plus an API
recreate, confirmed by the same health read.
