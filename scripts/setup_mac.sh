#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN=""
CREATE_VENV_COMMAND=()
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.12)"
  CREATE_VENV_COMMAND=("$PYTHON_BIN" -m venv .venv)
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
  CREATE_VENV_COMMAND=("$PYTHON_BIN" -m venv .venv)
elif command -v uv >/dev/null 2>&1 && uv python find 3.12 >/dev/null 2>&1; then
  PYTHON_BIN="$(uv python find 3.12)"
  CREATE_VENV_COMMAND=(uv venv --seed --python "$PYTHON_BIN" .venv)
elif command -v uv >/dev/null 2>&1 && uv python find 3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(uv python find 3.11)"
  CREATE_VENV_COMMAND=(uv venv --seed --python "$PYTHON_BIN" .venv)
else
  echo "Python 3.11 or 3.12 is required."
  echo "Install one with Homebrew, for example: brew install python@3.12"
  echo "If you use uv, run: uv python install 3.12"
  exit 1
fi

echo "Using Python: $PYTHON_BIN"
"${CREATE_VENV_COMMAND[@]}"

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

COCOA_PLUGIN="$(python - <<'PY'
from pathlib import Path

try:
    from PySide6.QtCore import QLibraryInfo
except Exception:
    print("")
    raise SystemExit

library_path = getattr(QLibraryInfo, "LibraryPath", QLibraryInfo)
plugins_key = getattr(library_path, "PluginsPath", None)
if plugins_key is None:
    plugins_key = getattr(QLibraryInfo, "PluginsPath")
print(Path(QLibraryInfo.path(plugins_key)) / "platforms" / "libqcocoa.dylib")
PY
)"

if [ ! -f "$COCOA_PLUGIN" ]; then
  echo "PySide6 cocoa plugin is missing; reinstalling compatible PySide6."
  python -m pip install --force-reinstall 'PySide6>=6.7,<6.10'
fi

python scripts/qt_doctor.py

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists; leaving it unchanged"
fi

echo
echo "Setup complete."
echo "Next steps:"
echo "1. Add GMAIL_APP_PASSWORD to .env if you want to check Gmail login or send a single test email."
echo "2. Start the app with: ./scripts/run_mac.sh"
echo "3. Run checks with: ./scripts/test_mac.sh"
