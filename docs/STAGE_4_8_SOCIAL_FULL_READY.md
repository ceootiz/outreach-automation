# Stage 4.8 Social Full-Ready Audit

Stage 4.8 turns Instagram, TikTok, X and VK into complete safe Manual Assist channels and adds a full channel readiness and search layer.

This is not an unsafe automation stage. The app does not bypass captchas, run stealth browsers, farm accounts, evade bans, auto-click platform send buttons, scrape private data, or send messages in the background.

## What Full-Ready Means

For restricted social channels, full-ready means the operator can complete the workflow safely:

1. choose channel;
2. import contacts;
3. enrich public data when allowed;
4. generate AI drafts;
5. review in Outreach Session;
6. open profile;
7. copy message;
8. send manually outside the app;
9. mark manually sent;
10. move to the next lead.

The app tracks local state, timeline, analytics, replies and follow-ups. It does not perform hidden social-platform sending.

## Instagram

Instagram is Manual Assist Full:

- handle/profile URL import;
- safe public URL handoff;
- creator-friendly short AI drafts;
- copy/open/mark-sent;
- manual replies and follow-ups;
- global history search.

Official automated messaging remains disabled unless an approved, safe API path is added later.

## TikTok

TikTok is Manual Assist Full:

- handle/profile URL import;
- very short creator-style drafts;
- copy/open/mark-sent;
- manual timeline and follow-up tracking.

Automatic outreach through ordinary accounts is not implemented.

## X

X is Manual Assist/API Pending:

- handle/profile URL import;
- concise/direct drafts;
- copy/open/mark-sent;
- timeline, search and follow-up tracking.

Official API live-send is pending approved access and a safe product flow.

## VK

VK is Manual Assist/API Pending:

- profile URL/user handle handoff;
- direct social draft tone;
- copy/open/mark-sent;
- replies, timeline and follow-up tracking.

Official API live-send remains disabled until configured safely.

## Channel Readiness

New documentation:

```text
docs/CHANNEL_READINESS_MATRIX.md
```

New UI:

```text
Готовность каналов
```

The matrix includes Email, Telegram, Instagram, TikTok, X, VK, WhatsApp future and Viber future.

## Global Search

Stage 4.8 adds a `Поиск` section that searches local history:

- contacts;
- emails;
- handles;
- profile URLs;
- companies;
- campaigns;
- messages;
- replies;
- notes and timeline events;
- send logs;
- AI metrics/brief traces;
- enrichment text;
- follow-ups;
- manual sent records.

Search is local-only and does not call external APIs.

## QA Scripts

Synthetic social QA data:

```bash
python scripts/generate_social_qa_data.py --reset
```

Social Manual Assist benchmark:

```bash
python scripts/social_operator_benchmark.py
```

Both scripts use fake/demo data only and perform no sends.

## AI Social Rules

Social drafts should be:

- shorter than email;
- subject-less;
- value-first;
- friendly but not cringe;
- low-pressure;
- free of fake familiarity;
- free of claims like “I studied your profile” unless the data explicitly supports it.

All AI output remains pending review.

## Known Limitations

- Instagram, TikTok, X and VK live send are not automated.
- Official API slots are present but intentionally inactive until safe credentials and platform approval exist.
- Reply ingestion for restricted social channels is manual for now.
- Benchmark numbers are local synthetic performance, not real-world platform latency.
