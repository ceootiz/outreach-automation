# Stage 3.4 Reply Ingestion

Stage 3.4 adds a real read-only reply ingestion layer for the unified inbox.
It does not add auto-reply, AI autosend, or any hidden outbound automation.

## Email IMAP Sync

Email sync uses Gmail IMAP over SSL:

- host: `imap.gmail.com`;
- port: `993`;
- active Gmail profile email;
- the same saved Gmail App Password already stored securely by the app.

The IMAP client selects `INBOX` in read-only mode and fetches message data.
It does not delete, archive, flag, or remotely mark messages as read.

## Telegram Polling

Telegram sync uses the official Telegram Bot API:

- `getUpdates`;
- safe incremental offset;
- no webhooks in this stage;
- no userbot;
- no message send.

The bot only sees chats where it already has access according to Telegram Bot
API rules.

## Unified Inbox

Synced replies are stored as:

- `replies`;
- `conversation_messages`;
- unread conversation state;
- timeline events;
- AI summary jobs.

The `Входящие` screen has:

- `Sync now`;
- `Refresh inbox`;
- `Mark read`;
- conversation list;
- conversation thread;
- reply composer;
- AI summary/reply/follow-up suggestion buttons.

## Matching Logic

Email matching uses conservative fallbacks:

1. remote message id / UID duplicate check;
2. sender email to existing contact;
3. normalized subject fallback;
4. orphan conversation bucket if no contact matches.

Telegram matching uses `chat_id` (`external_id`) first. Unknown chats become
orphan Telegram contacts for manual review.

## Sync Safety

Sync is idempotent:

- Email stores IMAP UID and remote Message-ID;
- Telegram stores update_id;
- duplicate remote messages are skipped;
- sync checkpoints are persisted in `inbox_sync_state`;
- restart recovery continues from the last checkpoint.

## AI Reply Analysis

After ingest, the app queues:

- `ai_summarize_reply`;
- `ai_stage_suggestion`.

AI records summary, intent, sentiment, urgency, next action, and suggested lead
stage. It does not apply lead stage changes automatically.

## Safety Guarantees

- No auto-reply.
- No AI autosend.
- No remote mailbox mutation.
- No Telegram sends during sync.
- No passwords/tokens in SQLite.
- No secrets in logs.
- Human review remains required before any outbound action.

## Known Limitations

- IMAP sync is incremental and intentionally conservative.
- Email thread matching by Message-ID is future-ready, but old outbound
  messages may not have remote Message-ID metadata.
- Background sync settings are present with a safe minimum interval; this stage
  focuses on manual/queued sync and persistence.
- Orphan conversations need operator review.
