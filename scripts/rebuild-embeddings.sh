#!/usr/bin/env bash
# Embed new reference images into the existing DINOv2 index (reuses old vectors).
# Default: pad only (what scans use). Pass --preprocess pad,square for both.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== embeddings"
docker compose -f compose.catalogue.yaml run --rm -T \
  -e PYTHONUNBUFFERED=1 \
  catalogue -u -m bootstrap.embeddings --preprocess pad "$@"

echo "Restart the API to load the new vectors:"
echo "  docker compose restart api"
