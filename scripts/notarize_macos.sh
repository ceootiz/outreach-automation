#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Gmail Рассылка"
DMG_PATH="${1:-dist/${APP_NAME}.dmg}"

if [ -z "${NOTARY_APPLE_ID:-}" ] || [ -z "${NOTARY_TEAM_ID:-}" ] || [ -z "${NOTARY_KEYCHAIN_PROFILE:-}" ]; then
  echo "Skipping notarization: NOTARY_APPLE_ID, NOTARY_TEAM_ID, or NOTARY_KEYCHAIN_PROFILE is not set"
  exit 0
fi

if [ ! -f "${DMG_PATH}" ]; then
  echo "DMG not found: ${DMG_PATH}"
  exit 1
fi

echo "Submitting DMG for notarization using keychain profile from environment."
xcrun notarytool submit "${DMG_PATH}" \
  --keychain-profile "${NOTARY_KEYCHAIN_PROFILE}" \
  --wait

xcrun stapler staple "${DMG_PATH}"
spctl --assess --type open --verbose=4 "${DMG_PATH}"
echo "Notarization, stapling, and Gatekeeper verification completed."
