#!/bin/bash
# Switch one ScanApp deployment to a catalogue release file, with a recorded rollback.
#
#   catalogue-release-switch.sh apply|preflight|prepare|forward|rollback|status
#
# Run on the host that runs the deployment. The release file holds no secrets: the catalogue
# schema, the import id, the artifact directories and the recognition flags.
#
# Required:
#   RELEASE_FILE   the reviewed release file (docs/release/phase-e/catalogue-release.env)
#   RELEASE_NAME   a name for this switch, used for the rollback directory (phase-e-20261110)
#   PROJECT        the Dokploy Compose project (docker compose -p ...)
# Optional (defaults are production's):
#   CONFIG_DIR     /etc/scanapp-production
#   COMPOSE_FILE   compose.dokploy.production.yaml
#   CODE_DIR       /etc/dokploy/compose/$PROJECT/code
#   MANIFEST       absolute path of the sha256 list of the artifacts (paths relative to the data
#                  volume). When set,
#                  preflight checks every file the release names; without it only that the
#                  directories exist.
#   MIN_FREE_MB    memory that must be available before the API starts (default 3072)
#
# apply     prepare, then forward: the one command that switches a deployment.
# prepare   saves the release in use (if any), stages the new one and writes the rollback file:
#           the saved release with every flag the new release adds set explicitly to false.
# forward   runs preflight, installs the new release, recreates the API, waits for health and
#           checks that the API reports this release. On failure it rolls back by itself.
# rollback  installs the rollback file and recreates the API. On a first start (nothing was
#           running before) it stops the API and removes the release file.
set -euo pipefail

: "${RELEASE_NAME:?set RELEASE_NAME}" "${PROJECT:?set PROJECT}"
CONFIG_DIR=${CONFIG_DIR:-/etc/scanapp-production}
COMPOSE_FILE=${COMPOSE_FILE:-compose.dokploy.production.yaml}
CODE_DIR=${CODE_DIR:-/etc/dokploy/compose/$PROJECT/code}
MIN_FREE_MB=${MIN_FREE_MB:-3072}
ENV_FILE=$CONFIG_DIR/catalogue-release.env
R=$CONFIG_DIR/catalogue-rollback/$RELEASE_NAME
API=$PROJECT-api-1
SUDO="sudo -n"; [ "$(id -u)" = 0 ] && SUDO=

value() { $SUDO grep -E "^$2=" "$1" | tail -1 | cut -d= -f2-; }
flags() { $SUDO grep -E '^[A-Z0-9_]+=(true|false)$' "$1" | cut -d= -f1 | sort; }
data_dir() { docker volume inspect "${PROJECT}_scanapp-data" --format '{{.Mountpoint}}'; }

recreate() {  # only the API; on a first start (no API container yet) the whole project
  local only="--no-deps api"
  docker inspect "$API" >/dev/null 2>&1 || only=
  # shellcheck disable=SC2086
  (cd "$CODE_DIR" && $SUDO docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d $only >/dev/null 2>&1)
}

health() {  # prints the health line; succeeds only when ready and on the release in $1
  local want; want=$(value "$1" PLANETSCALE_IMPORT_ID)
  for _ in $(seq 1 60); do
    [ "$(docker inspect "$API" --format '{{.State.Health.Status}}' 2>/dev/null || echo none)" = healthy ] && break
    sleep 10
  done
  docker exec "$API" python3 -c "
import json, sys, urllib.request
h = json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=10).read())
print('health', h['status'], 'ready', h['ready'], 'import', h.get('catalogue_import_id'))
sys.exit(0 if h['status'] == 'ok' and h['ready'] and h.get('catalogue_import_id') == '$want' else 1)"
}

report() {
  docker inspect "$API" --format 'restarts={{.RestartCount}} oom={{.State.OOMKilled}} status={{.State.Health.Status}}'
  docker exec "$API" sh -c 'env | grep -E "^(RANK_|OCR_|PRINTING_|RETRY_|SET_TOTAL|NUMBER_LED|LATIN_NAME|VERIFY_UNMATCHED|TWIN_|PLANETSCALE_SCHEMA|PLANETSCALE_IMPORT_ID)" | sort'
}

flags_match() {  # every flag in the file has that value inside the container
  local bad=0 line
  while read -r line; do
    docker exec "$API" sh -c "[ \"\$${line%%=*}\" = \"${line#*=}\" ]" || { echo "flag differs in the container: ${line%%=*}"; bad=1; }
  done < <($SUDO grep -E '^[A-Z0-9_]+=(true|false)$' "$1")
  return $bad
}

preflight() {
  local ok=0 data free dir
  fail() { echo "FAIL  $*"; ok=1; }
  pass() { echo "ok    $*"; }
  $SUDO test -f "$R/catalogue-release.env.after" && pass "release staged in $R" || fail "release not staged: run prepare"
  $SUDO test -f "$CONFIG_DIR/planetscale.env" && pass "catalogue database role file present" || fail "$CONFIG_DIR/planetscale.env is missing"
  $SUDO test -f "$CODE_DIR/$COMPOSE_FILE" && pass "compose file present" || fail "$CODE_DIR/$COMPOSE_FILE is missing"
  data=$(data_dir 2>/dev/null) && pass "data volume $data" || fail "data volume ${PROJECT}_scanapp-data is missing"
  if [ -n "${data:-}" ] && $SUDO test -f "$R/catalogue-release.env.after"; then
    for key in REFERENCE_FEATURES_DIR ARTWORK_BUNDLE_DIR; do
      dir=$(value "$R/catalogue-release.env.after" $key)
      $SUDO test -d "$data${dir#/data}" && pass "$key $dir" || fail "$key $dir is not on the data volume"
    done
    $SUDO test -d "$data/models" && pass "models directory" || fail "models directory is missing"
    if [ -n "${MANIFEST:-}" ]; then
      if $SUDO sh -c 'cd "$1" && sha256sum --quiet -c "$2" >/dev/null 2>&1' sh "$data" "$MANIFEST"; then pass "artifact checksums ($(wc -l < "$MANIFEST") files)"
      else fail "artifact checksums differ from $MANIFEST"; fi
    else
      echo "note  MANIFEST not set: artifact checksums not checked"
    fi
  fi
  free=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  if docker inspect "$API" >/dev/null 2>&1; then pass "API container exists (memory in use is counted in it)"
  elif [ "$free" -ge "$MIN_FREE_MB" ]; then pass "memory available ${free} MB"
  else fail "memory available ${free} MB, need $MIN_FREE_MB MB for a first start"; fi
  return $ok
}

case "${1:-}" in
apply) "$0" prepare && "$0" forward ;;
preflight) preflight ;;
prepare)
  : "${RELEASE_FILE:?set RELEASE_FILE}"
  $SUDO mkdir -p "$R"
  if $SUDO test -f "$ENV_FILE"; then
    $SUDO test -f "$R/catalogue-release.env.before" || $SUDO cp -p "$ENV_FILE" "$R/catalogue-release.env.before"
    docker inspect "$API" 2>/dev/null | $SUDO tee "$R/container-before.json" >/dev/null || true
  fi
  $SUDO install -m 600 "$RELEASE_FILE" "$R/catalogue-release.env.after"
  if $SUDO test -f "$R/catalogue-release.env.before"; then
    { $SUDO cat "$R/catalogue-release.env.before"
      comm -13 <(flags "$R/catalogue-release.env.before") <(flags "$R/catalogue-release.env.after") | sed 's/$/=false/'
    } | $SUDO tee "$R/catalogue-release.env.rollback" >/dev/null
  fi
  $SUDO chmod 600 "$R"/*
  $SUDO sha256sum "$R"/catalogue-release.env.* ;;
forward)
  preflight
  $SUDO install -m 600 -o root -g root "$R/catalogue-release.env.after" "$ENV_FILE"
  recreate
  if health "$R/catalogue-release.env.after" && flags_match "$R/catalogue-release.env.after"; then report; echo "FORWARD OK $RELEASE_NAME"
  else echo "FORWARD FAILED: rolling back"; "$0" rollback; exit 1; fi ;;
rollback)
  if $SUDO test -f "$R/catalogue-release.env.rollback"; then
    $SUDO install -m 600 -o root -g root "$R/catalogue-release.env.rollback" "$ENV_FILE"
    recreate
    if health "$R/catalogue-release.env.rollback" && flags_match "$R/catalogue-release.env.rollback"; then report; echo "ROLLED BACK to the release before $RELEASE_NAME"
    else report || true; echo "ROLLBACK HEALTH CHECK FAILED"; exit 1; fi
  else
    (cd "$CODE_DIR" && $SUDO docker compose -p "$PROJECT" -f "$COMPOSE_FILE" stop api) || true
    $SUDO test -f "$ENV_FILE" && $SUDO mv "$ENV_FILE" "$R/catalogue-release.env.removed"
    echo "ROLLED BACK: no release ran before $RELEASE_NAME, the API is stopped"
  fi ;;
status) health "$ENV_FILE" || true; report ;;
*) sed -n '2,29p' "$0"; exit 2 ;;
esac
