#!/usr/bin/env bash
# Build and start the scraper lanes on the scraper host from this checkout,
# then check that the API container can reach every lane.
#   SCRAPER_SSH=root@scraper-1 ./scripts/scraper-host/deploy.sh
# API_SSH= (empty) skips the reachability check.
set -euo pipefail
cd "$(dirname "$0")/../.."

SCRAPER_SSH="${SCRAPER_SSH:?set SCRAPER_SSH, for example root@scraper-1}"
REMOTE_DIR="${REMOTE_DIR:-/opt/scanapp-scraper}"
API_SSH="${API_SSH-auctaro-staging}"
API_CONTAINER="${API_CONTAINER:-scanapp-scanapp-z1mwj4-api-1}"
COMPOSE="docker compose -f compose.scraper-host.yaml --env-file .env"
LANES=(scraper-a scraper-b)

tag="$(git rev-parse --short HEAD)"
if ! git diff --quiet HEAD -- scraper api/app docker/scraper.Dockerfile compose.scraper-host.yaml; then
  tag="${tag}-dirty"
fi

echo "== check $REMOTE_DIR/.env on $SCRAPER_SSH"
if ! ssh "$SCRAPER_SSH" "test -s '$REMOTE_DIR/.env'"; then
  echo "missing $REMOTE_DIR/.env. Copy docker/scraper-host.env.example there and fill it in" >&2
  exit 1
fi

echo "== sync build context ($tag)"
rsync -az --delete --relative \
  --filter 'protect .env' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' \
  ./compose.scraper-host.yaml ./docker/scraper.Dockerfile ./scraper/ ./api/app/ \
  "$SCRAPER_SSH:$REMOTE_DIR/"

echo "== build and start ${LANES[*]}"
ssh "$SCRAPER_SSH" "cd '$REMOTE_DIR' && SCRAPER_IMAGE_TAG='$tag' $COMPOSE up -d --build --remove-orphans"

echo "== wait for healthy"
deadline=$((SECONDS + 180))
while :; do
  states="$(ssh "$SCRAPER_SSH" "cd '$REMOTE_DIR' && for lane in ${LANES[*]}; do id=\$($COMPOSE ps -q \$lane); echo \"\$lane \$(docker inspect --format '{{.State.Health.Status}}' \$id 2>/dev/null || echo missing)\"; done")"
  if ! grep -v -q ' healthy$' <<<"$states"; then
    echo "$states"
    break
  fi
  if (( SECONDS > deadline )); then
    echo "$states" >&2
    echo "lanes not healthy after 180 s. Logs: ssh $SCRAPER_SSH 'cd $REMOTE_DIR && $COMPOSE logs --tail 80'" >&2
    exit 1
  fi
  sleep 10
done

if [[ -z "$API_SSH" ]]; then
  echo "== API_SSH empty, skipping reachability check"
  exit 0
fi

settings="$(ssh "$SCRAPER_SSH" "grep -E '^(SCRAPER_BIND_ADDR|SCRAPER_A_PORT|SCRAPER_B_PORT)=' '$REMOTE_DIR/.env'")"
value() { sed -n "s/^$1=//p" <<<"$settings" | tail -1 | tr -d '"'"'"; }
bind="$(value SCRAPER_BIND_ADDR)"
a_port="$(value SCRAPER_A_PORT)"
b_port="$(value SCRAPER_B_PORT)"
urls=("http://$bind:${a_port:-8001}" "http://$bind:${b_port:-8002}")

echo "== reach lanes from $API_CONTAINER on $API_SSH"
for url in "${urls[@]}"; do
  ssh "$API_SSH" "docker exec '$API_CONTAINER' python -c \"import urllib.request; r = urllib.request.urlopen('$url/health', timeout=5); print('$url', r.status, r.read().decode())\""
done

echo
echo "lanes: ${urls[*]}"
echo "one lane today: set SCRAPER_URL=${urls[0]} on the API service in Dokploy and redeploy."
echo "all lanes: SCRAPER_URLS=$(IFS=,; echo "${urls[*]}") once the lane pool (plan part 3) is merged."
