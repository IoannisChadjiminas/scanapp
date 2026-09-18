#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <tcgdex-set-id>[,<id>...]   e.g. $0 sv03.5" >&2
  exit 1
fi
docker compose -f compose.catalogue.yaml run --rm --build catalogue \
  -m bootstrap.build --sets "$1" --languages "${TCGDEX_LANGUAGES:-en,ja,zh-cn,zh-tw}" --skip-models
echo "Restart the API to load the new vectors: docker compose restart api"
