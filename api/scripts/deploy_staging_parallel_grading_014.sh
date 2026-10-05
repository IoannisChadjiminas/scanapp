#!/bin/sh
# API-only rollout of the frozen-response scheduling regression. No DB writes.
set -eu
umask 077
audit=/tmp/scanapp-latency014.G8kzxy
checkout=/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code
project=scanapp-scanapp-z1mwj4
api=scanapp-scanapp-z1mwj4-api-1
rollback_dir=/etc/scanapp-staging/rollback-parallel-grading-014
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["photos"]==150 and r["equal_responses"]==150 and r["grading_equal"]==150 and not r.get("diagnostic_detector_max_side",False)' "$audit/parallel-summary.json"
cd "$checkout"
test "$(git rev-parse HEAD)" = fd7597009bbd328079383eca8207084d77bfbdb9
test -z "$(git diff --name-only -- api/app)"
test ! -e api/app/recognition/grading_parallel.py
test "$(docker inspect --format '{{.Image}}' "$api")" = sha256:7fb328d7c375c68f62bf1a32c9bf1cc43fecf65cefe4465692036560ae182cb2
mkdir "$rollback_dir"
chmod 700 "$rollback_dir"
tar -czf "$rollback_dir/code-before.tar.gz" api/app/config.py api/app/main.py api/app/recognition/ocr.py api/app/recognition/pipeline.py api/app/recognition/runtime.py
cp compose.dokploy.yaml "$rollback_dir/compose-before.yaml"
docker inspect --format '{{.Config.Image}}' "$api" > "$rollback_dir/image-name.txt"
docker inspect --format '{{.Id}}' scanapp-scanapp-z1mwj4-web-1 scanapp-scanapp-z1mwj4-scraper-1 > "$rollback_dir/other-containers-before.txt"
docker tag "$(docker inspect --format '{{.Image}}' "$api")" scanapp-staging-rollback:parallel-grading-014
cp /tmp/scanapp-latency014-activate.yaml "$rollback_dir/activate.yaml"
cp /tmp/scanapp-latency014-rollback.yaml "$rollback_dir/rollback.yaml"
rollback() {
    tar -xzf "$rollback_dir/code-before.tar.gz"
    if test -e api/app/recognition/grading_parallel.py; then
        mv api/app/recognition/grading_parallel.py "$rollback_dir/grading_parallel.failed.py"
    fi
    docker tag scanapp-staging-rollback:parallel-grading-014 "$(cat "$rollback_dir/image-name.txt")"
    docker compose -p "$project" -f compose.dokploy.yaml -f "$rollback_dir/rollback.yaml" up -d --no-deps api
}
trap 'status=$?; if test "$status" -ne 0; then rollback; fi' EXIT
tar -xzf /tmp/scanapp-latency014-api.tar.gz
docker compose -p "$project" -f compose.dokploy.yaml -f "$rollback_dir/activate.yaml" config --quiet
docker compose -p "$project" -f compose.dokploy.yaml -f "$rollback_dir/activate.yaml" build api
docker compose -p "$project" -f compose.dokploy.yaml -f "$rollback_dir/activate.yaml" up -d --no-deps api
healthy=0
attempt=0
while test "$attempt" -lt 120; do
    if curl -fsS https://scan.pokesingle.com/api/v1/health > "$rollback_dir/health-after.json" &&
       python3 -c 'import json,sys; h=json.load(open(sys.argv[1])); assert h.get("ready") is True and h.get("catalogue_import_id")=="PS-RECOVERY-011-20261003"' "$rollback_dir/health-after.json"; then
        healthy=1
        break
    fi
    attempt=$((attempt + 1))
    sleep 3
done
test "$healthy" -eq 1
docker inspect --format '{{.Id}}' scanapp-scanapp-z1mwj4-web-1 scanapp-scanapp-z1mwj4-scraper-1 > "$rollback_dir/other-containers-after.txt"
cmp "$rollback_dir/other-containers-before.txt" "$rollback_dir/other-containers-after.txt"
cmp compose.dokploy.yaml "$rollback_dir/compose-before.yaml"
docker inspect --format '{{.Image}} {{.RestartCount}} {{.State.OOMKilled}}' "$api" > "$rollback_dir/image-after.txt"
