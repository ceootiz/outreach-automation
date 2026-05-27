# Stage 3.3 Conversation Intelligence

Stage 3.3 turns the app from a sender-plus-analytics tool into a calm
conversation intelligence workspace. It keeps the same safety model:
messages are never auto-sent, replies are never auto-generated into a live
send, and every outbound action still requires operator review.

## Unified Inbox

The new `Входящие` screen is a unified inbox for:

- email replies;
- Telegram replies;
- future channel replies.

Stage 3.3 keeps reply ingestion manual by default. IMAP fetch and Telegram
polling remain future-ready architecture, not hidden automation.

Inbox rows show:

- channel;
- recipient/contact;
- lead stage;
- unread/read state;
- last activity.

## Conversation Threads

Each contact can have a `conversation_threads` row and a structured
`conversation_messages` timeline. Messages can represent:

- outbound sent messages;
- dry-run records;
- inbound manual replies;
- AI notes;
- follow-up suggestions;
- status changes.

This is local SQLite data and does not trigger a send.

## Lead Pipeline

Contacts now have a lightweight lead stage:

- `New`
- `Contacted`
- `Warm`
- `Interested`
- `Negotiating`
- `Closed`
- `Lost`

The operator can change the lead stage from the inbox. AI can suggest a stage
from reply text, but it does not close deals, send messages, or rewrite
recipient/sender data.

## AI Conversation Intelligence

`src/intelligence/conversation_ai.py` provides a deterministic local baseline
for reply analysis:

- summary;
- intent;
- sentiment;
- urgency;
- recommended next action;
- follow-up timing/tone.

The rules are deliberately conservative:

- no fake relationship history;
- no invented facts;
- no claims of previous contact when none exists;
- no aggressive spam language;
- channel-aware tone.

## AI Reply Assist

AI Reply Assist suggests three draft variants:

- short reply;
- friendly reply;
- formal reply.

The user must copy/edit/use these manually. The app does not auto-send them.

## Follow-Up Intelligence

Follow-up suggestions are reminders and recommendations only:

1. AI suggests a timing and reason.
2. The suggestion is saved locally.
3. The operator decides what to do.
4. Any actual send still goes through existing dry-run/live guardrails.

## Analytics

Conversation metrics extend existing campaign metrics:

- reply rate;
- warm lead rate;
- interested lead rate;
- lead stage breakdown;
- follow-up suggestion count;
- channel comparison.

Visuals stay intentionally minimal to avoid CRM dashboard clutter.

## Safety Guarantees

- No auto-reply.
- No AI autosend.
- Human confirmation remains required.
- AI never changes sender.
- AI never rewrites recipient.
- Email/Gmail profiles remain active.
- Telegram Bot API guardrails remain active.
- Safe mode and allowed test recipient still block instead of rewriting.
- Secrets are never stored in SQLite and are redacted from logs.

## Known Limitations

- Email reply ingestion is manual in Stage 3.3.
- Telegram reply ingestion is manual in Stage 3.3.
- No IMAP sync is enabled yet.
- No Telegram polling is enabled yet.
- The inbox is operator-focused, not a full email client or Slack clone.
