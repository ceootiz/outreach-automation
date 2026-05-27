#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

CREATE_DRAFT=0
ALLOW_PARTIAL=0
for arg in "$@"; do
  case "$arg" in
    --create-draft)
      CREATE_DRAFT=1
      ;;
    --allow-partial)
      ALLOW_PARTIAL=1
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./scripts/release/github_release.sh [--create-draft] [--allow-partial]"
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

TAG="v${VERSION}"
NOTES="docs/RELEASE_NOTES_${VERSION//./_}.md"
MANIFEST="dist/release_manifest.json"
ASSET_DIR="dist/release-assets/v${VERSION}"

validate_args=(--version "${VERSION}" --smoke-status "prepared" --asset-dir "${ASSET_DIR}")
if [ "${CREATE_DRAFT}" -eq 0 ] || [ "${ALLOW_PARTIAL}" -eq 1 ]; then
  validate_args+=(--allow-missing-macos --allow-missing-windows)
fi
"${PYTHON_BIN}" scripts/release/validate_release.py "${validate_args[@]}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI not found. Draft release not created."
  echo "Prepared tag/title: ${TAG}"
  echo "Prepared notes: ${NOTES}"
  echo "Prepared assets directory: ${ASSET_DIR}"
  exit 0
fi

if [ "${CREATE_DRAFT}" -ne 1 ]; then
  echo "Dry run only. To create a draft GitHub release, run:"
  echo "./scripts/release/github_release.sh --create-draft"
  echo "Use --allow-partial only for internal partial release prep."
  echo "Tag/title: ${TAG}"
  echo "Notes: ${NOTES}"
  echo "Manifest: ${MANIFEST}"
  exit 0
fi

assets=()
while IFS= read -r file; do
  assets+=("${file}")
done < <(find "${ASSET_DIR}" -maxdepth 1 -type f | sort)

gh release create "${TAG}" \
  --draft \
  --title "${TAG}" \
  --notes-file "${NOTES}" \
  "${assets[@]}"

echo "Draft GitHub release created: ${TAG}"
