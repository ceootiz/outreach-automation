# Stage 3.8 Channel Execution Framework

Stage 3.8 adds a unified execution layer for every channel. The goal is
production-grade multi-channel operations without unsafe automation.

## Capability Matrix

Each channel now has explicit capabilities:

- Email: official Gmail SMTP/IMAP, live send allowed with confirmation, low risk.
- Telegram: official Bot API, live send and polling allowed only for accessible chat_id, low-medium risk.
- X / Twitter: limited official API surface, live automation disabled, Manual Assist recommended, medium-high risk.
- Instagram: restricted automation, live automation disabled, Manual Assist only, high risk.
- VK: partial official API path, live automation disabled until a safe integration exists, medium risk.
- TikTok: limited official API surface, live automation disabled, Manual Assist only, high risk.

The matrix lives in `src/channels/execution/capability_matrix.py` and is used by
UI, service policy and tests.

## Execution Modes

The main campaign screen exposes an `Execution Mode` selector:

- Dry-run: validates flow and records logs without external sends.
- Official API: uses approved official integrations such as Gmail SMTP or Telegram Bot API.
- Manual Assist: prepares the text/profile action for the operator, but does not send.

Unsupported official/live sends are blocked instead of silently falling back to hidden automation.

## Manual Assist

Manual Assist is the safe path for channels where automatic messaging is unsafe,
restricted or not implemented.

The operator sees:

- prepared message;
- profile/recipient;
- copy button;
- open profile button;
- mark as sent button.

No login automation, scraping, captcha bypass, stealth browser flow or fake-account behavior is implemented.

## Risk Labels

Each channel carries a risk level and explanation. The UI shows the active risk
beside the execution mode so the operator knows whether the channel is official,
manual, or restricted.

## Inbox Operator Actions

Unified Inbox now includes manual workflow helpers:

- Copy reply;
- Open profile;
- Mark replied manually;
- Mark follow-up done.

These actions record operator workflow state. They do not auto-reply or auto-send.

## AI Context

AI draft prompts now include execution context. For Manual Assist and social
channels, AI is instructed to write short, natural human-style messages and to
avoid implying hidden automation.

AI still never sends, never approves, never changes sender and never rewrites recipients.

## Safety Rules

The framework enforces:

- no hidden auto-send for unsupported channels;
- explicit confirmation for official live sends;
- safe-mode and recipient guardrails stay in the existing send path;
- blacklist and rate limits stay active;
- structured execution logs for manual assists, dry-runs and official sends.

## Known Limitations

Manual Assist opens profile URLs only when the contact has a URL or a supported
handle-to-profile pattern. Official live integrations remain limited to Gmail
and Telegram Bot API.
