#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Gmail Рассылка"
APP_PATH="${1:-dist/${APP_NAME}.app}"

if [ -z "${DEVELOPER_ID_APP:-}" ]; then
  echo "Skipping Developer ID signing: DEVELOPER_ID_APP is not set"
  exit 0
fi

if [ ! -d "${APP_PATH}" ]; then
  echo "App bundle not found: ${APP_PATH}"
  exit 1
fi

if command -v dot_clean >/dev/null 2>&1; then
  dot_clean -m "${APP_PATH}" || true
fi

if command -v xattr >/dev/null 2>&1; then
  xattr -cr "${APP_PATH}" || true
  find "${APP_PATH}" -name '*.framework' -type d -exec xattr -c {} \; || true
  xattr -c "${APP_PATH}" || true
fi

echo "Signing app bundle with Developer ID identity from environment."
codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --sign "${DEVELOPER_ID_APP}" \
  "${APP_PATH}"

codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
echo "Developer ID signing verified."
