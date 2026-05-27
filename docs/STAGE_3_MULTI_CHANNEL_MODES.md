# Stage 3.0 Multi-Channel Modes

Stage 3.0 adds a safe foundation for choosing an outreach channel without
turning the app into a spam bot.

## Channels

- Email
- X / Twitter
- Instagram
- Telegram
- VK
- TikTok

Email remains the only channel with live send support. It uses the active Gmail
profile, dry-run by default, manual review, blacklist, daily limits and live
confirmation.

## What Works Now

- Channel selector on the main screen.
- Channel-aware recipient fields: handle, profile URL and external ID.
- Channel-aware queue jobs and send logs.
- Dry-run for every channel.
- AI Assist prompt context per channel.
- Social-channel AI drafts use message body only; subject stays empty.
- Platform limitation cards in Accounts and Settings.

## Dry-Run Only Channels

X, Instagram, Telegram, VK and TikTok are intentionally dry-run only in Stage
3.0. The app can prepare messages, validate that a recipient handle/profile is
present, put jobs into the queue, write audit logs and export reports.

Live sending is blocked with a clear message until a safe official API
integration is implemented.

## Platform Limits

- X / Twitter: direct message automation is limited by platform rules. Use only
  permitted APIs and manual confirmation.
- Instagram: automatic messaging is strongly limited. No mass live sends.
- Telegram: a bot can write only to chats it can access.
- VK: official authorization/API and limits are required.
- TikTok: ordinary accounts are not intended for automated mass messaging.

## Safety Rules

- No captcha or anti-spam bypass.
- No scraping private data.
- No fake or stolen accounts.
- No browser automation intended to bypass platform rules.
- No autosend for new channels.
- No API tokens in SQLite, logs, exports or reports.
- Human review remains mandatory.

## Future Integration Plan

1. Add official API connectors one channel at a time.
2. Keep dry-run and manual review as default.
3. Add per-channel rate limits and stop-lists before enabling any live send.
4. Run one-recipient live verification for each official integration.
