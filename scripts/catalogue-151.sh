#!/usr/bin/env bash
# English 151 from this machine: download, helper pause, link, pack, apply on auctaro-staging.
set -euo pipefail
cd "$(dirname "$0")/.."

SET_ID="${TCGDEX_SET:-sv03.5}"
LANGS="${TCGDEX_LANGUAGES:-en}"
STAGING_SSH="${STAGING_SSH:-auctaro-staging}"
CM_URL="https://www.cardmarket.com/en/Pokemon/Products/Singles/151"

download() {
  echo "== download 151 ($SET_ID, languages $LANGS)"
  docker compose -f compose.catalogue.yaml run --rm --build catalogue \
    -m bootstrap.build --sets "$SET_ID" --languages "$LANGS" --skip-models
  docker compose restart api
}

link_and_ship() {
  echo "== write Cardmarket URLs onto local cards"
  docker compose -f compose.catalogue.yaml run --rm catalogue -m bootstrap.link
  if [[ "${SKIP_STAGING:-}" == "1" ]]; then
    echo "== pack local tar only"
    ./scripts/offload-local.sh
    return
  fi
  echo "== pack and apply on staging ($STAGING_SSH)"
  ./scripts/offload-to-staging.sh
}

usage() {
  echo "usage: $0 [--download-only | --link-offload | --local-only]" >&2
  echo "  (no args)        download 151, wait for helper, link, apply on auctaro-staging" >&2
  echo "  --download-only  images + vectors + CDN URLs only" >&2
  echo "  --link-offload   after helper Import/Save; link + staging apply" >&2
  echo "  --local-only     like --link-offload but do not SSH to staging" >&2
}

case "${1:-}" in
  -h | --help)
    usage
    exit 0
    ;;
  --download-only)
    download
    echo "Helper: Local Docker http://localhost:8080"
    echo "Open $CM_URL and Import this set page (or Save a product)."
    echo "Then: $0 --link-offload"
    ;;
  --local-only)
    SKIP_STAGING=1
    link_and_ship
    ;;
  --link-offload)
    link_and_ship
    ;;
  "")
    download
    echo
    echo "Helper: Local Docker http://localhost:8080"
    echo "Open $CM_URL"
    echo "Import this set page (or crawl the whole set / Save a product)."
    if [[ -t 0 ]]; then
      echo "Press Enter when that is done."
      read -r _
      link_and_ship
    else
      echo "Then run: $0 --link-offload"
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac
