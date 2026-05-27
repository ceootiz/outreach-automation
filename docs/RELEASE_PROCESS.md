# Release Process

This project ships as a controlled desktop outreach operator platform. Releases must
never include secrets, runtime databases, logs, exports, imports, cached inbox data or
credential files.

## Release Safety Rules

- Do not commit `.env`, `.venv`, SQLite files, logs, exports, imports, caches or
  local credential files.
- Do not publish Gmail App Passwords, OpenAI keys, Telegram tokens or any other API
  keys.
- Do not run real sends as part of release packaging.
- Keep live connector verification separate and controlled with owned test targets.
- Use draft GitHub releases first.
- Confirm the GitHub remote before uploading assets.

## macOS Build

```bash
cd outreach_automation
./scripts/test_mac.sh
./scripts/check_no_secrets.sh
python scripts/ui_clickability_doctor.py
./scripts/build_macos.sh
./scripts/build_dmg.sh --versioned
./scripts/smoke_packaged_app.sh
./scripts/smoke_dmg.sh "dist/Gmail Рассылка-<version>.dmg"
```

Expected release artifact:

```text
dist/Gmail Рассылка-<version>.dmg
dist/Gmail Рассылка-<version>.dmg.sha256
```

Signing and notarization are optional and depend on Apple Developer ID credentials.
The packaging scripts skip notarization unless the required environment variables are
set.

## Windows Build

Run on Windows PowerShell:

```powershell
cd outreach_automation
.\scripts\windows\setup_windows.ps1
.\scripts\windows\test_windows.ps1
.\scripts\windows\build_windows.ps1
.\scripts\windows\package_windows.ps1
.\scripts\windows\smoke_windows.ps1
```

Expected release artifact:

```text
dist\windows\Gmail Рассылка-<version>-windows.zip
dist\windows\Gmail Рассылка-<version>-windows.zip.sha256
```

The Windows ZIP must include the executable, launchers and install docs. It must not
include `.env`, runtime SQLite files, logs, exports, imports, caches or personal data.

## Prepare Release Assets

On macOS:

```bash
./scripts/release/prepare_release.sh
```

On Windows:

```powershell
.\scripts\release\prepare_release.ps1
```

These scripts run safe checks, create checksums, generate `dist/release_manifest.json`
and collect existing assets into:

```text
dist/release-assets/v<version>/
```

If one platform artifact is missing because the script is running on the other OS,
the manifest records that platform as missing/skipped. Run the validator again after
both artifacts are present for a full cross-platform release manifest.

## Manifest Validation

```bash
python scripts/release/validate_release.py \
  --version <version> \
  --smoke-status passed \
  --asset-dir "dist/release-assets/v<version>"
```

The manifest contains:

- app version and build timestamp;
- macOS and Windows artifacts;
- SHA256 checksums;
- supported platform status;
- smoke/test status fields;
- safety flags: no autosend, no unsafe automation, runtime data excluded.

## GitHub Release Flow

The scripts support draft releases through the GitHub CLI, but do not upload by
default.

The release target must be the outreach repository:

```text
https://github.com/ceootiz/outreach-automation.git
```

The release scripts run `scripts/release/verify_git_remote.py` before any GitHub
release preparation or upload. The guard blocks the old `Purchase-Updater` remote
and any repo name outside the approved outreach repository list.

If the repository does not exist yet, create it first:

```bash
gh repo create ceootiz/outreach-automation --private --source . --remote origin --push
```

If the repository exists and this checkout is safe to point at it:

```bash
git remote set-url origin https://github.com/ceootiz/outreach-automation.git
git remote -v
python scripts/release/verify_git_remote.py
git push -u origin release/5.1.1-outreach-automation
```

Do not push if the git root contains unrelated projects that should not be part of
the outreach repository. In that case, create a clean outreach-only checkout first.

Dry run:

```bash
./scripts/release/github_release.sh
```

Create draft release after confirming the remote and assets:

```bash
./scripts/release/github_release.sh --create-draft
```

Draft creation requires both macOS and Windows artifacts by default. Use
`--allow-partial` only for an internal partial release preparation pass.

PowerShell equivalent:

```powershell
.\scripts\release\github_release.ps1
.\scripts\release\github_release.ps1 -CreateDraft
```

Before creating a draft release:

```bash
git remote -v
git status --short
python scripts/release/verify_git_remote.py
```

Do not upload if the remote points to the wrong repository.

## Release Checklist

- [ ] `git status --short` has no secrets/runtime files staged.
- [ ] `./scripts/test_mac.sh` passes.
- [ ] `./scripts/check_no_secrets.sh` passes.
- [ ] UI doctor passes for dev and packaged app.
- [ ] macOS DMG is built and smoked.
- [ ] Windows ZIP is built and smoked on Windows.
- [ ] SHA256 files exist for all published artifacts.
- [ ] `dist/release_manifest.json` exists.
- [ ] Release notes exist for the version.
- [ ] GitHub remote is confirmed.
- [ ] Release is created as draft first.
