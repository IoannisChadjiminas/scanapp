#!/usr/bin/env bash
# Print a helper_id + token. Paste once in the Chrome helper for that server.
set -euo pipefail
cd "$(dirname "$0")/.."
target="${1:-local}"
case "$target" in
  local)
    docker compose exec -T api python -m app.helper_credential
    ;;
  staging)
    ssh -o BatchMode=yes "${STAGING_SSH:-auctaro-staging}" bash -s <<'EOF'
set -euo pipefail
c=$(docker ps --format '{{.Names}}' | grep -E 'scanapp.*-api-1$' | head -n 1 || true)
if [ -z "$c" ]; then
  echo "No Scanapp API container on staging" >&2
  exit 1
fi
docker exec "$c" python -m app.helper_credential
EOF
    ;;
  *)
    echo "usage: $0 [local|staging]" >&2
    exit 1
    ;;
esac
