#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python_bin="${SCRAPER_PYTHON:-python3.13}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python 3.13 is required for the pinned scraper dependencies." >&2
  echo "Install Python 3.13, or set SCRAPER_PYTHON to a compatible Python 3.10–3.13 executable." >&2
  exit 1
fi

if [[ ! -x .venv-scraper/bin/python ]]; then
  "$python_bin" -m venv .venv-scraper
fi
.venv-scraper/bin/python -m pip install -r scraper/requirements.txt
echo "Local scraper environment is ready at .venv-scraper."
