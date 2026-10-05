#!/bin/sh
# API-only rollout after paired phone tests and frozen-corpus accuracy review.
set -eu
umask 077
audit=/tmp/scanapp-ocr025.BTzU7Q
checkout=/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code
project=scanapp-scanapp-z1mwj4
api=scanapp-scanapp-z1mwj4-api-1
rollback_dir=/etc/scanapp-staging/rollback-ocr-complete-frame-025
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["photos"]==153 and r["counts"]=={"raw":100,"slab":50,"phone_capture":3} and not r["lost_correct_matches"]; assert r["correct"]["after"]>=r["correct"]["before"]+1; assert all(x["case"].startswith("phone_") for x in r["identity_or_status_changes"])' "$audit/ocr-framing-summary.json"
cd "$checkout"
test "$(git rev-parse HEAD)" = fd7597009bbd328079383eca8207084d77bfbdb9
test "$(docker inspect --format '{{.Image}}' "$api")" = sha256:a290ee795c519353e8359b558a26c90f2a945b2d01e283feefbc7e7fd9a7fc74
test ! -e api/app/recognition/ocr_framing.py
printf '%s\n' '9e1762b811e798eaf46fb63690aa8d1eba4a96e6dd8ff90adf21a1127dde8681  api/app/config.py' 'abe395ccf9521c98938236a3a79fa36ff41024c483340f1f77e5a06a428ee864  api/app/recognition/runtime.py' '6fd01c0df9d327f8713bffd4321b6cb2e240a5e9de2f86513c1110cd770561a0  api/app/recognition/ocr.py' 'b6aa2235822604552a6262d75d48a79ec3ca23b7674cc16e9871a02efc68c1b5  api/app/recognition/pipeline.py' | sha256sum --check
mkdir "$rollback_dir"
chmod 700 "$rollback_dir"
tar -czf "$rollback_dir/code-before.tar.gz" api/app/config.py api/app/recognition/runtime.py api/app/recognition/ocr.py api/app/recognition/pipeline.py
cp compose.dokploy.yaml "$rollback_dir/compose-before.yaml"
docker inspect --format '{{.Config.Image}}' "$api" > "$rollback_dir/image-name.txt"
docker inspect --format '{{.Id}}' scanapp-scanapp-z1mwj4-web-1 scanapp-scanapp-z1mwj4-scraper-1 > "$rollback_dir/other-containers-before.txt"
docker tag "$(docker inspect --format '{{.Image}}' "$api")" scanapp-staging-rollback:ocr-complete-frame-025
cp /tmp/scanapp-ocr025-activate.yaml "$rollback_dir/activate.yaml"
cp /tmp/scanapp-ocr025-rollback.yaml "$rollback_dir/rollback.yaml"
rollback() {
    tar -xzf "$rollback_dir/code-before.tar.gz"
    if test -e api/app/recognition/ocr_framing.py; then
        mv api/app/recognition/ocr_framing.py "$rollback_dir/ocr_framing.failed.py"
    fi
    docker tag scanapp-staging-rollback:ocr-complete-frame-025 "$(cat "$rollback_dir/image-name.txt")"
    docker compose -p "$project" -f compose.dokploy.yaml -f "$rollback_dir/rollback.yaml" up -d --no-deps api
}
trap 'status=$?; if test "$status" -ne 0; then rollback; fi' EXIT
tar -xzf /tmp/scanapp-ocr025-api.tar.gz
for file in api/app/config.py api/app/recognition/runtime.py api/app/recognition/ocr.py api/app/recognition/pipeline.py api/app/recognition/ocr_framing.py; do
    cmp "$file" "$audit/candidate/$file"
done
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
