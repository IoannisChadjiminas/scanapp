#!/usr/bin/env bash
# Unique-link stored Cardmarket SKUs onto catalogue cards.
# Unique identity → write the URL. 2+ listings → scan picker, not auto-assign.
# Pass --promo to limit to S-P / SWSH / SVP / M-P and the other promo codes.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== stop API (sqlite)"
docker compose stop api

echo "== unique-link Cardmarket SKUs"
docker compose run --rm --no-deps -T \
  -e PYTHONUNBUFFERED=1 \
  -v "$PWD/api/app:/app/app" \
  -v "$PWD/catalogue/bootstrap:/app/bootstrap" \
  api python -u -m bootstrap.link "$@"

echo "== start API"
docker compose start api
echo "API is starting; wait until healthy before scanning."
