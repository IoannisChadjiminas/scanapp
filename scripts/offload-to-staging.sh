#!/usr/bin/env bash
# Pack the local index (if needed), copy it to auctaro-staging, apply, restart API.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${STAGING_SSH:-auctaro-staging}"
TAR="${1:-exports/scanapp-index.tar}"

if [[ ! -f "$TAR" ]]; then
  echo "== pack local index"
  ./scripts/offload-local.sh
  TAR=exports/scanapp-index.tar
fi

echo "== discover staging Scanapp"
REMOTE=$(ssh -o BatchMode=yes "$HOST" bash -s <<'EOF'
set -euo pipefail
c=$(docker ps --format '{{.Names}}' | grep -E 'scanapp.*-api-1$' | head -n 1 || true)
if [ -z "$c" ]; then
  echo "No Scanapp API container on staging" >&2
  exit 1
fi
docker inspect "$c" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
EOF
)

echo "== copy $TAR -> $HOST:$REMOTE/exports/"
ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE/exports'"
scp -o BatchMode=yes "$TAR" "$HOST:$REMOTE/exports/scanapp-index.tar"
scp -o BatchMode=yes scripts/offload-apply.sh "$HOST:/tmp/scanapp-offload-apply.sh"
ssh -o BatchMode=yes "$HOST" "chmod +x /tmp/scanapp-offload-apply.sh && STAGING_DIR='$REMOTE' /tmp/scanapp-offload-apply.sh"
echo "Done. Check https://staging-scan.auctaro.com/api/v1/health"
