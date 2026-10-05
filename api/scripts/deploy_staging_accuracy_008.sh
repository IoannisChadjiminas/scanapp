#!/bin/sh
# Approved API-only guard-order correction; preserve earlier accuracy fixes.
set -eu
umask 077
cd /etc/dokploy/compose/scanapp-scanapp-z1mwj4/code
test "$(git rev-parse HEAD)" = 129babe5242adcd674e326cf81e45abaf23368c6
test "$(sha256sum api/app/cardmarket.py | cut -d ' ' -f 1)" = eedca9ea0a85184187c99675f27e03ea5d5a42a03728d8fa8051e958ce4eaca8
rollback_dir=/etc/scanapp-staging/rollback-staging-accuracy-008
mkdir "$rollback_dir"
chmod 700 "$rollback_dir"
tar -czf "$rollback_dir/code-before.tar.gz" api/app/cardmarket.py compose.dokploy.yaml
docker ps --filter label=com.docker.compose.project=scanapp-scanapp-z1mwj4 --format '{{.Names}} {{.ID}}' > "$rollback_dir/containers-before.txt"
docker tag "$(docker inspect --format '{{.Image}}' scanapp-scanapp-z1mwj4-api-1)" scanapp-staging-rollback:staging-accuracy-008
docker inspect --format '{{.Config.Image}}' scanapp-scanapp-z1mwj4-api-1 > "$rollback_dir/image-name.txt"
rollback() {
    tar -xzf "$rollback_dir/code-before.tar.gz"
    docker tag scanapp-staging-rollback:staging-accuracy-008 "$(cat "$rollback_dir/image-name.txt")"
    docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml up -d --no-deps api
}
trap 'status=$?; if test "$status" -ne 0; then rollback; fi' EXIT
tar -xf /tmp/scanapp-staging-accuracy-008.tar
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
