#!/bin/bash
# Simulate a phone on the frozen panel, replay it on the local catalogue, and
# estimate a stage-1 gate. Nothing here is deployed. The catalogue and the
# reference images are a read-only copy of the public staging export.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
COREML_PY="${COREML_PY:-/tmp/coreml-stage0/bin/python}"
OUT="${OUT:-$ROOT/data/latency/stage0-simulation-20261021}"
KIT="$OUT/kit"
RUNTIME="$OUT/runtime"
PORT="${PORT:-8017}"
ONNX="${ONNX:-$ROOT/data/catalogue-completion/staging-data-local-20261014/models/dinov2_small.onnx}"
MODELS="${MODELS:-$ROOT/data/catalogue-completion/staging-data-local-20261014/models}"
MODEL="$OUT/coreml_pal8.mlpackage"

mkdir -p "$OUT" "$RUNTIME"
if [[ ! -x /tmp/vision_text || "$ROOT/api/scripts/vision_text.swift" -nt /tmp/vision_text ]]; then
  swiftc -O "$ROOT/api/scripts/vision_text.swift" -o /tmp/vision_text
fi
"$PY" "$ROOT/api/scripts/simulate_stage0.py" fields --out "$OUT" --vision /tmp/vision_text
"$PY" "$ROOT/api/scripts/footer_numbers.py" \
  --stage0 "$OUT/stage0.jsonl" --catalog "$KIT/catalog.sqlite" \
  --totals "$ROOT/data/catalogue-completion/staging-data-local-20261014/catalog.sqlite" \
  --vision /tmp/vision_text --ablation "$OUT/footer-ablation.json"

if [[ ! -d "$MODEL" ]]; then
  "$COREML_PY" "$ROOT/api/scripts/simulate_stage0.py" convert --onnx "$ONNX" --model "$MODEL"
fi
"$COREML_PY" "$ROOT/api/scripts/simulate_stage0.py" embed --out "$OUT" --model "$MODEL"

# Point the exported catalogue at the local reference images. The export file
# itself stays unchanged.
if [[ ! -f "$RUNTIME/catalog.sqlite" ]]; then
  "$PY" - << PY
import shutil, sqlite3
from pathlib import Path
kit = Path("$KIT")
runtime = Path("$RUNTIME")
images = kit / "reference-images"
shutil.copy(kit / "catalog.sqlite", runtime / "catalog.sqlite")
db = sqlite3.connect(runtime / "catalog.sqlite")
db.execute("UPDATE cards SET image_path = replace(image_path, '/data/reference-images', ?)", (str(images),))
db.commit()
print("rewrote", db.execute("SELECT COUNT(*) FROM cards WHERE image_path LIKE ?", (str(images) + "%",)).fetchone()[0])
PY
fi
ln -sfn "$KIT/vectors" "$RUNTIME/vectors"
ln -sfn "$MODELS" "$RUNTIME/models"
ln -sfn "$KIT/reference-images" "$RUNTIME/reference-images"

export DATA_DIR="$RUNTIME"
export CATALOGUE_BACKEND=sqlite
export PREPROCESS_CONFIG=pad
export PRICE_GUIDE_ENABLED=false
export TCGDEX_PRICES_ENABLED=false
export SCAN_PRICE_SERVER_READ=off
export ORT_INTRA_THREADS=2
export DINO_INTRA_THREADS=2
export OMP_NUM_THREADS=1
export GRADING_AT_CARD_DEADLINE=true
export GRADING_REQUIRES_CLIENT_HINT=true
export APP_SLAB_DETECTION=true
export OCR_COMPLETE_FRAME_FIRST=true
export OCR_ADAPTIVE_FOOTER=true
export OCR_TITLE_ONLY_SINGLE_PRINTING=false
export OCR_DAMAGED_FOOTER_ORDER=false
export OCR_PARALLEL_REGIONS=true
export OCR_CONFLICT_TITLE_RETRY=true
export OCR_LABEL_NAME_FILTER=true
export TEXT_IDENTITY_CANDIDATES=true
export SLAB_LABEL_IDENTITY=true
export SLAB_TEXT_RECOVERY=true
export FULL_IMAGE_TEXT_FALLBACK=true
export APP_CLIENT_TEXT=true
export CLIENT_TEXT_HINTS=true
export CLIENT_TEXT_OCR=footer
export APP_CLIENT_LABEL=false
export APP_CLIENT_EMBEDDING=false
export APP_CLIENT_QUALITY=false
export ENABLE_MATCHED=true
export PARALLEL_GRADING=true

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" || true
    wait "$SERVER_PID" || true
  fi
}
trap cleanup EXIT

cd "$ROOT/api"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$OUT/server.log" 2>&1 &
SERVER_PID=$!
ready=0
for _ in $(seq 1 180); do
  if "$PY" - << PY
import sys, urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:$PORT/api/v1/health", timeout=2).read()
except Exception:
    sys.exit(1)
PY
  then
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "API failed to start" >&2
    tail -40 "$OUT/server.log" >&2
    exit 1
  fi
  sleep 2
done
if [[ "$ready" != 1 ]]; then
  echo "API did not become ready" >&2
  tail -40 "$OUT/server.log" >&2
  exit 1
fi

"$PY" "$ROOT/api/scripts/cpu_replay.py" \
  --panel "$OUT/cases.json" --root "$OUT/panel" --stage0 "$OUT/stage0.jsonl" \
  --hint --server-pid "$SERVER_PID" --url "http://127.0.0.1:$PORT/api/v1/scans" \
  --out "$OUT/replay.jsonl"

"$PY" "$ROOT/api/scripts/estimate_stage1.py" \
  --panel "$OUT/stage0.jsonl" --index "$KIT/vectors/pad" --catalog "$KIT/catalog.sqlite" \
  --replay "$OUT/replay.jsonl" --log "$OUT/server.log" --out "$OUT/stage1.json" \
  --duplicates-out "$ROOT/docs/experiments/stage0-duplicate-pairs-20261021.csv"

"$PY" "$ROOT/api/scripts/estimate_stage1b.py" \
  --panel "$OUT/stage0.jsonl" --photos "$OUT/panel" --cases "$OUT/cases.json" \
  --index "$KIT/vectors/pad" --catalog "$KIT/catalog.sqlite" --references "$KIT" \
  --replay "$OUT/replay.jsonl" --out "$OUT/stage1b.json"
