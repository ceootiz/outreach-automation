#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

FAILED=0

warn() {
  echo "WARNING: $1"
  FAILED=1
}

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  warn ".env is tracked"
fi

STAGED_RUNTIME="$(git diff --cached --name-only -- data exports logs imports || true)"
if [ -n "${STAGED_RUNTIME}" ]; then
  echo "${STAGED_RUNTIME}" | while IFS= read -r path; do
    [ -n "${path}" ] && echo "WARNING: runtime file staged: ${path}"
  done
  FAILED=1
fi

TRACKED_RUNTIME="$(git ls-files data exports logs imports || true)"
if [ -n "${TRACKED_RUNTIME}" ]; then
  echo "${TRACKED_RUNTIME}" | while IFS= read -r path; do
    [ -n "${path}" ] && echo "WARNING: runtime file tracked: ${path}"
  done
  FAILED=1
fi

TRACKED_FILES="$(mktemp "${TMPDIR:-/tmp}/outreach_tracked_files.XXXXXX")"
trap 'rm -f "${TRACKED_FILES}"' EXIT
git ls-files -z > "${TRACKED_FILES}"

scan_pattern() {
  local label="$1"
  local pattern="$2"
  local matches
  matches="$(xargs -0 grep -IlE "${pattern}" < "${TRACKED_FILES}" 2>/dev/null || true)"
  if [ -n "${matches}" ]; then
    echo "${matches}" | while IFS= read -r path; do
      [ -n "${path}" ] && echo "WARNING: possible ${label} in tracked file: ${path}"
    done
    FAILED=1
  fi
}

# Variable names in docs/code are expected; this catches likely real values.
scan_pattern "Gmail app password value" 'GMAIL_APP_PASSWORD[[:space:]]*=[[:space:]]*[A-Za-z0-9]{12,}'
scan_pattern "Telegram bot token value" 'TELEGRAM_BOT_TOKEN[[:space:]]*=[[:space:]]*[0-9]{6,}:[A-Za-z0-9_-]{20,}'
scan_pattern "OpenAI-style API key" 'sk-[A-Za-z0-9_-]{20,}'
scan_pattern "GitHub token" 'gh[pousr]_[A-Za-z0-9_]{20,}'
scan_pattern "Slack token" 'xox[baprs]-[A-Za-z0-9-]{20,}'
scan_pattern "AWS access key" 'AKIA[0-9A-Z]{16}'
scan_pattern "private key block" 'BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY'

if [ "${FAILED}" -ne 0 ]; then
  echo "No-secrets audit failed. Values are not printed; inspect listed files."
  exit 1
fi

echo "No-secrets audit passed."
