#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Gmail Рассылка"
DMG_PATH="${1:-dist/${APP_NAME}.dmg}"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/outreach_dmg_smoke.XXXXXX")"
MOUNT_DIR="${TEMP_ROOT}/mounted"
INSTALL_DIR="${TEMP_ROOT}/Applications"
APP_DATA_DIR="${TEMP_ROOT}/Application Support/${APP_NAME}"
MOUNTED=0

cleanup() {
  if [ "${MOUNTED}" -eq 1 ]; then
    hdiutil detach "${MOUNT_DIR}" -quiet || true
  fi
  if [ "${OUTREACH_KEEP_SMOKE_DATA:-0}" != "1" ]; then
    rm -rf "${TEMP_ROOT}"
  else
    echo "Smoke data kept: ${TEMP_ROOT}"
  fi
}
trap cleanup EXIT

if [ ! -f "${DMG_PATH}" ]; then
  echo "DMG not found: ${DMG_PATH}"
  echo "Run first: ./scripts/build_dmg.sh"
  exit 1
fi

mkdir -p "${MOUNT_DIR}" "${INSTALL_DIR}"

if ! hdiutil attach "${DMG_PATH}" -nobrowse -readonly -mountpoint "${MOUNT_DIR}" -quiet; then
  echo "Unable to mount DMG. On macOS this can require disk image permissions outside a sandbox."
  exit 1
fi
MOUNTED=1

if [ ! -d "${MOUNT_DIR}/${APP_NAME}.app" ]; then
  echo "App bundle not found inside DMG: ${MOUNT_DIR}/${APP_NAME}.app"
  exit 1
fi

cp -R "${MOUNT_DIR}/${APP_NAME}.app" "${INSTALL_DIR}/"
APP_BIN="${INSTALL_DIR}/${APP_NAME}.app/Contents/MacOS/${APP_NAME}"
if [ ! -x "${APP_BIN}" ]; then
  echo "Copied app binary missing or not executable: ${APP_BIN}"
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
    echo "Missing app data directory after DMG smoke: ${APP_DATA_DIR}/${dir}"
    exit 1
  fi
done

echo "DMG smoke passed."
echo "DMG: ${DMG_PATH}"
