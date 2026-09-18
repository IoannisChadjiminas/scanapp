#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p exports
docker compose -f compose.catalogue.yaml run --rm --build catalogue \
  -m bootstrap.offload export -o /exports/scanapp-index.tar
echo "Wrote $(pwd)/exports/scanapp-index.tar"
echo "On staging, copy the tar into exports/ then:"
echo "  docker compose -f compose.dokploy.yaml -f compose.catalogue.yaml run --rm --build catalogue \\"
echo "    -m bootstrap.offload apply /exports/scanapp-index.tar"
echo "  docker compose -f compose.dokploy.yaml restart api"
