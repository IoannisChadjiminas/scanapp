#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p exports
docker compose -f compose.catalogue.yaml run --rm --build catalogue \
  -m bootstrap.offload export -o /exports/scanapp-index.tar
echo "Wrote $(pwd)/exports/scanapp-index.tar"
echo "Load it on staging with: ./scripts/offload-to-staging.sh"
