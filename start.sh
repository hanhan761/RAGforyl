#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "[1/5] Creating virtual environment..."
  python3 -m venv .venv
fi

. .venv/bin/activate
echo "[2/5] Installing RAGforyl..."
python -m pip install -e .

[ -f .env ] || cp .env.example .env
mkdir -p data/source data/index
if ! find data/source -maxdepth 1 -type f | grep -q .; then
  cp examples/sources/flight_basics.md data/source/flight_basics.md
fi

echo "[3/5] Checking environment..."
python -m ragforyl doctor

if [ ! -f data/index/manifest.json ]; then
  echo "[4/5] Building the demo knowledge graph..."
  python -m ragforyl build
else
  echo "[4/5] Existing index found."
fi

echo "[5/5] Opening http://127.0.0.1:8000"
python -m ragforyl serve --host 127.0.0.1 --port 8000 --open-browser
