# Stage 1 Complete — Gmail Рассылка

Stage 1 brings the project to a release-candidate desktop app for controlled Gmail outreach. The app is intentionally conservative: it is built for reviewed, rate-limited email sending, not for bulk spam or anti-spam bypass.

## What Is Implemented

- Russian Apple-like PySide6 desktop UI with onboarding-first flow.
- Manual recipient table: each row has its own email, subject, and message.
- Excel/CSV import with flexible Russian and English column names.
- Clipboard paste from Excel/Google Sheets.
- Local SQLite persistence with migrations and production user directories.
- Template engine with deterministic variable substitution.
- Queue-based generate/send/export execution so the UI stays responsive.
- Background worker that survives job errors and keeps processing later jobs.
- Contact state machine for safe transitions.
- Gmail SMTP dry-check without sending email.
- Dry-run send mode by default.
- Live Gmail send only behind operator confirmation and guardrails.
- Blacklist, daily limit, delay between emails, safe mode, and allowed test recipient.
- Export reports with contacts, send logs, queue logs, and errors.
- macOS `.app` and DMG build pipeline.
- Fresh packaged app smoke scripts and release-candidate smoke pipeline.
- Optional signing/notarization hooks that skip gracefully without Apple Developer credentials.

## Architecture

The application is split into small service layers:

- `src/db.py` owns SQLite schema creation and migrations.
- `src/campaign_service.py` coordinates imports, contact edits, generation, send guardrails, exports, and logs.
- `src/queue_service.py` stores and manages jobs.
- `src/background_worker.py` processes queue jobs sequentially in a PySide-safe worker.
- `src/state_machine.py` validates contact status transitions.
- `src/mailer.py` handles Gmail SMTP connection checks and live sends.
- `src/platform_utils.py` resolves production user directories.
- `src/db_safety.py` handles startup integrity checks and backups.
- `src/gui/` contains the Russian desktop UI.

## Guardrails

Stage 1 keeps the following safety constraints:

- `send_mode=dry_run` by default.
- Dry-run never calls SMTP and records `dry_run_send` logs.
- Live send requires explicit confirmation when `real_send_confirm_required=true`.
- `safe_mode=true` remains available and should stay enabled for early tests.
- `allowed_test_recipient` can restrict live sends to one owned inbox.
- Daily limit is enforced from `send_logs`.
- Blacklisted recipients are blocked before sending.
- Multiple Gmail profiles can be saved through the app UI; the active profile is used as sender.
- Gmail App Password values are saved through secure local storage, keyed per profile.
- `.env` is still supported as a development-only fallback when no UI credential is saved.
- Gmail App Password is not stored in SQLite, exported, or intentionally logged.

## Packaging

Stage 1 production readiness includes:

- `dist/Gmail Рассылка.app`
- `dist/Gmail Рассылка-5.1.1.dmg`
- `scripts/build_macos.sh`
- `scripts/build_dmg.sh`
- `scripts/smoke_packaged_app.sh`
- `scripts/smoke_dmg.sh`
- `scripts/release_smoke.sh`
- `scripts/check_no_secrets.sh`

Runtime data is stored outside the project:

```text
~/Library/Application Support/Gmail Рассылка/
  data/
  exports/
  imports/
  logs/
  backups/
```

## Onboarding

On first visible launch, the app shows a short onboarding dialog:

1. Welcome.
2. What the app can do.
3. How to connect Gmail App Password.
4. Why dry-run should be used first.

The setting `onboarding_completed=true` is saved after the user finishes it.

## Queue System

Long operations are queued:

- message generation
- dry-run send
- live send
- export report

The worker processes jobs sequentially, updates progress, records failures, and keeps the UI responsive. Failed jobs can be retried and completed jobs can be cleared from the queue history.

## Contact State Machine

Contacts move through strict statuses:

```text
new -> generation_queued -> generating -> pending_review -> approved
approved -> queued -> sending -> dry_run_sent
approved -> queued -> sending -> sent
approved -> queued -> sending -> failed
failed -> approved/queued
dry_run_sent -> approved
any -> blacklisted
```

Invalid transitions are blocked with structured errors instead of crashing the UI.

## Dry-Run And Live

Dry-run is the normal first path:

- no SMTP call
- status becomes `dry_run_sent`
- queue job completes
- send log action is `dry_run_send`

Live send is only for an explicitly approved, owned test recipient during final validation:

- Gmail credentials must be present.
- Sender email must be configured.
- `allowed_test_recipient` must be set for the first live test.
- `daily_send_limit=1` should be used.
- Operator confirmation is required.

## Final Validation Status

Stage 1.10 release-candidate validation can be completed in two layers:

- Build, packaged app, DMG, onboarding, and no-secrets checks can run without Gmail credentials.
- Gmail dry-check and one-recipient live send require a real Gmail App Password, configured sender email, and owned allowed test recipient.

If those Gmail requirements are missing, the correct Stage 1.10 result is `PARTIAL` with no live send attempted.

## Known Limitations

- No AI personalization API in Stage 1; later stages add draft-only AI with human review.
- Stage 1 had no Instagram, X, Telegram, WhatsApp, Facebook, VK, or other channels.
  Later stages add Telegram official Bot API and safe Manual Assist for restricted social channels.
- No open/click tracking.
- No auto-replies.
- No automatic follow-up engine.
- No anti-spam bypasses, CAPTCHA bypasses, fake accounts, or identity hiding.
- Public distribution still requires Developer ID signing and notarization.

## Future Roadmap

- Stage 2: AI personalization provider behind explicit settings and review.
- Stage 2+: multi-mailbox support with clear identity and consent boundaries.
- Stage 2+: additional channels only if implemented with platform-compliant, user-controlled workflows.
- Later: richer import validation, campaign analytics, and safer operator audit trails.
