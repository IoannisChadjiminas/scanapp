#!/usr/bin/env bash
# List catalogue cards with no downloaded reference image.
# Pass --retry to download rows that still have a TCGdex URL (skips cards with no CDN).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p exports

retry=0
for arg in "$@"; do
  if [[ "$arg" == "--retry" ]]; then
    retry=1
  fi
done

if [[ "$retry" -eq 1 ]]; then
  echo "== stop API (sqlite)"
  docker compose stop api
fi

echo "== missing images"
docker compose run --rm --no-deps -T \
  -e PYTHONUNBUFFERED=1 \
  -v "$PWD/api/app:/app/app" \
  -v "$PWD/catalogue/bootstrap:/app/bootstrap" \
  -v "$PWD/exports:/exports" \
  api python -u -m bootstrap.missing_images --out /exports/missing-images.json "$@"

if [[ "$retry" -eq 1 ]]; then
  echo "== start API"
  docker compose start api
  echo "New files are not in DINOv2 until you rebuild embeddings."
fi
echo "Report: $(pwd)/exports/missing-images.json"
echo "Cardmarket URLs: $(pwd)/exports/missing-cardmarket-urls.txt"
