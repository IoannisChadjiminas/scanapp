#!/bin/sh
# Approved card-deadline grading policy. Only the staging API is restarted.
set -eu
umask 077
audit=/tmp/scanapp-deadline019.sOEuqo/combined
checkout=/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code
project=scanapp-scanapp-z1mwj4
api=scanapp-scanapp-z1mwj4-api-1
rollback_dir=/etc/scanapp-staging/rollback-grading-deadline-018
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["photos"]==150 and r["card_responses_equal"]==150 and r["card_deadline"] and not r["diagnostic_detector_max_side"] and r["retested_photos"]>=len(r["affected_branches_rechecked"])' "$audit/parallel-summary.json"
cd "$checkout"
test "$(git rev-parse HEAD)" = fd7597009bbd328079383eca8207084d77bfbdb9
test -z "$(git diff --name-only -- api/app)"
test ! -e api/app/recognition/grading_parallel.py
test ! -e api/app/recognition/grading_control.py
test "$(docker inspect --format '{{.Image}}' "$api")" = sha256:7fb328d7c375c68f62bf1a32c9bf1cc43fecf65cefe4465692036560ae182cb2
mkdir "$rollback_dir"
chmod 700 "$rollback_dir"
tar -czf "$rollback_dir/code-before.tar.gz" api/app/config.py api/app/main.py api/app/recognition/ocr.py api/app/recognition/pipeline.py api/app/recognition/runtime.py api/app/recognition/label_vision.py
cp compose.dokploy.yaml "$rollback_dir/compose-before.yaml"
docker inspect --format '{{.Config.Image}}' "$api" > "$rollback_dir/image-name.txt"
docker inspect --format '{{.Id}}' scanapp-scanapp-z1mwj4-web-1 scanapp-scanapp-z1mwj4-scraper-1 > "$rollback_dir/other-containers-before.txt"
docker tag "$(docker inspect --format '{{.Image}}' "$api")" scanapp-staging-rollback:grading-deadline-018
cp /tmp/scanapp-deadline018-activate.yaml "$rollback_dir/activate.yaml"
cp /tmp/scanapp-deadline018-rollback.yaml "$rollback_dir/rollback.yaml"
rollback() {
    tar -xzf "$rollback_dir/code-before.tar.gz"
    for module in grading_parallel grading_control; do
        if test -e "api/app/recognition/$module.py"; then
            mv "api/app/recognition/$module.py" "$rollback_dir/$module.failed.py"
        fi
    done
    docker tag scanapp-staging-rollback:grading-deadline-018 "$(cat "$rollback_dir/image-name.txt")"
    docker compose -p "$project" -f compose.dokploy.yaml -f "$rollback_dir/rollback.yaml" up -d --no-deps api
}
trap 'status=$?; if test "$status" -ne 0; then rollback; fi' EXIT
tar -xzf /tmp/scanapp-deadline018-api.tar.gz
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
