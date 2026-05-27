# Stage 4.9 Social Finalization

Stage 4.9 makes social channels feel production-ready without pretending that restricted platforms can be safely automated.

## Connector Slots

Every channel now has a connector slot:

- Email
- Telegram
- Instagram
- TikTok
- X
- VK
- WhatsApp future
- Viber future

Each slot exposes:

- connection state;
- capability summary;
- official API status;
- execution mode;
- limitations;
- recommended workflow;
- setup instructions;
- credential state;
- risk label.

Human states are used in the UI: Connected, Partial, Manual Assist, API Pending, Not Configured, Future Support.

## Channel Cockpits

The new `Каналы` screen is an operator cockpit for each channel.

It shows:

- current connector state;
- workflow checklist;
- current lead;
- AI/manual message preview;
- open profile;
- copy message;
- mark manually sent;
- add reply;
- channel exports.

Social channels do not send hidden DMs. They prepare the operator to act manually.

## Manual Assist Philosophy

For Instagram, TikTok, X and VK, full-ready means:

- import works;
- handle/profile URL works;
- AI draft works;
- outreach session works;
- copy/open/mark sent works;
- replies/timeline/follow-ups/search/export work;
- limitations are visible.

It does not mean hidden automatic DM sending.

## Focus Mode

Outreach Session includes Focus Mode:

- current lead;
- draft;
- hotkeys;
- core actions.

It hides filter clutter while preserving the session state.

## Profile URLs

`src/channels/profile_urls.py` safely builds public URLs for:

- Instagram;
- TikTok;
- X;
- VK.

If a URL cannot be built, the UI says `Профиль не найден`.

## Search

Global Search now supports:

- recent searches;
- token fallback;
- contacts;
- companies;
- handles;
- replies;
- campaigns;
- messages;
- AI briefs;
- follow-ups;
- timeline events.

Search is local and does not call external APIs.

## Exports

Per-channel/session exports support:

- CSV;
- JSON;
- clipboard summary.

Exports include local contact/session state only and do not include secrets.

## Safety

Stage 4.9 still refuses:

- hidden sending;
- captcha bypass;
- anti-detection;
- browser farming;
- fake accounts;
- stealth automation;
- background DM spam;
- platform limit bypass.

If a platform limits an action, the app shows that limitation and routes the operator to Manual Assist or official API setup.

## Known Limitations

- Instagram, TikTok, X and VK remain Manual Assist/API Pending unless official API access is added.
- WhatsApp and Viber are future connector slots only.
- Channel cockpits are local operator tools; they do not replace platform-native compliance review.
