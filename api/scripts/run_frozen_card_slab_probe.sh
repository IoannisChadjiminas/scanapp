#!/usr/bin/env bash
# Offline probe of original frozen photos. No network or persistent DB writes.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
output_dir="$1"
run_name="$2"
sources_file="$3"
shift 3
case "$output_dir:$sources_file" in /*:/*) ;; *) exit 2 ;; esac
case "$run_name" in *[!a-zA-Z0-9_-]*|'') exit 2 ;; esac
test -d "$output_dir"
test -f "$sources_file"
test ! -e "$output_dir/$run_name.jsonl"
test ! -e "$output_dir/$run_name.err"
test ! -e "$output_dir/$run_name-code.json"
candidate_dir="$repo_root/data/image-recovery/20261002-official/verified-final-v5"
docker run --rm --network none \
  --mount "type=bind,source=$candidate_dir,target=/data,readonly" \
  --mount type=volume,source=scanapp_scanapp-data,target=/data/models/original-data,readonly \
  --mount "type=bind,source=$repo_root/data/image-recovery/20261002-official/reference-overlay,target=/data/reference-images,readonly" \
  --mount type=volume,source=scanapp_scanapp-data,target=/data/reference-images/original-data,readonly \
  --mount "type=bind,source=$candidate_dir/images,target=/data/reference-images/recovered,readonly" \
  --mount "type=bind,source=$repo_root,target=/workspace,readonly" \
  --mount "type=bind,source=$sources_file,target=/sources.json,readonly" \
  --mount "type=bind,source=$output_dir,target=/audit" \
  --entrypoint python scanapp-api:local \
  /workspace/api/scripts/probe_fresh_cards_and_slabs.py \
  --sources /sources.json --code-snapshot "/audit/$run_name-code.json" "$@" \
  > "$output_dir/$run_name.jsonl" 2> "$output_dir/$run_name.err"
