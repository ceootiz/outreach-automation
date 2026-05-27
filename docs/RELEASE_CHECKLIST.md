# Stage 1 Release Checklist

Use this checklist before publishing a Stage 1 release candidate.

## Required Automated Checks

- [ ] Run test suite:
  ```bash
  ./scripts/test_mac.sh
  ```
- [ ] Run no-secrets audit:
  ```bash
  ./scripts/check_no_secrets.sh
  ```
- [ ] Build `.app`:
  ```bash
  ./scripts/build_macos.sh
  ```
- [ ] Build versioned DMG:
  ```bash
  ./scripts/build_dmg.sh --versioned
  ```
- [ ] Run packaged app smoke:
  ```bash
  ./scripts/smoke_packaged_app.sh
  ```
- [ ] Run DMG smoke:
  ```bash
  ./scripts/smoke_dmg.sh "dist/Gmail Рассылка-<version>.dmg"
  ```
- [ ] Or run the full release smoke:
  ```bash
  ./scripts/release_smoke.sh
  ```

## Fresh Install Flow

- [ ] Mount the DMG.
- [ ] Confirm `Gmail Рассылка.app` exists in the DMG.
- [ ] Confirm the `/Applications` shortcut exists.
- [ ] Copy the app to a clean location.
- [ ] Launch without project-local `data/`, `exports/`, `imports/`, or `logs`.
- [ ] Confirm app data is created under `~/Library/Application Support/Gmail Рассылка/`.
- [ ] Confirm the app starts without a Python traceback.

## First Launch / Onboarding

- [ ] On fresh app data, onboarding appears.
- [ ] Onboarding explains Gmail App Password and test mode.
- [ ] Completing onboarding stores `onboarding_completed=true`.
- [ ] Next launch does not show onboarding again.

## No-Secrets Audit

- [ ] `.env` is not tracked.
- [ ] `.venv` is not tracked.
- [ ] Runtime SQLite files are not staged or tracked.
- [ ] `exports/`, `logs/`, and personal `imports/` are not staged or tracked.
- [ ] No Gmail app password value appears in tracked files.
- [ ] No API keys, private keys, or obvious tokens appear in tracked files.

## Gmail Checks

- [ ] Gmail dry-check pending for release owner environment.
- [ ] One-recipient live Gmail test pending for owned inbox.
- [ ] Live test must use:
  - `send_mode=live`
  - `safe_mode=true`
  - `allowed_test_recipient=<owned inbox>`
  - `daily_send_limit=1`
  - explicit operator confirmation

## Signing / Notarization Status

- [ ] Developer ID signing skipped unless `DEVELOPER_ID_APP` is set.
- [ ] Notarization skipped unless `NOTARY_APPLE_ID`, `NOTARY_TEAM_ID`, and `NOTARY_KEYCHAIN_PROFILE` are set.
- [ ] If signing env vars are present, verify:
  ```bash
  codesign --verify --deep --strict --verbose=2 "dist/Gmail Рассылка.app"
  ```
- [ ] If notarization env vars are present, verify:
  ```bash
  spctl --assess --type open --verbose=4 "dist/Gmail Рассылка-<version>.dmg"
  ```

## Final Manual UI QA

- [ ] Main window opens on macOS.
- [ ] Sidebar and main workflow are readable.
- [ ] Add row works.
- [ ] Paste recipients works.
- [ ] Import XLSX/CSV works.
- [ ] Generate messages works in queue.
- [ ] Approve selected works.
- [ ] Dry-run send works and does not send SMTP.
- [ ] Export report works.
- [ ] Settings persist after restart.
- [ ] Logs tab opens without traceback.
- [ ] Queue controls do not freeze UI.

## Release Decision

- [ ] All automated checks passed.
- [ ] Known limitations are documented.
- [ ] Release artifact path recorded.
- [ ] Commit hash recorded.
