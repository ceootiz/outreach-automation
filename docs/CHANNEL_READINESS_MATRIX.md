# Channel Readiness Matrix

This matrix defines what “ready” means for each channel without unsafe automation.

The app does not bypass captchas, platform limits, account restrictions, anti-spam systems, private pages or login requirements. If a platform restricts automated messaging, the product shows that limitation and routes the operator to Manual Assist.

## Status Summary

| Channel | Status | Official API live-send | Reply ingestion | Manual Assist | Readiness |
|---|---|---:|---:|---:|---:|
| Email | Full | Yes, Gmail SMTP | Yes, Gmail IMAP read-only | Optional | 96% |
| Telegram | Full-ready, credentials may be pending | Yes, Bot API | Yes, getUpdates polling | Ready fallback | 92% |
| Instagram | Manual Assist Full | Restricted, not enabled | Manual only | Full | 88% |
| TikTok | Manual Assist Full | Limited, not enabled | Manual only | Full | 86% |
| X | Manual Assist/API Pending | Limited, not enabled | Manual only | Full | 82% |
| VK | Manual Assist/API Pending | Partial, not enabled | Manual only | Full | 82% |
| WhatsApp | Future slot | Future official Business Platform only | Future | Not implemented | 15% |
| Viber | Future slot | Future official bot/business API only | Future | Not implemented | 15% |

## Full-Ready Definition For Restricted Social Channels

For Instagram, TikTok, X and VK, “full-ready” means the safe operator workflow is complete:

- contact import works;
- handle/profile URL fields work;
- public-only enrichment can run when safe;
- AI Research and Writer drafts are channel-aware;
- priority scoring works;
- Outreach Session works;
- copy message works;
- open profile works;
- mark manually sent works;
- manual reply add works;
- timeline updates;
- analytics update;
- follow-ups work;
- global search finds history;
- exports include contact state;
- no dead buttons;
- limitations are clear.

It does not mean hidden automatic DM sending.

## Channel Notes

### Email

Email is full via Gmail profiles, secure App Password storage, SMTP dry-run/live guardrails, IMAP read-only sync, timeline, reports and safe mode.

### Telegram

Telegram uses only the official Bot API. Live send requires a saved Bot Token and a `chat_id` where the bot already has access. Polling uses `getUpdates`; no userbot is used.

### Instagram

Instagram is Manual Assist Full. The app can prepare a short message, open the profile URL and track manual status. It does not automate login, DM clicks, captcha, scraping or anti-spam behavior.

### TikTok

TikTok is Manual Assist Full. The app prepares very short creator-style text and opens public profile URLs. No hidden automatic messaging is implemented.

### X

X is Manual Assist/API Pending. The app supports concise/direct drafts, copy/open/mark-sent and tracking. Official live API work remains pending until an approved safe integration exists.

### VK

VK is Manual Assist/API Pending. The app supports profile/user link handoff, copied text and manual sent tracking. Official API send is intentionally disabled until configured safely.

### WhatsApp And Viber

WhatsApp and Viber are future slots only. They require official business/bot APIs before any live integration can be considered.

## Runtime UI

The app exposes this matrix under:

```text
Готовность каналов
```

Credentials missing for Email or Telegram are shown as normal readiness status, not as product failure.

Stage 4.9 also exposes connector slots and per-channel cockpits under:

```text
Каналы
```

Each connector slot shows connection state, credential state, official API status, current execution mode, recommended workflow and limitations.
