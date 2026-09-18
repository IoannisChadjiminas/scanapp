#!/usr/bin/env bash
# Apply exports/scanapp-index.tar into the running Scanapp data volume.
# Run this on the Scanapp host (staging), or via scripts/offload-to-staging.sh
set -euo pipefail

CONTAINER="${SCANAPP_API_CONTAINER:-$(docker ps --format '{{.Names}}' | grep -E 'scanapp.*-api-1$' | head -n 1 || true)}"
if [[ -z "$CONTAINER" ]]; then
  echo "No Scanapp API container is running" >&2
  exit 1
fi

PROJECT=$(docker inspect "$CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}')
WORKDIR=$(docker inspect "$CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')
IMAGE=$(docker inspect "$CONTAINER" --format '{{.Config.Image}}')
VOLUME=$(docker inspect "$CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}')
CODE="${STAGING_DIR:-$WORKDIR}"
TAR="${1:-$CODE/exports/scanapp-index.tar}"

if [[ ! -f "$TAR" ]]; then
  echo "Missing $TAR" >&2
  exit 1
fi
if [[ -z "$VOLUME" || -z "$IMAGE" ]]; then
  echo "Could not resolve API volume/image from $CONTAINER" >&2
  exit 1
fi

mkdir -p "$CODE/exports"
if [[ "$(realpath "$TAR")" != "$(realpath "$CODE/exports/scanapp-index.tar")" ]]; then
  cp "$TAR" "$CODE/exports/scanapp-index.tar"
fi

echo "== apply $CODE/exports/scanapp-index.tar -> volume $VOLUME (project $PROJECT)"
docker run --rm \
  -v "$VOLUME:/data" \
  -v "$CODE/api/app:/app/app:ro" \
  -v "$CODE/catalogue/bootstrap:/app/bootstrap:ro" \
  -v "$CODE/exports:/exports:ro" \
  -e DATA_DIR=/data \
  -e PYTHONPATH=/app \
  -w /app \
  "$IMAGE" \
  python -m bootstrap.offload apply /exports/scanapp-index.tar

echo "== restart $CONTAINER"
docker restart "$CONTAINER"
echo "Staging catalogue loaded."
