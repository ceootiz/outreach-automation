# Stage 3.7 Web Enrichment Layer

Stage 3.7 adds a conservative public web enrichment layer for Research Brain.
The goal is better recipient briefs without unsafe automation.

## What It Does

- Extracts a candidate website from explicit `website` data or a non-generic email domain.
- Fetches only public pages with normal HTTP `GET`.
- Reads homepage text and, when obvious and same-domain, one or two public pages such as About or Contact.
- Extracts page title, meta description, visible text, category signals, source URLs, warnings and confidence.
- Stores a structured `EnrichmentResult` with `source_basis`.
- Feeds successful or partial enrichment into Research Brain before Writer Brain creates the draft.

## Safety Rules

The enrichment layer does not:

- log in to websites;
- use browser automation or JavaScript rendering;
- bypass captcha, paywalls or anti-bot systems;
- scrape private pages;
- use cookies;
- fetch aggressively in the background;
- claim that a human or AI “studied” a site when fetch failed.

Generic email domains such as Gmail, Yandex, Mail.ru, Outlook, Yahoo and iCloud are not used to infer a company.

## Robots And Limits

By default, enrichment:

- respects `robots.txt` when it explicitly blocks a page;
- uses an 8 second timeout;
- fetches up to 2 public pages per contact;
- caches results for 7 days;
- limits batch size to 25 contacts.

These limits are configurable in `Аккаунты и настройки` → `AI Assist` → `Web Enrichment`.

## AI Integration

The dual-brain flow can now run:

```text
contact row
→ web enrichment
→ Research Brain recipient brief
→ Writer Brain draft
→ pending_review
```

Research Brain may use enrichment only when `status` is `success` or `partial`.
It must mark `website_public_data` in `source_basis`.

Writer Brain may use insights from the brief, but must not write phrases like
“я изучил ваш сайт” or imply private/manual browsing.

AI still never sends, never approves, never changes sender and never rewrites recipient.

## UI

AI Assist mode adds:

- `Обогатить данные из сайта`;
- `Проверить данные получателей`;
- per-contact enrichment status: `Не проверено`, `Найдено`, `Частично`, `Ошибка`, `Блок`, `Пропущено`;
- Settings controls for batch size, pages, timeout, cache TTL and robots.

## Cache

The `enrichment_cache` table stores fetched public summaries by URL. Runtime cache data is not a secret, but it is app data and should not be committed.

## Future Slot

The architecture leaves room for future official search/enrichment providers.
Stage 3.7 does not call search APIs and does not perform live web browsing beyond conservative public page fetches.
