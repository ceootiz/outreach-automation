# macOS Signing And Notarization Checklist

This project can build a local `.app` and `.dmg` without Apple credentials. That build is useful for local testing, but it is only ad-hoc signed by PyInstaller/macOS tooling and is not ready for public distribution through Gatekeeper.

## Current State

- `./scripts/build_macos.sh` creates `dist/Gmail Рассылка.app`.
- `./scripts/build_dmg.sh` creates `dist/Gmail Рассылка.dmg` or `dist/Gmail Рассылка-<version>.dmg`.
- The app bundle is suitable for local QA.
- The app is not notarized yet.
- PyInstaller can emit a local ad-hoc signing warning on some macOS file systems because bundled Qt frameworks carry Finder metadata. The build script still validates launch behavior through smoke tests. Developer ID release signing must be verified with the commands below.

## Requirements For Distribution

You need:

- Apple Developer Program membership.
- A `Developer ID Application` certificate installed in Keychain.
- An App Store Connect API key or Apple ID notary credentials configured for `notarytool`.
- A clean release machine or CI runner that does not expose `.env`, Gmail app passwords, SQLite runtime data, logs, or exports.

Never store notarization credentials, Gmail secrets, `.env`, runtime SQLite files, logs, or exports in git.

## Sign The App

Replace `Developer ID Application: Your Name (TEAMID)` with the actual identity:

```bash
codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  "dist/Gmail Рассылка.app"
```

Validate the signature:

```bash
codesign --verify --deep --strict --verbose=2 "dist/Gmail Рассылка.app"
codesign -dv --verbose=4 "dist/Gmail Рассылка.app"
```

## Build And Sign The DMG

Build the DMG:

```bash
./scripts/build_dmg.sh --versioned
```

Optionally sign the DMG:

```bash
codesign \
  --force \
  --timestamp \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  "dist/Gmail Рассылка-5.1.1.dmg"
```

## Notarize

Submit the DMG:

```bash
xcrun notarytool submit "dist/Gmail Рассылка-5.1.1.dmg" \
  --keychain-profile "notarytool-profile-name" \
  --wait
```

Staple the notarization ticket:

```bash
xcrun stapler staple "dist/Gmail Рассылка-5.1.1.dmg"
```

## Gatekeeper Verification

Check the app:

```bash
spctl --assess --type execute --verbose=4 "dist/Gmail Рассылка.app"
```

Check the DMG:

```bash
spctl --assess --type open --verbose=4 "dist/Gmail Рассылка-5.1.1.dmg"
```

Run the packaged smoke checks:

```bash
./scripts/smoke_packaged_app.sh
./scripts/smoke_dmg.sh "dist/Gmail Рассылка-5.1.1.dmg"
```

## What Is Not Automated Yet

- Developer ID signing is not automated because it requires a private certificate.
- Notarization is not automated because it requires Apple credentials.
- Hardened runtime entitlements have not been customized; add an entitlements file only when a concrete capability requires it.
