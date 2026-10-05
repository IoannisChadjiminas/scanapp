#!/bin/sh
# Approved API-only rollout. Run on auctaro-staging after unit/paired tests pass.
set -eu
umask 077
cd /etc/dokploy/compose/scanapp-scanapp-z1mwj4/code
test "$(git rev-parse HEAD)" = 129babe5242adcd674e326cf81e45abaf23368c6
git diff --quiet -- api/app/config.py api/app/cardmarket.py api/app/recognition/embed.py api/app/recognition/ocr.py api/app/recognition/rank.py api/app/recognition/pipeline.py
test ! -e api/app/recognition/orientation.py
test -f /tmp/scanapp-staging-accuracy-006.tar
rollback_dir=/etc/scanapp-staging/rollback-staging-accuracy-006
mkdir "$rollback_dir"
chmod 700 "$rollback_dir"
tar -czf "$rollback_dir/code-before.tar.gz" api/app/config.py api/app/cardmarket.py api/app/recognition/embed.py api/app/recognition/ocr.py api/app/recognition/rank.py api/app/recognition/pipeline.py compose.dokploy.yaml
docker ps --filter label=com.docker.compose.project=scanapp-scanapp-z1mwj4 --format '{{.Names}} {{.ID}}' > "$rollback_dir/containers-before.txt"
staging_image_id=$(docker inspect --format '{{.Image}}' scanapp-scanapp-z1mwj4-api-1)
test -n "$staging_image_id"
docker tag "$staging_image_id" scanapp-staging-rollback:staging-accuracy-006
docker inspect --format '{{.Config.Image}}' scanapp-scanapp-z1mwj4-api-1 > "$rollback_dir/image-name.txt"
rollback() {
    tar -xzf "$rollback_dir/code-before.tar.gz"
    if test -f api/app/recognition/orientation.py; then
        mv api/app/recognition/orientation.py "$rollback_dir/proposed-orientation.py"
    fi
    docker tag scanapp-staging-rollback:staging-accuracy-006 "$(cat "$rollback_dir/image-name.txt")"
    docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml up -d --no-deps api
}
trap 'status=$?; if test "$status" -ne 0; then rollback; fi' EXIT
tar -xf /tmp/scanapp-staging-accuracy-006.tar
docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml config --quiet
docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml build api
docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml up -d --no-deps api
healthy=0
attempt=0
while test "$attempt" -lt 45; do
    if curl -fsS https://staging-scan.auctaro.com/api/v1/health > "$rollback_dir/health-after.json" &&
       python3 -c 'import json,sys; h=json.load(open(sys.argv[1])); sys.exit(not(h.get("ready") is True and h.get("catalogue_backend")=="planetscale"))' "$rollback_dir/health-after.json"; then
        healthy=1
        break
    fi
    attempt=$((attempt + 1))
    sleep 2
done
test "$healthy" -eq 1
docker ps --filter label=com.docker.compose.project=scanapp-scanapp-z1mwj4 --format '{{.Names}} {{.ID}}' > "$rollback_dir/containers-after.txt"
