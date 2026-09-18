#!/usr/bin/env bash
# Download every TCGdex set (EN/JA/ZH), match stored Cardmarket URLs, apply on auctaro-staging.
set -euo pipefail
cd "$(dirname "$0")/.."

LANGS="${TCGDEX_LANGUAGES:-en,ja,zh-cn,zh-tw}"

echo "== download all sets ($LANGS)"
docker compose -f compose.catalogue.yaml run --rm --build catalogue \
  -m bootstrap.build --sets all --languages "$LANGS" --skip-models --extras
docker compose restart api

echo "== write Cardmarket URLs onto local cards"
docker compose -f compose.catalogue.yaml run --rm catalogue -m bootstrap.link

if [[ "${1:-}" == "--local-only" ]]; then
  echo "== pack local tar only"
  ./scripts/offload-local.sh
  exit 0
fi

echo "== pack and apply on staging"
./scripts/offload-to-staging.sh
