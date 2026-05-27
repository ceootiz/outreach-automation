#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

latest_dmg() {
  "${PYTHON_BIN}" - <<'PY'
from pathlib import Path

dmgs = sorted(Path("dist").glob("Gmail Рассылка*.dmg"), key=lambda path: path.stat().st_mtime, reverse=True)
if dmgs:
    print(dmgs[0])
PY
}

./scripts/test_mac.sh
./scripts/build_macos.sh
./scripts/smoke_packaged_app.sh
./scripts/build_dmg.sh --versioned

DMG_PATH="$(latest_dmg)"
if [ -z "${DMG_PATH}" ]; then
  echo "No DMG found after build."
  exit 1
fi

./scripts/smoke_dmg.sh "${DMG_PATH}"

echo "Release smoke passed."
echo "Latest DMG: ${DMG_PATH}"
