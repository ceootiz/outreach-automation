# Stage 3.5 Production Verification

Stage 3.5 is a validation stage, not a feature stage. It verifies the real
integration boundaries added through Stage 3.4 while preserving the product
safety model:

- no auto-replies;
- no AI autosend;
- no mass sending;
- no unknown recipients/chats;
- no secrets in SQLite, exports, reports or logs;
- live sends only to controlled owned targets.

## Release Candidate Criteria

RC is ready only when all of these pass:

- Gmail SMTP live send verified with exactly one owned recipient.
- Gmail IMAP read-only sync verified against an owned inbox.
- Telegram Bot API `getMe`, dry-run, live send and `getUpdates` polling verified
  against one owned chat where the bot has access.
- AI Assist live key check and draft generation verified.
- Unified Inbox ingests replies idempotently.
- Safe mode blocks mismatches, missing recipients, missing confirmation and
  daily-limit excess.
- No sender/recipient rewrite regression.
- No autosend or auto-approve regression.
- No secret/token/password leakage.

## Controlled Live Checklist

Before any live send:

1. Use only owned accounts, owned inboxes and owned Telegram chats.
2. Keep `safe_mode=true`.
3. Set `daily_send_limit=1`.
4. Set `allowed_test_recipient` to the exact owned target.
5. Keep `real_send_confirm_required=true`.
6. Confirm the live dialog shows the correct sender and recipient.
7. Send exactly one message.
8. Check status, timeline, conversation and logs.
9. Export only sanitized/non-personal reports.

## Gmail SMTP Verification

Expected flow:

1. Active Gmail profile exists.
2. App Password is saved through secure credential storage.
3. Gmail connection check succeeds.
4. One owned contact is dry-run sent first.
5. Dry-run does not call SMTP.
6. The contact is re-approved.
7. Live mode sends exactly one message.
8. SMTP envelope recipient equals `contact.email`.
9. SMTP sender equals the active Gmail profile email.
10. Timeline and conversation contain the outbound message.

Regression tests cover the same routing and guardrails with fake SMTP so CI
never sends real email.

## Gmail IMAP Verification

Expected flow:

1. Reply manually from the owned inbox.
2. Run `Sync now`.
3. IMAP login uses the active Gmail profile App Password.
4. Sync is read-only.
5. The reply is added to the conversation and Unified Inbox.
6. Running sync again does not duplicate the reply.
7. Lead stage changes are suggestions only.

Sync checkpoints are stored locally in `inbox_sync_state`; remote mailbox state
is not mutated.

## Telegram Verification

Expected flow:

1. Bot Token is saved through secure credential storage.
2. `Check Telegram connection` calls `getMe` only.
3. One controlled Telegram contact uses an owned `chat_id`.
4. Dry-run does not call `sendMessage`.
5. Live send calls `sendMessage` once with the exact `chat_id`.
6. Manual reply in Telegram is ingested through `getUpdates`.
7. Re-running polling does not duplicate the reply.

Telegram Bot API limitations still apply: the bot can message only chats where
it has access.

## AI Verification

Expected flow:

1. OpenAI API key is saved through secure credential storage.
2. `Test AI connection` succeeds.
3. AI Assist generates drafts for controlled contacts.
4. Drafts remain `pending_review`.
5. Contacts are not approved automatically.
6. No send jobs are created by AI generation.
7. Replies can be summarized and suggested replies can be generated.
8. AI suggestions never send and never change recipients/senders.

Prompt quality checks remain focused on cautious personalization, no fabricated
facts and no fake relationship history.

## Failure Tests

Expected behavior for invalid credentials/tokens/network failures:

- show user-safe errors;
- never print raw secrets;
- never crash the UI;
- keep failed jobs recoverable;
- keep live send blocked when guardrails fail.

## Verified By Automated Stage 3.5 Tests

`tests/test_stage_3_5_production_verification.py` covers:

- Gmail dry-run and live routing with fake SMTP;
- active Gmail profile sender/password isolation;
- safe-mode mismatch blocking;
- missing recipient blocking;
- live-send confirmation blocking;
- daily limit enforcement;
- Telegram dry-run/live/polling with fake official Bot API client;
- IMAP ingestion idempotency with fake IMAP client;
- AI draft/reply intelligence no-autosend guarantees;
- token redaction on failure paths.

## Remaining Manual Live Items

The following require real owned credentials and cannot be proven by automated
tests alone:

- Gmail SMTP delivery to an owned inbox.
- Gmail IMAP login against the real mailbox.
- Telegram `getMe`, `sendMessage` and `getUpdates` against an owned bot/chat.
- OpenAI live key check and real model draft quality.

If any of those credentials/targets are missing or ownership cannot be
confirmed, Stage 3.5 should be reported as `PARTIAL` for live verification while
the guarded build/tests remain valid.
