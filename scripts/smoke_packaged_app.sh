#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Gmail Рассылка"
APP_PATH="dist/${APP_NAME}.app"
APP_BIN="${APP_PATH}/Contents/MacOS/${APP_NAME}"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/outreach_packaged_smoke.XXXXXX")"
APP_DATA_DIR="${TEMP_ROOT}/Application Support/${APP_NAME}"

cleanup() {
  if [ "${OUTREACH_KEEP_SMOKE_DATA:-0}" != "1" ]; then
    rm -rf "${TEMP_ROOT}"
  else
    echo "Smoke data kept: ${TEMP_ROOT}"
  fi
}
trap cleanup EXIT

if [ ! -x "${APP_BIN}" ]; then
  echo "Packaged app binary not found: ${APP_BIN}"
  echo "Run first: ./scripts/build_macos.sh"
  exit 1
fi

if [ -z "${QT_QPA_PLATFORM:-}" ] && [ "${OUTREACH_AUTOMATION_VISIBLE_SMOKE:-0}" != "1" ]; then
  export QT_QPA_PLATFORM=offscreen
fi

export OUTREACH_AUTOMATION_APP_DIR="${APP_DATA_DIR}"
export OUTREACH_AUTOMATION_SMOKE_EXIT_MS="${OUTREACH_AUTOMATION_SMOKE_EXIT_MS:-1000}"

"${APP_BIN}"

for dir in data exports imports logs backups; do
  if [ ! -d "${APP_DATA_DIR}/${dir}" ]; then
    echo "Missing app data directory after smoke: ${APP_DATA_DIR}/${dir}"
    exit 1
  fi
done

echo "Packaged app smoke passed."
echo "App data dir: ${APP_DATA_DIR}"
