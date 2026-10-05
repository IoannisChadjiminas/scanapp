#!/usr/bin/env bash
# Offline, read-only benchmark; output paths must be new absolute paths.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
pilot_dir="$1"
sources_file="$2"
output_file="$3"
shift 3
case "$pilot_dir:$sources_file:$output_file" in /*:/*:/*) ;; *) exit 2 ;; esac
test ! -e "$output_file"
test ! -e "$output_file.err"
candidate_dir="$repo_root/data/image-recovery/20261002-official/verified-final-v5"
docker run --rm --network none \
  --mount "type=bind,source=$candidate_dir,target=/data,readonly" \
  --mount type=volume,source=scanapp_scanapp-data,target=/data/models/original-data,readonly \
  --mount "type=bind,source=$repo_root/data/image-recovery/20261002-official/reference-overlay,target=/data/reference-images,readonly" \
  --mount type=volume,source=scanapp_scanapp-data,target=/data/reference-images/original-data,readonly \
  --mount "type=bind,source=$candidate_dir/images,target=/data/reference-images/recovered,readonly" \
  --mount "type=bind,source=$repo_root,target=/workspace,readonly" \
  --mount "type=bind,source=$pilot_dir,target=/pilot,readonly" \
  --mount "type=bind,source=$sources_file,target=/sources.json,readonly" \
  --entrypoint python scanapp-api:local \
  /workspace/api/scripts/benchmark_artwork_pilot.py --pilot-dir /pilot \
  --artwork-dir /data/artwork --photos-only --sources /sources.json "$@" \
  > "$output_file" 2> "$output_file.err"
