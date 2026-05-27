#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Gmail Рассылка"
APP_PATH="dist/${APP_NAME}.app"
DMG_ROOT="dist/dmg-root"
CLEAN=1
VERSIONED=0
PYTHON_BIN="python3"

for arg in "$@"; do
  case "$arg" in
    --no-clean)
      CLEAN=0
      ;;
    --clean)
      CLEAN=1
      ;;
    --versioned)
      VERSIONED=1
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./scripts/build_dmg.sh [--clean|--no-clean] [--versioned]"
      exit 2
      ;;
  esac
done

if [ ! -d "${APP_PATH}" ]; then
  echo "App bundle not found: ${APP_PATH}"
  echo "Run first: ./scripts/build_macos.sh"
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

APP_VERSION="$("${PYTHON_BIN}" - <<'PY'
from src.app_metadata import APP_VERSION
print(APP_VERSION)
PY
)"

if [ "${VERSIONED}" -eq 1 ]; then
  DMG_PATH="dist/${APP_NAME}-${APP_VERSION}.dmg"
else
  DMG_PATH="dist/${APP_NAME}.dmg"
fi

APP_BIN="${APP_PATH}/Contents/MacOS/${APP_NAME}"
if [ ! -x "${APP_BIN}" ]; then
  echo "App binary missing or not executable: ${APP_BIN}"
  exit 1
fi

COCOA_PLUGIN="$(find "${APP_PATH}" -path '*/platforms/libqcocoa.dylib' -type f | head -n 1)"
if [ -z "${COCOA_PLUGIN}" ]; then
  echo "Qt cocoa platform plugin missing in app bundle."
  exit 1
fi

if [ ! -f "${APP_PATH}/Contents/Resources/app_icon.icns" ]; then
  echo "Packaged app icon missing."
  exit 1
fi

if [ "${CLEAN}" -eq 1 ]; then
  rm -rf "${DMG_ROOT}" "${DMG_PATH}"
fi
mkdir -p "${DMG_ROOT}"
cp -R "${APP_PATH}" "${DMG_ROOT}/"
ln -s /Applications "${DMG_ROOT}/Applications"

hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${DMG_ROOT}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

rm -rf "${DMG_ROOT}"

./scripts/notarize_macos.sh "${DMG_PATH}"

echo "DMG created: ${DMG_PATH}"
echo "App size: $(du -sh "${APP_PATH}" | awk '{print $1}')"
echo "DMG size: $(du -sh "${DMG_PATH}" | awk '{print $1}')"
echo "App version: ${APP_VERSION}"
