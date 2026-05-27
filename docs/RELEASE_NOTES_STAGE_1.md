# Gmail Рассылка — Stage 1 Release Notes

## What Stage 1 Supports

- Local macOS desktop app built with Python and PySide6.
- Russian Apple-like UI for a simple email workflow.
- Recipient table where each row is one email with its own subject and message.
- Manual row editing, clipboard paste, and XLSX/CSV import.
- Flexible Russian/English import headers for email, subject, message, name, company, and note.
- Template fallback for rows without individual text.
- Queue-based message preparation, dry-run send, live send, and report export.
- Background worker so long operations do not block the UI.
- SQLite local storage.
- Gmail SMTP configuration check.
- Multiple saved Gmail sender profiles with one active profile for sending.
- Export reports to XLSX.
- Blacklist, daily limit, safe mode, allowed test recipient, and live-send confirmation.
- macOS `.app` and DMG packaging scripts.
- First-launch onboarding.
- Production user data directories under `~/Library/Application Support/Gmail Рассылка/`.
- Database backups and corruption recovery guard.

## Safety Guardrails

- Version `1.10.0` fixes recipient routing safety. Live Gmail send validates
  that SMTP receives the contact row email as the envelope recipient.
  `allowed_test_recipient` only allows or blocks and never rewrites recipients.
  The rebuilt app keeps the latest UI/clickability/credential fixes.
- Version `1.10.0` also adds multiple Gmail profiles. Profile names/emails/status
  live in SQLite; App Password values remain in secure credential storage and
  are never exported.
- Version `2.0.0` adds AI Assist as a separate draft-only mode. AI-generated
  drafts always require human review and never send or approve email
  automatically.
- Version `3.1.1` verifies the AI Assist UX with stronger prompt guardrails,
  AI draft review indicators, and no-autosend regression tests.
- Version `3.2.0` adds campaign intelligence: timeline, manual reply tracking,
  AI quality scoring, AI reply suggestions, analytics, presets and reminder-only
  follow-ups. No auto-send behavior is added.
- Version `3.3.0` adds unified inbox, conversation threads, lead pipeline,
  AI conversation summaries, reply suggestions and follow-up intelligence.
  Replies remain manual and AI never auto-sends.
- Version `3.4.0` adds read-only Email IMAP sync and Telegram getUpdates
  ingestion with checkpoints, duplicate protection and AI summary queues.
  Sync never sends replies and never mutates the remote mailbox.
- Version `3.5.0` adds a production verification phase for Gmail SMTP/IMAP,
  Telegram Bot API/polling, AI Assist, unified inbox ingestion and safe-mode
  protections. Live checks stay limited to controlled owned targets.
- Version `3.6.0` adds Dual AI Brain generation: Research Brain builds a
  structured recipient brief from row data only, then Writer Brain creates a
  channel-aware draft for human review. Research and Writer API keys are stored
  separately in secure credential storage and never in SQLite.
- Version `3.7.0` adds public-only Web Enrichment for Research Brain with
  robots-aware GET fetches, conservative caching, source_basis, warnings and
  no login/private scraping.
- Version `3.8.0` adds Channel Execution Framework with explicit capability
  matrix, risk labels, Official API vs Manual Assist modes and no hidden
  automation for restricted social channels.
- Version `3.9.0` adds Operator Workflow System with campaign presets,
  New Campaign Wizard, launch checklist, health score, quick starts and smart
  warnings so operators understand the next safe step.
- Version `4.0.0` adds real-world readiness QA and hardening: queue recovery
  after interrupted running jobs, controlled live-check criteria, malformed AI
  failure coverage, IMAP idempotency and Manual Assist operational QA.
- Version `4.6.0` adds High Volume Operator Mode with a keyboard-first
  Outreach Session, priority-ranked lead review, manual-assist conveyor flow,
  session recovery, AI feedback and explicit no-hidden-automation guardrails.
- Version `4.7.0` polishes operator throughput with synthetic 100-lead QA,
  local latency benchmark, smart batching, quick filters, safer hotkeys,
  unsaved draft recovery and faster Manual Assist review.
- Version `4.8.0` completes a safe social full-ready audit for Instagram,
  TikTok, X and VK: Manual Assist full flow, channel readiness matrix,
  global history search, social QA data, social benchmark and clearer
  human labels for channel limitations.
- Version `4.9.0` finalizes social operator workflows with connector slots,
  channel cockpits, Focus Mode, profile URL engine, per-channel exports,
  recent/fuzzy search and smart channel recommendations.
- Version `5.0.0` adds the Production Operator Platform: command palette,
  Quick Review 2.0, notification center, background task monitor, performance
  cache/metrics, chunked imports, paginated contacts and a local benchmark
  suite. It remains manual-confirmed and does not add autosend.
- Version `5.1.1` adds Windows port packaging: Windows app-data paths,
  Credential Manager priority, `.bat`/PowerShell launchers, PyInstaller
  Windows spec, portable ZIP scripts, smoke scripts and a non-technical
  Windows install guide. It also adds the draft-first GitHub release workflow,
  release manifest generation and SHA256 checksums.
- `send_mode=dry_run` is the default.
- Dry-run send does not call SMTP and does not send real email.
- Live send requires explicit confirmation when configured.
- Safe mode can restrict live sends to one allowed test recipient.
- Daily send limit is enforced.
- Blacklisted recipients are blocked before send.
- Gmail App Password can be saved from the app UI into secure local storage.
- `.env` remains available only as a development fallback.
- Logs redact password-like values.
- No hidden social-network autosend, tracking pixels, open/click tracking, or autoresponders.

## What Stage 1 Does Not Support

- Stage 1 itself did not include Instagram, X/Twitter, Telegram, WhatsApp, Facebook, or VK.
  Later stages add Email/Telegram official paths and safe Manual Assist for restricted social channels.
- Stage 1 itself did not include AI API integration. Later stages add draft-only AI Assist with human review.
- No open/click tracking.
- No automatic reply processing.
- No full follow-up engine.
- No anti-spam bypassing, captcha handling, identity hiding, fake accounts, or aggressive automation.
- No notarized public macOS distribution yet unless release owner provides Apple Developer credentials.

## Installation

For local development:

```bash
./scripts/setup_mac.sh
./scripts/run_mac.sh
```

For release candidate QA:

```bash
./scripts/release_smoke.sh
```

Build artifacts:

```text
dist/Gmail Рассылка.app
dist/Gmail Рассылка-<version>.dmg
```

## First Launch

On a fresh user data directory, the app shows onboarding:

1. Welcome.
2. What the app does.
3. How Gmail App Password works.
4. Why the first send should be dry-run.

Runtime data is stored outside the project:

```text
~/Library/Application Support/Gmail Рассылка/
  data/
  exports/
  imports/
  logs/
  backups/
```

## Known Limitations

- The current release artifact is suitable for local QA.
- Developer ID signing and notarization require Apple credentials and are opt-in through environment variables.
- DMG Finder layout is intentionally minimal.
- Bundle size is optimized, but still includes PySide6 runtime dependencies.
- Gmail dry-check and one-recipient live test must be performed by the release owner with their own credentials and owned inbox.

## Next Stages

- Developer ID signing and notarization in release CI.
- Final one-recipient live Gmail verification by release owner.
- Optional DMG visual polish.
- Broader manual UI QA on multiple macOS versions and screen sizes.
