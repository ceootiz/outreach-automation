#!/usr/bin/env bash
set -u

APP_NAME="Gmail Рассылка"
APP_VERSION="5.1.1"
LAUNCHER_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${LAUNCHER_DIR}/.." && pwd)"
APP_PATH="${PROJECT_DIR}/dist/${APP_NAME}.app"
DEV_SCRIPT="${PROJECT_DIR}/scripts/run_mac.sh"
LAUNCH_MODE="${OUTREACH_AUTOMATION_LAUNCH_MODE:-auto}"

pause_on_error() {
  if [ -t 0 ]; then
    echo
    read -r -p "Нажмите Enter, чтобы закрыть окно..." _
  fi
}

fail() {
  echo
  echo "Ошибка: $1"
  echo
  echo "Если проблема повторяется, откройте README.md или запустите scripts/setup_mac.sh."
  pause_on_error
  exit 1
}

warn_old_installed_copies() {
  local found=0
  for old_app in "/Applications/${APP_NAME}.app" "${HOME}/Applications/${APP_NAME}.app"; do
    if [ -d "${old_app}" ]; then
      if [ "${found}" -eq 0 ]; then
        echo "Внимание:"
        echo "Найдена старая установленная копия. Чтобы не открыть старую версию, удалите ее или замените новой из DMG."
        found=1
      fi
      echo "  ${old_app}"
    fi
  done
  if [ "${found}" -eq 1 ]; then
    echo
  fi
}

run_production() {
  if [ ! -d "${APP_PATH}" ]; then
    return 1
  fi

  warn_old_installed_copies
  echo "Запускаю ${APP_NAME} ${APP_VERSION} из dist"
  if ! open "${APP_PATH}"; then
    fail "Не удалось открыть собранное приложение."
  fi
  echo "Приложение запущено."
  return 0
}

run_dev() {
  echo "Запускаю dev-режим."

  if [ ! -x "${DEV_SCRIPT}" ]; then
    fail "Файл запуска dev-режима не найден: scripts/run_mac.sh"
  fi

  if [ ! -d "${PROJECT_DIR}/.venv" ]; then
    fail "Окружение не настроено. Запустите scripts/setup_mac.sh"
  fi

  cd "${PROJECT_DIR}" || fail "Не удалось перейти в папку проекта."
  "${DEV_SCRIPT}"
  status=$?
  if [ "${status}" -ne 0 ]; then
    fail "Dev-режим завершился с ошибкой (${status})."
  fi
}

echo "Gmail Рассылка"
echo "Папка проекта: ${PROJECT_DIR}"
echo

case "${LAUNCH_MODE}" in
  production)
    run_production || fail "Собранное приложение не найдено. Соберите его командой scripts/build_macos.sh"
    ;;
  dev)
    run_dev
    ;;
  auto)
    if ! run_production; then
      echo "Собранное приложение не найдено. Запускаю dev-режим."
      run_dev
    fi
    ;;
  *)
    fail "Неизвестный режим запуска: ${LAUNCH_MODE}. Используйте auto, production или dev."
    ;;
esac
