# Stage 3.2 Campaign Intelligence

Stage 3.2 turns the app into a lightweight outreach operating system while
keeping the same safety model: AI helps draft and analyze, but never sends or
approves messages automatically.

## Campaign Intelligence

The app now keeps structured campaign context:

- campaign metrics;
- recent contact timeline events;
- channel breakdown;
- AI draft counts and average confidence;
- reply counts and response statuses.

The UI exposes this in calm Apple-like screens: `Кампании`, `AI Assist`,
`Ответы`, and `Аналитика`.

## Contact Timeline

Each contact can have timeline events:

- `contact_created`;
- `ai_generated`;
- `approved`;
- `dry_run`;
- `sent`;
- `failed`;
- `reply_added`;
- `blacklisted`;
- `note_added`;
- `status_changed`.

Timeline is local SQLite data. It is not exported with secrets and does not
trigger any message send.

## Reply System

Reply Inbox supports manual reply tracking:

- reply text;
- reply status;
- AI summary;
- suggested next action.

Supported reply statuses:

- `interested`;
- `maybe_later`;
- `not_interested`;
- `no_response`;
- `follow_up_needed`;
- `closed`.

Telegram replies are manual-add only at this stage.

## AI Reply Assist

AI Reply Assist is suggestion-only. It can produce:

- short reply;
- formal reply;
- friendly reply;
- summary;
- suggested next action.

The user must choose, edit, and send manually. There is no auto-reply.

## AI Quality Scoring

Drafts can be scored locally for:

- spam risk;
- personalization quality;
- confidence;
- genericness score;
- tone quality;
- warnings.

This is a lightweight quality signal, not a deliverability guarantee.

## Campaign Presets

Stage 3.2 includes presets:

- B2B Email Outreach;
- Telegram Outreach;
- Influencer Collaboration;
- Affiliate Proposal;
- Partnership Intro.

Presets store tone, length, prompt hints, and manual follow-up guidance.

## Follow-Up Workflow

Follow-ups are reminders only:

1. Schedule a due date.
2. Queue a reminder.
3. The operator reviews the contact.
4. Any follow-up send still requires normal confirmation.

No follow-up is auto-sent.

## Safety Guarantees

- AI never auto-sends.
- AI never auto-approves.
- AI never changes sender identity.
- AI never rewrites recipients.
- Email/Gmail profiles and Telegram Bot API guardrails remain active.
- Secrets are not stored in SQLite and are redacted from logs.
