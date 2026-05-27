#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

SKIP_BUILD=0
SKIP_TESTS=0

for arg in "$@"; do
  case "$arg" in
    --skip-build)
      SKIP_BUILD=1
      ;;
    --skip-tests)
      SKIP_TESTS=1
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./scripts/release/prepare_release.sh [--skip-build] [--skip-tests]"
      exit 2
      ;;
  esac
done

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

VERSION="$("${PYTHON_BIN}" - <<'PY'
from src.app_metadata import APP_VERSION
print(APP_VERSION)
PY
)"

"${PYTHON_BIN}" scripts/release/verify_git_remote.py

if [ "${SKIP_TESTS}" -eq 0 ]; then
  ./scripts/check_no_secrets.sh
  ./.venv/bin/python scripts/ui_clickability_doctor.py
fi

if [ "${SKIP_BUILD}" -eq 0 ]; then
  ./scripts/release_smoke.sh
fi

ASSET_DIR="dist/release-assets/v${VERSION}"
"${PYTHON_BIN}" scripts/release/validate_release.py \
  --version "${VERSION}" \
  --allow-missing-windows \
  --smoke-status "passed" \
  --asset-dir "${ASSET_DIR}"

echo "Release assets prepared: ${ASSET_DIR}"
echo "Windows ZIP can be added after running scripts/windows/package_windows.ps1 on Windows."
