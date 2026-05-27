#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Gmail Рассылка"
APP_PATH="dist/${APP_NAME}.app"
APP_BIN="${APP_PATH}/Contents/MacOS/${APP_NAME}"
ICON_PATH="resources/icons/app_icon.icns"
CLEAN=1

for arg in "$@"; do
  case "$arg" in
    --no-clean)
      CLEAN=0
      ;;
    --clean)
      CLEAN=1
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./scripts/build_macos.sh [--clean|--no-clean]"
      exit 2
      ;;
  esac
done

if [ ! -d .venv ]; then
  echo ".venv is missing. Run: ./scripts/setup_mac.sh"
  exit 1
fi

source .venv/bin/activate

export PYINSTALLER_CONFIG_DIR="${TMPDIR:-/tmp}/outreach_automation_pyinstaller"
mkdir -p "${PYINSTALLER_CONFIG_DIR}"

python scripts/generate_app_icon.py >/dev/null

APP_VERSION="$(python - <<'PY'
from src.app_metadata import APP_VERSION
print(APP_VERSION)
PY
)"

if ! python -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller is not installed in .venv."
  echo "Run: python -m pip install -r requirements.txt"
  exit 2
fi

if [ ! -f "${ICON_PATH}" ]; then
  echo "Icon missing: ${ICON_PATH}"
  exit 1
fi

if [ "${CLEAN}" -eq 1 ]; then
  rm -rf build "dist/${APP_NAME}" "${APP_PATH}"
fi

clean_bundle_metadata() {
  local clean_path="dist/${APP_NAME}.clean.app"
  rm -rf "${clean_path}"
  ditto --norsrc --noextattr "${APP_PATH}" "${clean_path}"
  rm -rf "${APP_PATH}"
  mv "${clean_path}" "${APP_PATH}"
  if command -v dot_clean >/dev/null 2>&1; then
    dot_clean -m "${APP_PATH}" || true
  fi
  if command -v xattr >/dev/null 2>&1; then
    xattr -cr "${APP_PATH}" || true
  fi
}

# Keep the bundle lean: this app uses only QtCore/QtGui/QtWidgets.
# Avoid broad PySide6 collection because it pulls Designer, Assistant, docs,
# QML, WebEngine, multimedia, 3D, and many unused Qt plugins.
PYINSTALLER_EXCLUDES=(
  PySide6.Qt3DAnimation
  PySide6.Qt3DCore
  PySide6.Qt3DExtras
  PySide6.Qt3DInput
  PySide6.Qt3DLogic
  PySide6.Qt3DRender
  PySide6.QtBluetooth
  PySide6.QtCharts
  PySide6.QtDataVisualization
  PySide6.QtDesigner
  PySide6.QtGraphs
  PySide6.QtHelp
  PySide6.QtHttpServer
  PySide6.QtLocation
  PySide6.QtMultimedia
  PySide6.QtMultimediaWidgets
  PySide6.QtNfc
  PySide6.QtPdf
  PySide6.QtPdfWidgets
  PySide6.QtPositioning
  PySide6.QtQml
  PySide6.QtQuick
  PySide6.QtQuick3D
  PySide6.QtQuickControls2
  PySide6.QtQuickWidgets
  PySide6.QtRemoteObjects
  PySide6.QtScxml
  PySide6.QtSensors
  PySide6.QtSerialBus
  PySide6.QtSerialPort
  PySide6.QtSpatialAudio
  PySide6.QtSql
  PySide6.QtSvg
  PySide6.QtSvgWidgets
  PySide6.QtTextToSpeech
  PySide6.QtUiTools
  PySide6.QtWebChannel
  PySide6.QtWebEngineCore
  PySide6.QtWebEngineQuick
  PySide6.QtWebEngineWidgets
  PySide6.QtWebSockets
  PySide6.QtWebView
  PySide6.scripts
)

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --name "${APP_NAME}"
  --icon "${ICON_PATH}"
  --add-data "resources/icons/app_icon.png:resources/icons"
  --hidden-import PySide6.QtCore
  --hidden-import PySide6.QtGui
  --hidden-import PySide6.QtTest
  --hidden-import PySide6.QtWidgets
)

if [ "${CLEAN}" -eq 1 ]; then
  PYINSTALLER_ARGS+=(--clean)
fi

for module in "${PYINSTALLER_EXCLUDES[@]}"; do
  PYINSTALLER_ARGS+=(--exclude-module "${module}")
done

python -m PyInstaller "${PYINSTALLER_ARGS[@]}" app.py

if [ ! -d "${APP_PATH}" ]; then
  echo "Build failed: ${APP_PATH} was not created."
  exit 1
fi

if [ ! -x "${APP_BIN}" ]; then
  echo "Build failed: app binary missing or not executable: ${APP_BIN}"
  exit 1
fi

COCOA_PLUGIN="$(find "${APP_PATH}" -path '*/platforms/libqcocoa.dylib' -type f | head -n 1)"
if [ -z "${COCOA_PLUGIN}" ]; then
  echo "Build failed: Qt cocoa platform plugin was not packaged."
  exit 1
fi

if [ ! -f "${APP_PATH}/Contents/Resources/app_icon.icns" ]; then
  echo "Build failed: packaged app icon missing."
  exit 1
fi

if [ ! -f "${APP_PATH}/Contents/Resources/resources/icons/app_icon.png" ]; then
  echo "Build failed: runtime icon resource missing."
  exit 1
fi

clean_bundle_metadata

./scripts/sign_macos.sh "${APP_PATH}"

echo "Build created: ${APP_PATH}"
echo "App version: ${APP_VERSION}"
echo "Qt cocoa plugin: ${COCOA_PLUGIN}"
echo "App size: $(du -sh "${APP_PATH}" | awk '{print $1}')"
