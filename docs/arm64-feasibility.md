# Arm64 feasibility test for the recognition API

Goal: find out whether the scanner gives the same answers on a Hetzner **CAX21**
(Arm Ampere, 4 vCPU / 8 GB, €12.48/month) as on x86, so production could later move
off the **CPX32** (x86, €42.23/month). Answers are the measure. Cost and latency
only matter once answers are known to hold.

This runbook uses a **disposable** server that you create and delete yourself in the
Hetzner console. Nothing here buys, resizes or deletes a server, deploys anything, or
changes production or staging. The test box gets public card data only, never a
database credential.

## What has been checked already (2026-10-19, on an M4 Pro Mac)

- **Images.** `docker/api.Dockerfile` and `docker/web.Dockerfile` build for
  `linux/arm64`, for `linux/amd64`, and for both in one multi-platform build. Every
  pinned API dependency installs from a prebuilt `manylinux` aarch64 wheel, with no
  source builds: onnxruntime 1.22.1, opencv-python(-headless) 4.11.0.86, numpy
  2.2.6, pillow 11.3.0, pillow-heif 1.1.0, rapidocr 3.4.0, psycopg-binary 3.3.6,
  shapely, pyclipper, pydantic-core, uvloop and the rest. `pip check` is clean. The
  build's own import check passes. In the arm64 image, SIFT runs and onnxruntime
  offers `CPUExecutionProvider`. OpenCV reports NEON baseline with DOTPROD, FP16
  and BF16 dispatch. Both architectures have identical library versions.
- **Only Dockerfile change:** the web image's Node build stage now runs on the
  builder's own platform (`FROM --platform=$BUILDPLATFORM`). Its output is static
  files, so a cross-build emulates only the Caddy stage. The API Dockerfile needed
  no change.
- **Scraper image stays x86-only.** `docker/scraper.Dockerfile` installs
  `google-chrome-stable` from Google's apt repository, which publishes amd64
  packages only (`arch=amd64` in the source line). It cannot build for arm64. The
  default production rollout runs no scraper. If you need one later, it runs on its
  own x86 host (`compose.scraper-host.yaml`, `docs/scraper-host.md`).
- **Reference-features rebuild** (`api/scripts/build_reference_features.py`) was
  tested on a 775-card subset of a real catalogue copy (96 cards with images), in
  the arm64 image and in the amd64 image under emulation. See the next section.

Not checked: anything on real Ampere hardware, the full 50,270-card catalogue, or
recognition answers on Arm. Those are what this runbook measures.

## Why the reference-features bundle is pinned to one architecture

The bundle (`REFERENCE_FEATURES_DIR`, `api/app/recognition/reference_features.py`)
holds precomputed SIFT keypoints, descriptors and printing thumbnails for every
catalogue image. Scans use it instead of decoding about 50,000 reference images
live. The bundle is only valid if it gives exactly what live extraction would give
on the serving host. So its `processing` contract records `architecture`
(`platform.machine()`) and `opencv_build_sha256` (a hash of
`cv2.getBuildInformation()`), along with the library versions and extraction
settings. `ReferenceFeatureStore.load` refuses any bundle whose contract differs
from the running host's. The API then reports not ready, and never silently falls
back to reading images.

That strictness is justified. The same pinned wheels on x86 and Arm compile to
different SIMD code (SSE/AVX against NEON, with fused multiply-add on aarch64). On
the 96-card subset, the arm64 and emulated-amd64 bundles were bitwise identical
for only 38 cards:

- Printing thumbnails differed on 57 cards, by at most 3.7e-8 (values up to about
  0.04, so roughly one float32 rounding step).
- SIFT keypoints were identical everywhere. On 11 card/profile pairs, exactly one
  descriptor row differed, by 1 on the 0-255 scale.

These differences are tiny, but they are real. So an Arm host needs its own native
build. A relabelled x86 bundle would break the "features equal live extraction"
guarantee.

The emulated amd64 run may not match a real x86 server exactly (CPU dispatch under
emulation can differ). It shows that the bundle is not portable, not the exact
amount of drift.

### The rebuild script

`api/scripts/build_reference_features.py` is the existing offline builder. It now
has optional strict checks for an architecture rebuild. Run with none of them, it
behaves exactly as before.

| Flag | Effect |
|---|---|
| `--expect-architecture aarch64` | Refuses, before building, unless `platform.machine()` is `aarch64` |
| `--expect-import-id PS-CATALOGUE-EN-JA-ENID2-20261019` | Refuses unless the exported catalogue (`vectors/*/manifest.json` → `exported_from.import_id`) came from that import |
| `--expect-cards 50270` | Refuses unless the catalogue has exactly that many cards |
| `--compare-manifest x86/manifest.json` | After building, compares with staging's x86 manifest. Only `architecture` and `opencv_build_sha256` may differ. Library versions, extraction settings, catalogue signature, card coverage, image mapping, art boxes, availability and source-image checksums must all match. |
| `--native-check 200` | Re-extracts 200 evenly spaced cards live and requires bitwise-equal features |
| `--mirror-unavailable display_only_no_vectors` | With `--compare-manifest`: marks unavailable exactly the cards the x86 manifest marks unavailable for that reason. That reason is a release curation step outside the builder (staging's `20261017-ja-sets` lists 10 such cards: `en:mfb-*` and `en:svp-500`). Without the flag, the comparison rightly refuses the bundle. |
| `--existing` | Re-checks an already built bundle in `--output` (restore `manifest.rejected.json` to `manifest.json` first) instead of rebuilding |
| `--limit N` | Smoke test only. Builds N evenly spaced cards. The bundle is bound to that subset, and the API rejects it for the full catalogue. |

If a comparison or native check fails, the script renames `manifest.json` to
`manifest.rejected.json`, so no loader can activate the bundle, and exits non-zero.
After every build it validates the bundle with the API's own
`ReferenceFeatureStore.load`. The bundle declares the host's own `aarch64` contract
and OpenCV hash. Nothing in validation is bypassed or relaxed. Tests:
`api/tests/test_build_reference_features_script.py` (they pass in the arm64 image,
with `api/tests/test_reference_features.py`).

## Two important limits of the comparison

1. **The test box runs the catalogue from a local export, not from PlanetScale.**
   That keeps credentials off the box. But in local (`sqlite`) mode the API does
   not load the visual image aliases that the cloud loader applies, and it builds
   listing groups differently. Arm results against the staging baseline therefore
   mix two effects: the architecture and the local-backend path. To separate them,
   run the same runbook on a disposable **x86 control** box as well (step 10). It
   costs a few cents for an hour or two. Without it, a non-zero difference against
   staging cannot be blamed on Arm.
2. **The pipeline is not fully deterministic.** Parallel OCR regions and the
   grading deadline depend on timing. Run each configuration twice. A difference
   only counts if it is larger than the run-to-run difference.

## What goes to the test box, and what never does

| Item | Source | Contents |
|---|---|---|
| arm64 API image | built from this branch | code and dependencies, no data |
| `catalog.sqlite`, `vectors/pad/*` | `api/scripts/export_cloud_snapshot.py` output | public card data and embeddings |
| `reference-images/` | staging `/data/reference-images` | public card artwork |
| `models/*.onnx` | staging `/data/models` | DINOv2 and PP-OCRv6 models |
| artwork bundle | staging `ARTWORK_BUNDLE_DIR` | artwork embeddings |
| x86 features `manifest.json` (manifest only) | staging `REFERENCE_FEATURES_DIR` | card IDs, image paths, checksums |
| `staging-recognition.env` | `api/scripts/recognition_settings.py` on staging | recognition flags and thresholds only |
| photo panel | `api/scripts/pack_replay_panel.py` | 150 frozen listing photos (+5 optional phone captures) |

**Never** copy: `/etc/scanapp-staging/planetscale.env`, any `.env`/`.env-prod`, the
container environment (`docker inspect … Env`, `docker exec … env`), `results.sqlite`,
sessions, `/data/review`, captures, portfolios, helper credentials, or the whole `/data`
volume. The box needs no database connection.

## Steps

Placeholders: `STAGING` is your SSH alias for the staging host, `BOX` is the test box's
IPv4 address, `KIT=~/scanapp-arm-kit` is a folder on your Mac. Run Mac commands from this
repository checkout.

### 1. Gather the kit on your Mac (read-only on staging)

```bash
mkdir -p ~/scanapp-arm-kit/data ~/scanapp-arm-kit/results
```

**a. Catalogue export.** The 2026-10-19 experiment left one on staging in `/root/bench`.
Reuse it only if `vectors/pad/manifest.json` → `exported_from.import_id` is
`PS-CATALOGUE-EN-JA-ENID2-20261019`. Otherwise export again on staging. The script loads
the catalogue with the API's own verifying loader. `/data` is a fresh scratch folder, so
nothing is written to the staging volume. Staging's models and images are mounted
read-only. The credential comes only from the existing env file and is never printed.
First find the API container's image and data volume. These commands print the image
name and mounts, not the environment:

```bash
ssh STAGING "docker inspect <staging-api-container> --format '{{.Config.Image}}{{println}}{{range .Mounts}}{{.Destination}} {{.Source}}{{println}}{{end}}'"
```

```bash
ssh STAGING mkdir -p /root/arm-export/scratch /root/arm-export/out && scp api/scripts/export_cloud_snapshot.py STAGING:/root/arm-export/
```

Set `VOL` to the source path of `/data`, both on staging and in your Mac shell (the
rsync commands below use it). Then, on staging:

```bash
docker run --rm --env-file /etc/scanapp-staging/planetscale.env --env-file /etc/scanapp-staging/catalogue-release.env -e CATALOGUE_BACKEND=planetscale -e DATA_DIR=/data -v /root/arm-export/scratch:/data -v "$VOL/models:/data/models:ro" -v "$VOL/reference-images:/data/reference-images:ro" -v /root/arm-export/export_cloud_snapshot.py:/app/scripts/export_cloud_snapshot.py:ro -v /root/arm-export/out:/out <staging-api-image> python /app/scripts/export_cloud_snapshot.py --out /out
```

It prints card counts and checksums only. Expect `cards` 50270 and `import_id`
`PS-CATALOGUE-EN-JA-ENID2-20261019`. Then delete `/root/arm-export/scratch` (it holds an
empty results database).

**b. Copy the public data down.** `ARTWORK_BUNDLE_DIR` and `REFERENCE_FEATURES_DIR` are
the selectors in `/etc/scanapp-staging/catalogue-release.env`. Read just those two lines
with `grep -E '^(ARTWORK_BUNDLE_DIR|REFERENCE_FEATURES_DIR)=' …`. Check sizes first with
`du -sh`. The reference images are several GB.

```bash
rsync -a STAGING:/root/arm-export/out/ ~/scanapp-arm-kit/data/
```

```bash
rsync -a STAGING:"$VOL/reference-images/" ~/scanapp-arm-kit/data/reference-images/
```

```bash
rsync -a --include='*.onnx' --exclude='*' STAGING:"$VOL/models/" ~/scanapp-arm-kit/data/models/
```

For the artwork bundle, keep its path relative to `/data`. For example,
`/data/artwork/PS-CATALOGUE-EN-JA-SETH3-20261017` goes to
`~/scanapp-arm-kit/data/artwork/PS-CATALOGUE-EN-JA-SETH3-20261017`. For the x86
features, copy `manifest.json` only (to `~/scanapp-arm-kit/x86-features-manifest.json`).
Map each `/data/...` path to `$VOL/...` on the host.

**c. Recognition settings.** This prints only flags, thresholds, version strings and
bundle folder names, never URLs, tokens or keys. It reads the API's `Settings`, not the
environment:

```bash
ssh STAGING "docker exec -i <staging-api-container> python -" < api/scripts/recognition_settings.py > ~/scanapp-arm-kit/staging-recognition.env
```

Look at the file before you use it. It must contain only `KEY=value` lines for
recognition settings.

**d. Photo panel and baseline.** These 150 listing photos are in this repository's
`datasets/review`. Each photo is checked against its recorded sha256.

```bash
.venv/bin/python api/scripts/pack_replay_panel.py --cases data/latency/staging-reference027-20261003/regression-cached.jsonl --repo-root . --out ~/scanapp-arm-kit/panel
```

```bash
cp data/latency/ocr-grading-cpu-20261019-raw/baseline.jsonl ~/scanapp-arm-kit/results/staging-x86-baseline.jsonl
```

The five `phone_capture`/`reported_phone` cases are real user captures. They exist only
on staging and are not needed. The comparison runs on the photos both runs share. To
include them, copy them from the bench folder on staging into a local folder and add
`--search <that folder>`. Keep them on the box only, and delete them with it.

**e. Image and scripts.** Build the arm64 API image from this branch and save it:

```bash
docker buildx build --platform linux/arm64 -f docker/api.Dockerfile -t scanapp-api:arm64-$(git rev-parse --short HEAD) --load .
```

```bash
docker save scanapp-api:arm64-$(git rev-parse --short HEAD) | gzip > ~/scanapp-arm-kit/scanapp-api-arm64.tar.gz
```

```bash
cp -R api/scripts ~/scanapp-arm-kit/scripts
```

### 2. Create the box (you, in the Hetzner console)

- Type **CAX21** (Arm64, 4 vCPU, 8 GB, 80 GB disk), image **Ubuntu 24.04**, any EU
  location that offers CAX, your SSH key, no backups or volumes. Name it
  `scanapp-arm-test`.
- Firewall: allow inbound TCP 22 from your own IP only. The API is never exposed;
  all traffic stays inside the box.
- Billing is hourly while the server exists, even when powered off. Delete it when
  you are done (step 11).

### 3. Install Docker on the box

```bash
ssh root@BOX
```

```bash
apt-get update && apt-get install -y ca-certificates curl rsync && install -m 0755 -d /etc/apt/keyrings && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list && apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
```

```bash
uname -m && docker info --format '{{.Architecture}} cgroup v{{.CgroupVersion}}'
```

Expect `aarch64` and cgroup v2. `cpu_replay.py` reads `cpu.stat` and `memory.peak` from
cgroup v2.

### 4. Copy the kit up and load the image

From the Mac:

```bash
rsync -a --info=progress2 ~/scanapp-arm-kit/ root@BOX:/srv/scanapp-arm/
```

On the box:

```bash
gunzip -c /srv/scanapp-arm/scanapp-api-arm64.tar.gz | docker load && docker images scanapp-api
```

To build on the box instead, copy a `git archive` tarball of this branch (never a
checkout holding `.env` files) and run the same `docker buildx build` there.

### 5. Rebuild reference features natively on the box

Set `IMG` to the loaded tag. Run a smoke build first. It is disposable and fails fast if
any path or image is wrong:

```bash
IMG=scanapp-api:arm64-<sha>; docker run --rm --network none -v /srv/scanapp-arm/data:/data -v /srv/scanapp-arm:/kit:ro "$IMG" python /kit/scripts/build_reference_features.py --data-dir /data --output /data/reference-features/smoke-aarch64 --workers 4 --expect-architecture aarch64 --expect-import-id PS-CATALOGUE-EN-JA-ENID2-20261019 --expect-cards 50270 --limit 500 --compare-manifest /kit/x86-features-manifest.json --native-check 50
```

Then the full build. The estimate is about 30-60 minutes, scaled from the Mac subset and
not measured on Ampere. Run it inside `tmux` or with `nohup`:

```bash
docker run --rm --network none -v /srv/scanapp-arm/data:/data -v /srv/scanapp-arm:/kit:ro "$IMG" python /kit/scripts/build_reference_features.py --data-dir /data --output /data/reference-features/PS-CATALOGUE-EN-JA-ENID2-20261019-aarch64 --workers 4 --expect-architecture aarch64 --expect-import-id PS-CATALOGUE-EN-JA-ENID2-20261019 --expect-cards 50270 --compare-manifest /kit/x86-features-manifest.json --mirror-unavailable display_only_no_vectors --native-check 200 | tee /srv/scanapp-arm/results/features-build.log
```

The last line is a JSON summary. Check it for `"validated": true`,
`"architecture": "aarch64"`, `compared.problems: []` with
`changed_processing_fields: ["architecture", "opencv_build_sha256"]`, and
`native_check.deltas: []`. Also record `cpu_seconds`, `build_seconds` and
`peak_rss_mb`. On failure there is no `manifest.json`; read the `problems` list.
`/data` is mounted read-write because the API later switches `catalog.sqlite` to WAL
mode. The builder itself opens the catalogue read-only.

### 6. Prepare the box's recognition settings

Start from staging's settings. Swap in the local backend and the Arm features, and turn
off every background job that would burn CPU during the replay:

```bash
cd /srv/scanapp-arm && grep -vE '^(CATALOGUE_BACKEND|REFERENCE_FEATURES_DIR|ARTWORK_BUNDLE_DIR)=' staging-recognition.env > box.env && cat >> box.env <<'EOF'
DATA_DIR=/data
TMP_DIR=/tmp/scanapp
CATALOGUE_BACKEND=sqlite
REFERENCE_FEATURES_DIR=/data/reference-features/PS-CATALOGUE-EN-JA-ENID2-20261019-aarch64
ARTWORK_BUNDLE_DIR=/data/<same path below /data as on staging>
STORE_CAPTURES=false
SCRAPER_ENABLED=false
DAILY_PRICES_ENABLED=false
PRICE_GUIDE_ENABLED=false
TCGDEX_PRICES_ENABLED=false
CARDMARKET_HELPER_ENABLED=false
SCAN_PRICE_SERVER_READ=off
OMP_NUM_THREADS=1
EOF
```

### 7. Start the API and check it

`--cpus 2` matches the staging baseline (2 vCPU, `--cpus 2`). On a box with more cores
than the target, `--cpuset-cpus 0-1` (or `0-3` for a CAX21) is closer to a real small
host; on 2026-10-19 both gave the same CPU per scan. The memory limit matches
the staging compose file.

```bash
docker run -d --name scanapp-arm-api --cpus 2 --memory 3072m --memory-swap 4096m --env-file /srv/scanapp-arm/box.env -v /srv/scanapp-arm/data:/data -v /srv/scanapp-arm:/kit:ro -v /srv/scanapp-arm/results:/results "$IMG"
```

```bash
sleep 60; docker exec scanapp-arm-api python -c "import urllib.request,json; h=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')); print(h['status'], h['ready'], h['catalogue_version'], h['detail'])"
```

Expect `ok True`. If it says not ready, `detail` names the artifact that was refused,
for example a reference-feature contract mismatch. Then confirm that recognition
settings equal staging's, apart from the keys changed on purpose:

```bash
docker exec -i scanapp-arm-api python - --check /kit/staging-recognition.env --ignore CATALOGUE_BACKEND --ignore REFERENCE_FEATURES_DIR < /srv/scanapp-arm/scripts/recognition_settings.py
```

It must print `0 differing recognition settings`.

### 8. Replay the panel (twice)

This mirrors the staging baseline: no `graded` hint, one scan at a time, CPU from the
container cgroup until it has been idle for 1.2 s. Each run takes roughly 15-30 minutes.

```bash
docker exec scanapp-arm-api python /kit/scripts/cpu_replay.py --panel /kit/panel/panel.json --root /kit/panel --out /results/arm64-run1.jsonl
```

```bash
docker restart scanapp-arm-api && sleep 60 && docker exec scanapp-arm-api python /kit/scripts/cpu_replay.py --panel /kit/panel/panel.json --root /kit/panel --out /results/arm64-run2.jsonl
```

Optional: production would have 4 vCPU. Repeat once with `--cpus 4` to see latency at
that size (CPU-seconds per scan should barely change).

Each row also records `rss_mb`, `peak_rss_mb` (the API process's VmHWM) and
`cgroup_peak_mb` (the container's `memory.peak`, which includes page cache).

### 9. Compare (on the Mac)

```bash
rsync -a root@BOX:/srv/scanapp-arm/results/ ~/scanapp-arm-kit/results/
```

```bash
.venv/bin/python api/scripts/compare_replay.py ~/scanapp-arm-kit/results/staging-x86-baseline.jsonl ~/scanapp-arm-kit/results/arm64-run1.jsonl ~/scanapp-arm-kit/results/arm64-run2.jsonl > ~/scanapp-arm-kit/results/arm64-vs-staging.json
```

```bash
.venv/bin/python api/scripts/compare_replay.py ~/scanapp-arm-kit/results/arm64-run1.jsonl ~/scanapp-arm-kit/results/arm64-run2.jsonl > ~/scanapp-arm-kit/results/arm64-repeat.json
```

Per variant, the output has: `answer_changes` and `answer_changed_ids` (card_id or
status changed), `changes[].fields` (before and after values), `regressions` and `fixes`
against the expected card, `correct`, `cpu_ms_mean/p50/p90`, `http_ms_p50/p90`,
`peak_rss_mb`, `cgroup_peak_mb`, and `baseline_on_same_photos` (the baseline restricted
to the photos both runs share).

### 10. x86 control (strongly recommended)

Create a second disposable box, an x86 **CPX** type, delete it afterwards, and repeat
steps 3-9 there with an amd64 image (`--platform linux/amd64`) and
`--expect-architecture x86_64`. It gets the same export, the same local backend and the
same replay. Then compare Arm against this control
(`compare_replay.py x86-control-run1.jsonl arm64-run1.jsonl …`). This isolates the
architecture effect; the control against staging shows the local-backend effect.

### 11. Tear down

Copy `results/` off the box, then **delete the server** in the Hetzner console. Powering
it off does not stop billing. The box holds no credentials. If you copied the five
phone captures, they go with it. On staging, `/root/arm-export` can be removed.

## How to read the result

The decision rests on **card_id and status changes**, not CPU.

- **Arm looks safe** if, against the x86 control, Arm changes no more answers than the
  control changes against itself between repeats, and loses no expected card.
- **Not safe yet** if Arm consistently changes answers (the same photo IDs in both
  runs), especially if `regressions` is non-empty. Look at each photo in
  `changes[].fields`. Differences only in OCR text or printing evidence, with the
  same card and status, do not count as answer changes.
- **Without the x86 control,** a difference against the staging baseline is an upper
  bound on the Arm effect, not a measurement of it.

One known setup effect inflates CPU on the box: in local mode every scan rebuilds the
Cardmarket listing groups (`cardmarket_ms` of about 3 s, against 5 ms with the cloud
catalogue; see `Runtime.listing_groups`). Subtract it before comparing CPU.

Then compare cost. Use CPU-seconds per scan (the mean and the p90) to see how many
scans per hour the 4 vCPU box sustains. Use p50/p90 latency at `--cpus 2` against the
staging baseline (12.2 s mean CPU, p50 HTTP 5.2 s, p90 9.7 s on 2026-10-19). Peak RSS
must fit the 3 GiB limit.

## Handing the box to Claude (optional)

If you want Claude to run steps 4-9, add a temporary SSH key to the box and say its name
or address. Claude will then only use that box. It will load the image, rebuild
features, run the replays, and report:

- Answer changes against the x86 staging baseline (photo IDs with card_id and status
  before and after).
- CPU-seconds per scan.
- p50/p90 latency.
- Peak RSS.

It will not touch staging, production or the Hetzner account. It will not print
environment or credential files. Server creation and deletion stay with you.
