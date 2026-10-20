#!/usr/bin/env bash
# Replay the frozen 155-photo panel on staging: baseline vs CLIENT_TEXT_OCR=footer.
#
#   scripts/staging-client-text-replay.sh            # plan only: prints what it would do, touches nothing
#   scripts/staging-client-text-replay.sh --run      # does it (stops the live staging API meanwhile)
#
# What it does with --run, on $HOST (default auctaro-staging):
#   1. Copies this branch's api/app and api/scripts, the panel, and the simulated phone hints to
#      $BENCH (a new directory). Records the live API container's id, image and state.
#   2. Stops ONLY the live ScanApp API container (web, scraper and every other service on the host
#      keep running; staging scans fail with 502 until step 5). A trap restarts it on any exit.
#   3. Runs a throwaway container `bench-api` from the live API's own image and environment, with
#      this branch's code mounted read-only, the live data volume mounted READ-ONLY at /data, and a
#      fresh data directory (symlinks to the live files, its own results.sqlite). 2 CPUs, no
#      captures, scrapers and price jobs off, not attached to the compose network.
#   4. Runs base, footer, base, footer (alternating, one container start per run), each the whole
#      panel with the oracle graded hint and the phone text, measuring CPU from the cgroup.
#   5. Removes bench-api, restarts the live API container, checks health, deletes the copied
#      panel photos and environment file, and copies the results back to $LOCAL_OUT.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${STAGING_SSH:-auctaro-staging}"
DOCKER="${STAGING_DOCKER:-docker}"
BENCH="${BENCH_DIR:-/root/bench-client-text}"
LIVE="${LIVE_API:-scanapp-scanapp-z1mwj4-api-1}"
VOLUME="${DATA_VOLUME:-scanapp-scanapp-z1mwj4_scanapp-data}"
PANEL="${PANEL_DIR:?set PANEL_DIR to the folder holding cases.json and photos/}"
HINTS="${HINTS_FILE:-$HOME/WebstormProjects/scanapp/data/latency/staging-reference027-20261003/device-text-hints-apple-vision-20261020.jsonl}"
LOCAL_OUT="${LOCAL_OUT:-$HOME/WebstormProjects/scanapp/data/latency/device-text-hints-20261020/staging}"
RUNS="${RUNS:-base footer base2 footer2}"
COMMIT="$(git rev-parse --short HEAD)"

if [[ "${1:-}" != "--run" ]]; then
  sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
  echo
  echo "host=$HOST live_api=$LIVE volume=$VOLUME bench=$BENCH code=$COMMIT runs='$RUNS'"
  echo "panel=$PANEL hints=$HINTS -> results in $LOCAL_OUT"
  exit 0
fi

[[ -f "$PANEL/cases.json" && -d "$PANEL/photos" && -f "$HINTS" ]] || { echo "panel or hints missing" >&2; exit 1; }
git diff --quiet HEAD -- api/app api/scripts || { echo "commit api/ changes first" >&2; exit 1; }

echo "== copy code $COMMIT, panel and hints to $HOST:$BENCH"
ssh -o BatchMode=yes "$HOST" "test ! -e '$BENCH' || { echo '$BENCH already exists' >&2; exit 1; }; mkdir -p '$BENCH/kit' '$BENCH/out' && chmod 700 '$BENCH'"
git archive --format=tar HEAD api/app api/scripts | ssh -o BatchMode=yes "$HOST" "tar -x -C '$BENCH'"
COPYFILE_DISABLE=1 tar --no-xattrs -C "$PANEL" -cf - cases.json photos | ssh -o BatchMode=yes "$HOST" "tar -x -C '$BENCH/kit'"
scp -q -o BatchMode=yes "$HINTS" "$HOST:$BENCH/kit/hints.jsonl"

ssh -o BatchMode=yes "$HOST" "$(printf 'BENCH=%q LIVE=%q VOLUME=%q DOCKER=%q RUNS=%q bash -s' \
  "$BENCH" "$LIVE" "$VOLUME" "$DOCKER" "$RUNS")" <<'EOF'
set -euo pipefail
D="$DOCKER"
state=$($D inspect "$LIVE" --format '{{.State.Status}}')
image=$($D inspect "$LIVE" --format '{{.Image}}')
echo "live api: $LIVE state=$state image=${image:7:12}"
[ "$state" = running ] || { echo "live API is not running; stopping here" >&2; exit 1; }
$D inspect "$LIVE" --format '{{.Id}} {{.Image}} {{.State.StartedAt}}' > "$BENCH/live-before.txt"
# The live environment goes straight to a 0600 file and is never printed.
umask 077
$D inspect "$LIVE" --format '{{range .Config.Env}}{{println .}}{{end}}' > "$BENCH/live.env"
vol=$($D volume inspect "$VOLUME" --format '{{.Mountpoint}}')
mkdir -p "$BENCH/data"
for entry in $(ls -A "$vol"); do
  case "$entry" in results.sqlite*|review|captures|tmp) ;; *) ln -s "/data/$entry" "$BENCH/data/$entry" ;; esac
done

restore() {
  set +e
  $D rm -f bench-api >/dev/null 2>&1
  if [ "$($D inspect "$LIVE" --format '{{.State.Status}}')" != running ]; then
    echo "== restart live API"; $D start "$LIVE" >/dev/null
  fi
  for i in $(seq 1 90); do
    $D exec "$LIVE" python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/api/v1/health').json().get('ready') else 1)" 2>/dev/null && break
    sleep 5
  done
  $D exec "$LIVE" python -c "import httpx; h=httpx.get('http://127.0.0.1:8000/api/v1/health').json(); print('live health', h.get('status'), 'ready', h.get('ready'), h.get('catalogue_import_id'))"
  rm -rf "$BENCH/kit" "$BENCH/live.env"
}
trap restore EXIT

echo "== stop live API (web, scraper and other services keep running)"
$D stop "$LIVE" >/dev/null

for run in $RUNS; do
  extra=""
  case "$run" in footer*) extra="-e CLIENT_TEXT_OCR=footer" ;; esac
  echo "== $run: start bench-api"
  $D rm -f bench-api >/dev/null 2>&1 || true
  rm -f "$BENCH/data/results.sqlite"*
  $D run -d --name bench-api --cpus 2 --memory 4g --env-file "$BENCH/live.env" \
    -e DATA_DIR=/bench -e TMP_DIR=/tmp/bench -e STORE_CAPTURES=false -e SCRAPER_ENABLED=false \
    -e DAILY_PRICES_ENABLED=false -e PRICE_GUIDE_ENABLED=false -e TCGDEX_PRICES_ENABLED=false \
    -e SCAN_PRICE_SERVER_READ=off -e SCAN_PRICE_START_ON_PROVISIONAL=false -e CARDMARKET_WEBVIEW_ENABLED=false \
    -e CLIENT_TEXT_HINTS=true $extra \
    -v "$VOLUME:/data:ro" -v "$BENCH/data:/bench" -v "$BENCH/kit:/kit:ro" -v "$BENCH/out:/out" \
    -v "$BENCH/api/app:/app/app:ro" -v "$BENCH/api/scripts:/app/scripts:ro" \
    "$image" >/dev/null
  for i in $(seq 1 180); do
    $D exec bench-api python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/api/v1/health').json().get('ready') else 1)" 2>/dev/null && break
    [ "$($D inspect bench-api --format '{{.State.Status}}')" = running ] || { $D logs --tail 30 bench-api; exit 1; }
    sleep 5
  done
  $D exec bench-api python -c "import httpx; h=httpx.get('http://127.0.0.1:8000/api/v1/health').json(); print('bench ready', h.get('ready'), h.get('catalogue_import_id'))"
  # Two warm-up scans, then the panel.
  $D exec bench-api python /app/scripts/cpu_replay.py --panel /kit/cases.json --root /kit --hint \
    --client-text /kit/hints.jsonl --limit 2 --out "/out/warm_$run.jsonl" >/dev/null
  $D exec bench-api python /app/scripts/cpu_replay.py --panel /kit/cases.json --root /kit --hint \
    --client-text /kit/hints.jsonl --out "/out/$run.jsonl" | tail -n 1
  $D logs bench-api 2>&1 | grep -E '^INFO scan.diagnostics (client_text|scan_reasons) ' > "$BENCH/out/$run.lines" || true
done
EOF

echo "== copy results to $LOCAL_OUT"
mkdir -p "$LOCAL_OUT"
scp -q -o BatchMode=yes "$HOST:$BENCH/out/*" "$LOCAL_OUT/"
ssh -o BatchMode=yes "$HOST" "rm -rf '$BENCH'"
python3 api/scripts/compare_replay.py "$LOCAL_OUT/base.jsonl" "$LOCAL_OUT/footer.jsonl" \
  "$LOCAL_OUT/base2.jsonl" "$LOCAL_OUT/footer2.jsonl" > "$LOCAL_OUT/compare.json"
echo "Done: $LOCAL_OUT/compare.json"
