# Stage 4.0 Real-World Readiness QA

Stage 4.0 is a production-readiness and operational QA phase. It does not add
unsafe automation. The objective is to prove that the system can be used by an
operator in real controlled conditions without breaking queue, routing, AI
review, inbox ingestion or Manual Assist flows.

## Release Status Definitions

### RC Ready

RC is ready when automated tests and packaged smoke pass, no-secrets audit is
clean, and all live checks are either verified with owned targets or clearly
marked pending.

### Beta Ready

Beta is ready when these controlled checks pass with owned accounts/chats:

- Gmail SMTP sends exactly one email to the configured allowed test recipient;
- Gmail IMAP read-only sync ingests the reply without duplicate messages;
- Telegram Bot API sends exactly one message to the owned allowed `chat_id`;
- Telegram polling ingests one reply without duplicate messages;
- OpenAI Research + Writer generates review-only drafts with no unsafe claims;
- no autosend, no auto-reply, no recipient rewrite regressions;
- queue remains stable after restart and failure recovery.

### Stable Ready

Stable is ready after repeated Beta checks with several small campaigns, multiple
Gmail profiles, Manual Assist social flows, failure testing and operator UX
review.

## Controlled Live Preconditions

Live verification must use only owned/test accounts and targets:

- `safe_mode=true`;
- `real_send_confirm_required=true`;
- `daily_send_limit=1`;
- `allowed_test_recipient` set to the exact owned email or Telegram `chat_id`;
- active Gmail profile has App Password in secure credential storage;
- Telegram Bot Token is saved in secure credential storage;
- OpenAI keys are saved in secure credential storage;
- no secrets are printed, exported or committed.

If any precondition is missing, live verification must be skipped and reported as
`PARTIAL`.

## Gmail SMTP Verification

Controlled flow:

1. Create one Email campaign from a preset.
2. Add exactly one owned test recipient.
3. Generate an AI draft.
4. Review and approve manually.
5. Dry-run send.
6. Switch to live only with safe preconditions.
7. Send exactly one email.

Expected:

- SMTP is not called during dry-run;
- live SMTP sender is the active Gmail profile;
- live recipient is `contact.email`;
- `allowed_test_recipient` only blocks mismatches and never rewrites;
- no duplicate send;
- contact status becomes `sent`;
- conversation and timeline entries are created.

## Gmail IMAP Read-Only Sync

Controlled flow:

1. Reply manually from the owned inbox.
2. Run Sync now.
3. Run Sync now again.

Expected:

- IMAP uses the active Gmail profile credentials;
- sync is read-only;
- reply is ingested into the matching conversation;
- unread/local state updates locally;
- repeated sync is idempotent;
- no server-side mutation and no autosend.

## Telegram Bot API Verification

Controlled flow:

1. Check Telegram connection via `getMe`.
2. Add one Telegram contact with owned `chat_id`.
3. Dry-run Telegram.
4. Live send exactly one message only if safe preconditions are met.
5. Reply manually in Telegram.
6. Run polling sync.

Expected:

- dry-run never calls `sendMessage`;
- live send uses exact `external_id/chat_id`;
- safe-mode mismatch blocks and does not rewrite;
- polling ingestion is idempotent;
- token never appears in logs or errors.

## OpenAI Dual-Brain QA

Controlled contacts:

- generic Gmail/Yandex-style address;
- real company domain;
- creator-style site/profile;
- Telegram channel-style contact.

Expected:

- Research Brain states when data is weak;
- Writer Brain uses only row/enrichment brief;
- no fake browsing claims;
- no fake familiarity;
- no spam tone;
- drafts stay `pending_review`;
- AI never approves, sends, or changes recipient/sender.

## Manual Assist QA

For Instagram, X, TikTok and VK:

- generate/copy message;
- open profile;
- mark sent manually;
- mark replied manually;
- mark follow-up done.

Expected:

- no hidden automation;
- no browser hacks, scraping, captcha bypass or fake accounts;
- warnings clearly state that restricted channels require Manual Assist.

## Performance And Stability QA

Recommended stress-like pass:

- import 100+ contacts;
- run AI draft batch within configured limits;
- run inbox sync;
- switch campaigns/channels/profiles;
- render timelines and analytics;
- restart during a queued/running job.

Stage 4.0 adds queue recovery for interrupted `running` jobs. On restart, such
jobs are returned to `queued` with a recovery marker so the worker can continue
instead of leaving them stuck.

## Failure QA

Test safely:

- invalid Gmail password;
- invalid OpenAI key;
- invalid Telegram token;
- network timeout;
- IMAP unavailable;
- enrichment failure;
- AI malformed JSON;
- worker interruption.

Expected:

- no crash;
- no raw traceback for the operator;
- no secret leakage;
- failed jobs can be retried or clearly diagnosed;
- no autosend or auto-reply after failures.

## Automated Coverage Added In Stage 4.0

`tests/test_stage_4_0_real_world_qa.py` covers:

- queue restore after restart;
- malformed AI output handling;
- live guardrails: confirmation, allowed recipient, safe daily limit;
- sender/recipient routing and Gmail profile isolation;
- IMAP ingestion idempotency;
- Manual Assist operator-only flow;
- no autosend.

## Current Limitation

Automated tests use fake SMTP, fake AI and fake IMAP clients. Real Gmail,
Telegram and OpenAI live verification still requires the operator to configure
owned credentials/targets locally and run the controlled checklist above.
