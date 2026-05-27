# v5.1.1 Release Notes

`v5.1.1` prepares the project for safe GitHub release distribution across macOS and
Windows. It does not add hidden sending, unsafe social automation or autosend behavior.

## Highlights

- GitHub release workflow for draft-first distribution.
- macOS and Windows release asset validation.
- SHA256 checksum generation for published packages.
- Release manifest generation at `dist/release_manifest.json`.
- Release asset collection under `dist/release-assets/v5.1.1/`.
- Windows package flow remains Windows-native and produces a portable ZIP.
- macOS package flow remains DMG-based.

## Platform Features Included

- AI dual brain: Research Brain plus Writer Brain for structured draft generation.
- Inbox intelligence: unified inbox, conversation timelines and manual reply analysis.
- Web enrichment: public-only enrichment with cache and source basis.
- Outreach sessions: high-throughput, keyboard-first manual operator flow.
- High Volume mode: operator-assisted conveyor workflow without hidden automation.
- Operator workflow: presets, guided launch flow, health checks and smart warnings.
- Windows support: app-data paths, Credential Manager support, launchers and ZIP packaging.
- Telegram support: official Bot API integration and polling with safe-mode controls.

## Install

macOS:

```text
Gmail Рассылка-5.1.1.dmg
```

Windows:

```text
Gmail Рассылка-5.1.1-windows.zip
```

Windows users should unzip the package and double-click `Gmail Рассылка.exe`.

## Safety Philosophy

- AI only prepares drafts and suggestions.
- Human review is required before sending.
- No autosend.
- No CAPTCHA bypass.
- No stealth browser automation.
- No fake account orchestration.
- No recipient rewriting.
- No secrets in release artifacts.

## Known Limitations

- Windows builds must be produced on Windows.
- macOS notarization requires Apple Developer credentials.
- GitHub upload is intentionally draft-first and requires explicit `--create-draft`.
- Real connector verification still requires owned test accounts and safe-mode limits.
