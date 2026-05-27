#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHERS_DIR="${PROJECT_DIR}/launchers"
APP_NAME="Gmail Рассылка Launcher"
APP_PATH="${LAUNCHERS_DIR}/${APP_NAME}.app"
ICON_PATH="${PROJECT_DIR}/resources/icons/app_icon.icns"
COMMAND_LAUNCHER="${LAUNCHERS_DIR}/Gmail Рассылка.command"
EXECUTABLE_NAME="launcher"

mkdir -p "${LAUNCHERS_DIR}"

if [ ! -x "${COMMAND_LAUNCHER}" ]; then
  echo "Command launcher is missing. Creating it first."
  "${PROJECT_DIR}/scripts/create_launcher.sh"
fi

rm -rf "${APP_PATH}"
mkdir -p "${APP_PATH}/Contents/MacOS" "${APP_PATH}/Contents/Resources"

cat > "${APP_PATH}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>ru</string>
  <key>CFBundleDisplayName</key>
  <string>Gmail Рассылка Launcher</string>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleIconFile</key>
  <string>app_icon</string>
  <key>CFBundleIdentifier</key>
  <string>local.outreach-automation.launcher</string>
  <key>CFBundleName</key>
  <string>Gmail Рассылка Launcher</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
</dict>
</plist>
PLIST

cat > "${APP_PATH}/Contents/MacOS/${EXECUTABLE_NAME}" <<'EOF'
#!/usr/bin/env bash
set -u

APP_BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
LAUNCHERS_DIR="$(cd "${APP_BUNDLE}/.." && pwd)"
PROJECT_DIR="$(cd "${LAUNCHERS_DIR}/.." && pwd)"
COMMAND_LAUNCHER="${PROJECT_DIR}/launchers/Gmail Рассылка.command"

show_dialog() {
  local message="$1"
  OUTREACH_LAUNCHER_ERROR="${message}" osascript <<'APPLESCRIPT' >/dev/null 2>&1 || true
set messageText to system attribute "OUTREACH_LAUNCHER_ERROR"
display dialog messageText buttons {"OK"} default button "OK" with icon caution
APPLESCRIPT
}

if [ ! -x "${COMMAND_LAUNCHER}" ]; then
  show_dialog "Launcher command не найден. Запустите scripts/create_launcher.sh"
  exit 1
fi

OUTPUT="$("${COMMAND_LAUNCHER}" 2>&1)"
STATUS=$?
if [ "${STATUS}" -ne 0 ]; then
  show_dialog "Не удалось запустить Gmail Рассылка.\n\n${OUTPUT}"
  exit "${STATUS}"
fi
EOF

chmod +x "${APP_PATH}/Contents/MacOS/${EXECUTABLE_NAME}"

if [ -f "${ICON_PATH}" ]; then
  cp "${ICON_PATH}" "${APP_PATH}/Contents/Resources/app_icon.icns"
fi

echo "macOS launcher app created:"
echo "  ${APP_PATH}"
