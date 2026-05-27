#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo ".venv is missing."
  echo "Run setup first: ./scripts/setup_mac.sh"
  exit 1
fi

source .venv/bin/activate

PLUGIN_PATH="$(python - <<'PY'
from PySide6.QtCore import QLibraryInfo

library_path = getattr(QLibraryInfo, "LibraryPath", QLibraryInfo)
plugins_key = getattr(library_path, "PluginsPath", None)
if plugins_key is None:
    plugins_key = getattr(QLibraryInfo, "PluginsPath")
print(QLibraryInfo.path(plugins_key))
PY
)"

export QT_PLUGIN_PATH="$PLUGIN_PATH"
export QT_QPA_PLATFORM_PLUGIN_PATH="$PLUGIN_PATH/platforms"
export QT_QPA_PLATFORM=offscreen

prepare_qt_plugin_path() {
  local source_path="$1"
  local cache_root="${TMPDIR:-/tmp}/outreach_automation_qt_plugins"
  local safe_path="$cache_root/plugins"

  mkdir -p "$cache_root"
  rm -rf "$safe_path"
  mkdir -p "$safe_path"
  cp -R "$source_path"/. "$safe_path"/
  printf '%s\n' "$safe_path"
}

EFFECTIVE_PLUGIN_PATH="$(prepare_qt_plugin_path "$PLUGIN_PATH")"
export QT_PLUGIN_PATH="$EFFECTIVE_PLUGIN_PATH"
export QT_QPA_PLATFORM_PLUGIN_PATH="$EFFECTIVE_PLUGIN_PATH/platforms"

python scripts/qt_doctor.py
python -m pytest tests -q
python -m compileall -q -x '(^|/)(\.venv|\.pytest_cache|__pycache__|build|dist)(/|$)' .
