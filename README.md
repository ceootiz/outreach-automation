# Outreach Automation Desktop App - Stage 1 Email MVP

Desktop-приложение для управляемой email-рассылки через Gmail SMTP. Stage 1 сфокусирован на безопасном ручном workflow: импорт контактов, генерация писем по шаблонам, ручное подтверждение, лимиты, blacklist, статусы и журналы ошибок.

Это не спам-система. В приложении нет обхода антиспама, капч, банов, скрытия личности, фейковых аккаунтов или агрессивной автоматизации.

## Быстрый запуск на macOS

```bash
cd outreach_automation
./scripts/setup_mac.sh
./scripts/run_mac.sh
./scripts/test_mac.sh
```

`setup_mac.sh` создает `.venv` через `python3.12` или `python3.11`, ставит зависимости и создает `.env` из `.env.example` только для dev-совместимости.

## Быстрый запуск на Windows

Для готового ZIP:

1. Распакуйте `Gmail Рассылка-5.1.1-windows.zip`.
2. Откройте папку `Gmail Рассылка`.
3. Дважды нажмите `Gmail Рассылка.exe`.

Для разработки/теста на Windows PowerShell:

```powershell
cd outreach_automation
.\scripts\windows\setup_windows.ps1
.\scripts\windows\run_windows.ps1
```

Данные Windows хранятся в `%APPDATA%\Gmail Рассылка\`, включая `data`, `exports`, `imports`, `logs`, `backups`, `cache`.

Подробнее:

```text
docs/WINDOWS_INSTALL.md
docs/STAGE_5_1_WINDOWS_PORT.md
```

## Установка вручную

```bash
cd outreach_automation
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Подключение Gmail в приложении

Обычному пользователю не нужно редактировать `.env`.

Откройте `Аккаунты и настройки` -> `Профили Gmail` и заполните:

- `Название профиля`
- `Gmail address`
- `App Password`

Затем нажмите:

- `Сохранить профиль`
- `Сделать активным`, если этот ящик должен быть отправителем
- `Проверить подключение Gmail`

Можно сохранить несколько Gmail-профилей и переключаться между ними без повторной привязки. Gmail App Password каждого профиля хранится в защищенном локальном хранилище:

- macOS: Keychain, если доступен;
- Windows: Credential Manager, если доступен;
- fallback: зашифрованный локальный файл в папке данных приложения.

Пароль не сохраняется в SQLite, не показывается в логах и не попадает в отчеты.

Важно:

- Gmail App Password - это отдельный пароль приложения Google, а не основной пароль от аккаунта.
- `.env` остается dev-only fallback: если в приложении пароль не сохранен, можно использовать `GMAIL_APP_PASSWORD`.
- Активный Gmail-профиль из UI имеет приоритет над `.env`.
- Кнопка `Проверить подключение Gmail` проверяет STARTTLS/login и не отправляет письмо.

## Как получить Gmail App Password

1. Включите 2-Step Verification в Google Account.
2. Откройте Google Account -> Security -> App passwords.
3. Создайте app password для Mail/Other app.
4. Вставьте значение в поле `App Password` в форме Gmail-профиля.

Для разработки `.env` fallback все еще поддерживается, но нормальный desktop UX — сохранить пароль внутри приложения.

## Запуск

```bash
cd outreach_automation
python app.py
```

На macOS удобнее запускать через:

```bash
./scripts/run_mac.sh
```

Если нужен headless smoke без реального окна:

```bash
OUTREACH_AUTOMATION_FORCE_OFFSCREEN=1 OUTREACH_AUTOMATION_SMOKE_EXIT_MS=1000 ./scripts/run_mac.sh
```

## Быстрый запуск без терминала

Можно создать пользовательский launcher и запускать приложение двойным кликом из Finder:

```bash
./scripts/create_launcher.sh
```

После этого появятся:

```text
launchers/Gmail Рассылка.command
launchers/Gmail Рассылка Launcher.command
```

Основной файл для пользователя:

```text
launchers/Gmail Рассылка.command
```

Поведение:

- если есть `dist/Gmail Рассылка.app`, launcher откроет собранное приложение;
- если собранного приложения нет, launcher покажет сообщение и запустит dev-режим через `./scripts/run_mac.sh`;
- если `.venv` отсутствует, launcher покажет понятную ошибку: нужно запустить `scripts/setup_mac.sh`;
- launcher не читает `.env` напрямую и не печатает секреты.

Собрать production `.app` можно так:

```bash
./scripts/build_macos.sh
```

Дополнительно можно создать macOS `.app` launcher без Terminal:

```bash
./scripts/create_macos_launcher_app.sh
```

Он создаст:

```text
launchers/Gmail Рассылка Launcher.app
```

Это легкий wrapper над `.command` launcher. Если нужен самый простой и прозрачный вариант, используйте `.command` launcher.

## macOS Qt cocoa plugin error

Симптом:

```text
qt.qpa.plugin: Could not find the Qt platform plugin "cocoa" in ""
This application failed to start because no Qt platform plugin could be initialized.
```

Обычно это означает, что PySide6 установлен, но launcher не передал Qt путь к platform plugins.
`run_mac.sh` вычисляет путь через PySide6 `QLibraryInfo` и выставляет:

- `QT_PLUGIN_PATH`
- `QT_QPA_PLATFORM_PLUGIN_PATH`

Проект закрепляет совместимый диапазон `PySide6>=6.7,<6.10`; если в `.venv` стоит более новая сборка и Cocoa не стартует, `setup_mac.sh` переустановит зависимости из `requirements.txt`.

Для диагностики:

```bash
./scripts/setup_mac.sh
./scripts/qt_doctor.py
./scripts/run_mac.sh
```

`qt_doctor.py` печатает Python/PySide6 версию, путь к Qt plugins и наличие `libqcocoa.dylib`. Он не читает и не печатает `.env`.

## Формат Excel/CSV

Поддерживаются `.xlsx`, `.xlsm`, `.csv`.

## Простой сценарий на русском

Основной сценарий теперь такой:

1. Откройте вкладку `Получатели`.
2. Добавьте строки вручную, вставьте таблицу из Excel/Google Sheets или загрузите XLSX/CSV.
3. Для каждой строки заполните минимум:
   - `Email`
   - `Тема письма`
   - `Сообщение`
4. Нажмите `Сохранить изменения`, если добавляли строки вручную.
5. На вкладке `Рассылка` нажмите `Подготовить сообщения`.
6. Проверьте строки и нажмите `Подтвердить выбранные`.
7. Сначала оставьте `Тестовый режим`: кнопка `Отправить подтвержденные` не отправит реальные письма, а только проверит процесс.
8. Для реальной проверки используйте `Боевой режим` только с одним своим тестовым ящиком и дневным лимитом `1`.

Каждая строка = отдельный получатель и свое отдельное сообщение. Шаблоны нужны только для строк, где сообщение пустое.

Можно скачать безопасный пример:

```text
Рассылка -> Скачать пример Excel
```

Обязательная колонка:

- `email`

Желательные/опциональные колонки:

- `subject`
- `message` или `base_message`
- `name`
- `company`
- `topic` или `niche`

Гибкие заголовки:

- email: `email`, `mail`, `почта`, `e-mail`, `адрес`, `email адрес`, `почтовый адрес`
- name: `name`, `имя`
- company: `company`, `компания`
- topic: `topic`, `niche`, `note`, `заметка`, `ниша`, `тема/ниша`
- subject: `subject`, `тема`, `тема письма`, `заголовок`
- base_message: `message`, `text`, `body`, `base_message`, `сообщение`, `текст`, `письмо`, `текст письма`

Невалидные email и дубликаты внутри кампании не импортируются и записываются в ошибки.

## Что поддерживает Stage 1

- PySide6 desktop UI с вкладками Campaign, Contacts, Templates, Settings, Logs.
- Импорт Excel/CSV в SQLite.
- Таблица контактов с фильтром по статусу и поиском.
- Ручное редактирование `subject`, `generated_message`, `status`.
- Шаблоны с переменными `{{name}}`, `{{company}}`, `{{topic}}`, `{{base_message}}`.
- Placeholder AI provider без внешних API.
- Review mode: `new -> pending_review -> approved -> sent`.
- Gmail SMTP отправка через STARTTLS.
- Dry-run send mode по умолчанию: SMTP не вызывается, действие пишется в logs, контакт получает статус `dry_run_sent`.
- Live send mode требует явного подтверждения оператора, если включен `real_send_confirm_required`.
- Optional `allowed_test_recipient` ограничивает live-отправку одним owned test inbox в safe mode.
- Blacklist/stop-list.
- Daily send limit по `send_logs`.
- Delay между письмами.
- Follow-up placeholder: после отправки ставится `follow_up_due_at = sent_at + N days`.
- Export report в `exports/contacts_export_YYYYMMDD_HHMMSS.xlsx` с листами contacts, send_logs, errors.
- Логи действий и ошибок в SQLite и `logs/app.log`.

## Что не поддерживается

- Нет скрытой автоматической отправки в Instagram/X/TikTok/VK.
- Нет WhatsApp/Viber live-интеграций: это future slots под official API.
- Нет open/click tracking.
- Нет автоответов.
- Нет автоотправки follow-up.
- Нет обходов антиспама, капч, банов или лимитов провайдеров.

## First real Gmail test

Безопасный порядок для первой реальной отправки на один owned test inbox:

Use only an inbox you own and can inspect. Do not guess or use a third-party address for the first live test.

1. Create Gmail App Password.
2. Run the app and open `Аккаунты и настройки`.
3. Enter Gmail address and App Password.
4. Click `Сохранить Gmail`.
5. Click `Проверить подключение Gmail`.
6. Set `send_mode=dry_run`.
7. Create/import one contact with your owned test inbox.
   Можно создать его скриптом:
   ```bash
   ./scripts/create_test_contact.py your_test_email@gmail.com
   ```
8. Generate message.
9. Approve selected.
10. Run Send approved in dry-run.
    В dry-run SMTP не вызывается, письмо не отправляется, контакт получает `dry_run_sent`.
11. Re-approve the same contact after reviewing the dry-run result.
12. Set `send_mode=live`.
13. Set `allowed_test_recipient` to the same owned inbox.
14. Keep `daily_send_limit=1`.
15. Send approved with confirmation.
16. Check inbox/spam.
17. Export report.

Live mode sends real Gmail messages. Keep `safe_mode=true` and `real_send_confirm_required=true` for the first test.

## Stage 1 Release Candidate

Stage 1 RC — это production-like macOS сборка для управляемой Gmail-рассылки с ручным подтверждением и безопасным dry-run по умолчанию.

Установка и первый запуск:

1. Откройте `dist/Gmail Рассылка-5.1.1.dmg`.
2. Перетащите `Gmail Рассылка.app` в Applications.
3. Запустите приложение.
4. Пройдите onboarding.
5. Сначала работайте в `Тестовый режим`: реальные письма не отправляются.

Gmail setup:

- Создайте Gmail App Password в Google Account.
- В приложении откройте `Аккаунты и настройки`.
- Создайте или выберите Gmail-профиль.
- Укажите `Gmail address`.
- Введите `App Password`.
- Нажмите `Сохранить профиль`.
- Нажмите `Сделать активным`.
- Нажмите `Проверить подключение Gmail`.

Safe mode и первая live-проверка:

- Оставьте `Безопасный режим` включенным.
- Установите `Дневной лимит = 1`.
- Заполните `Разрешенный тестовый получатель` своим owned inbox.
- Создайте ровно одного получателя с этим email.
- Сначала выполните тестовую отправку в dry-run.
- Только после этого включайте `Боевой режим` и подтверждайте live send.

Production limitations:

- Stage 1 не содержит AI API, соцсетей, tracking, автоответов и follow-up engine.
- Публичная раздача требует Developer ID signing и notarization.
- Финальная Gmail live-проверка невозможна без активного Gmail-профиля, сохраненного Gmail App Password и owned allowed test recipient.

Полное закрытие Stage 1 описано здесь:

```text
docs/STAGE_1_COMPLETE.md
docs/RELEASE_CHECKLIST.md
docs/RELEASE_NOTES_STAGE_1.md
```

## 1.10.0 multiple Gmail profiles

`1.10.0` adds multiple saved Gmail sender profiles. Each profile stores only its
name/email/status in SQLite; App Password values stay in Keychain/Credential
Manager/encrypted local storage. The active profile is used as SMTP sender,
while the recipient remains exactly the email from the selected contact row.
`allowed_test_recipient` still only blocks mismatches and never rewrites recipients.

## 2.0.1 AI Assist

`2.0.1` включает проверенный AI Assist flow: отдельный режим `AI Assist`
рядом с ручным режимом.

Ручной режим остается прежним: пользователь сам вводит тему и сообщение,
подтверждает получателей и запускает тестовую/боевую отправку через уже
существующие guardrails.

AI Assist работает только с черновиками:

- пользователь добавляет получателей и задает `Тема рассылки`;
- выбирает тон письма: дружелюбный, деловой, короткий или премиальный;
- AI генерирует индивидуальные `Тема письма` и `Сообщение`;
- контакт получает статус `Нужно подтвердить`;
- AI никогда не подтверждает и не отправляет письма автоматически.

OpenAI API key хранится через защищенное локальное хранилище приложения
(macOS Keychain / Windows Credential Manager / encrypted local fallback), не
попадает в SQLite, отчеты или логи. `.env` с `OPENAI_API_KEY` остается только
dev-only fallback.

Если ключ не задан, AI Assist показывает понятную ошибку, а ручной режим
продолжает работать.

## 3.0.0 Multi-channel foundation

`3.0.0` добавляет выбор канала рассылки:

- Email
- X / Twitter
- Instagram
- Telegram
- VK
- TikTok

Email остается полностью рабочим каналом через активный Gmail-профиль.
X, Instagram, Telegram, VK и TikTok в Stage 3.0 работают только в безопасном
режиме: можно подготовить сообщения, проверить базу, запустить dry-run,
посмотреть queue/logs и экспортировать отчет.

Live-отправка для новых каналов отключена до безопасной official API-интеграции.
`allowed_test_recipient` и другие guardrails не переписывают получателя:
они только разрешают или блокируют действие.

AI Assist учитывает канал: для Email генерирует тему и тело письма, для
социальных каналов готовит короткий текст без темы. AI по-прежнему только
создает черновики и никогда не отправляет сообщения автоматически.

Подробнее:

```text
docs/STAGE_3_MULTI_CHANNEL_MODES.md
```

## 3.1.1 Telegram Bot API

`3.1.1` добавляет первую official social live-интеграцию: Telegram Bot API.
В `3.1.1` также добавлены controlled verification tests для Telegram live flow.
На локальной проверке Bot Token и owned test `chat_id` не были настроены, поэтому
реальная Telegram-отправка не выполнялась.

Что доступно:

- Bot Token вводится в `Аккаунты и настройки` -> `Telegram`;
- token хранится в защищенном локальном хранилище, не в SQLite;
- `Проверить подключение` вызывает `getMe` и не отправляет сообщений;
- dry-run Telegram не делает HTTP вызовов;
- live send использует только `sendMessage` и только `chat_id` из поля `ID / chat`;
- `allowed_test_recipient` для Telegram сравнивается с `chat_id` и никогда не переписывает получателя.

Telegram Bot не может писать произвольным незнакомым людям. Получатель должен
уже начать диалог с ботом или быть в чате, где бот имеет доступ.

Подробнее:

```text
docs/TELEGRAM_BOT_INTEGRATION.md
```

## 3.2.0 Campaign Intelligence

`3.2.0` добавляет CRM-lite слой поверх текущей безопасной рассылки:

- экран `Кампании` со спокойной сводкой и contact timeline;
- `Ответы` для ручного reply tracking;
- `AI Assist` для quality scoring и вариантов ответа без auto-send;
- `Аналитика` с sent/reply/approval metrics и channel breakdown;
- follow-up reminders без автоотправки;
- campaign presets для B2B, Telegram, influencer, affiliate и partnership сценариев.

AI по-прежнему только помогает писать и анализировать. Он не подтверждает
получателей, не меняет отправителя, не переписывает recipient и не отправляет
сообщения автоматически.

Подробнее:

```text
docs/STAGE_3_2_CAMPAIGN_INTELLIGENCE.md
```

## 3.3.0 Conversation Intelligence

`3.3.0` добавляет conversation intelligence слой для операторской работы:

- новый раздел `Входящие` как unified inbox для Email, Telegram и будущих каналов;
- conversation threads и timeline сообщений по каждому контакту;
- lead pipeline: New, Contacted, Warm, Interested, Negotiating, Closed, Lost;
- AI conversation summary, intent/sentiment/urgency и suggested next action;
- AI Reply Assist с тремя вариантами ответа без auto-reply;
- follow-up suggestions без автоотправки;
- conversation metrics: reply rate, warm/interested leads, follow-up suggestions.

Reply ingestion в Stage 3.3 остается ручным. AI только анализирует и предлагает,
но не меняет отправителя, не переписывает получателя, не подтверждает контакты и
никогда не отправляет сообщения автоматически.

Подробнее:

```text
docs/STAGE_3_3_CONVERSATION_INTELLIGENCE.md
```

## 3.4.0 Reply Ingestion

`3.4.0` добавляет read-only ingest-систему ответов:

- Email reply sync через Gmail IMAP over SSL в режиме только чтения;
- Telegram reply sync через official Bot API `getUpdates`;
- unified inbox auto-ingestion без auto-reply и без autosend;
- sync checkpoints: IMAP UID и Telegram update_id;
- idempotent ingestion без дублей;
- AI summary/stage suggestion jobs после ingest;
- unread/read state, last activity и searchable conversation thread.

Email sync использует активный Gmail-профиль и уже сохраненный App Password.
Пароли не хранятся в SQLite. Telegram sync использует сохраненный Bot Token,
не пишет token в логи и не отправляет сообщения.

Lead stage меняется только после действий оператора. AI может предложить stage
и next action, но не применяет их автоматически.

Подробнее:

```text
docs/STAGE_3_4_REPLY_INGESTION.md
```

## 3.5.0 Production Verification

`3.5.0` добавляет production verification phase для реальных интеграций:

- Gmail SMTP и recipient routing проверяются через guarded live-flow сценарии;
- Gmail IMAP и Telegram polling проверяются на idempotent ingestion без дублей;
- AI Assist проверяется как draft-only pipeline без auto-approve и autosend;
- safe mode, allowed test recipient, daily limit и live confirmation покрыты regression tests;
- failure paths проверяются на user-safe errors и отсутствие leakage секретов.

Live SMTP/Telegram/OpenAI проверки выполняются только на owned accounts/chats
при `safe_mode=true`, `daily_send_limit=1` и настроенном `allowed_test_recipient`.
Если controlled credentials/targets не подтверждены, live часть считается pending,
а сборка остается в guarded RC состоянии.

Подробнее:

```text
docs/STAGE_3_5_PRODUCTION_VERIFICATION.md
```

## 3.6.0 Dual AI Brain

`3.6.0` добавляет двухступенчатую AI-систему:

- Research Brain анализирует только данные строки получателя: email/domain, имя,
  компанию, сайт URL, соцпрофиль и заметку;
- Writer Brain получает campaign topic, канал и structured recipient brief,
  затем пишет черновик;
- можно использовать один OpenAI key для обоих brain или разные keys;
- ключи хранятся через secure credential storage, не в SQLite;
- web enrichment пока выключен, поэтому AI не должен утверждать, что изучил сайт,
  профиль, видео или внешние источники;
- все AI outputs остаются `pending_review`;
- AI не подтверждает получателей, не меняет sender/recipient и не запускает отправку.

Подробнее:

```text
docs/STAGE_3_6_DUAL_AI_BRAIN.md
```

## 3.7.0 Web Enrichment Layer

`3.7.0` добавляет безопасный Web Enrichment Layer для Research Brain:

- извлекает публичные данные только из email domain, website URL и открытых страниц сайта;
- пропускает generic-домены вроде Gmail/Yandex/Mail.ru без лишних выводов;
- использует GET-only HTTP, понятный user-agent, timeout, лимиты страниц и cache;
- уважает `robots.txt`, если он явно запрещает fetch;
- не делает login automation, JS/browser automation, captcha bypass или приватный scraping;
- сохраняет enrichment result с `source_basis`, warnings и confidence;
- Research Brain использует enrichment только как публичный source, а Writer Brain не должен писать “я изучил ваш сайт”.

AI по-прежнему только готовит черновики. Все outputs остаются `pending_review`,
human review обязателен, отправка не запускается автоматически.

Подробнее:

```text
docs/STAGE_3_7_WEB_ENRICHMENT.md
```

## 3.8.0 Channel Execution Framework

`3.8.0` добавляет unified execution layer для всех каналов:

- явная capability matrix для Email, Telegram, X, Instagram, VK и TikTok;
- `Execution Mode`: Dry-run, Official API или Manual Assist;
- risk labels и понятные ограничения по каждому каналу;
- Manual Assist для X/Instagram/VK/TikTok: copy message, open profile, mark as sent;
- Email и Telegram остаются official API каналами с existing safe-mode/live confirmation guardrails;
- unsupported live automation блокируется, а не прячется за browser hacks;
- AI prompts получают execution context и пишут social/manual сообщения короче и естественнее;
- Inbox получил операторские действия: Copy reply, Open profile, Mark replied manually, Mark follow-up done.

Подробнее:

```text
docs/STAGE_3_8_CHANNEL_EXECUTION_FRAMEWORK.md
```

## 3.9.0 Operator Workflow System

`3.9.0` добавляет operator-friendly слой поверх всех мощных режимов:

- Campaign Presets для B2B Email Outreach, Influencer Collaboration, Telegram Outreach, Partnership Intro и Affiliate Proposal;
- New Campaign Wizard: preset → канал → execution mode → AI → получатели → checklist → draft launch;
- Launch checklist с понятными OK/warning/error пунктами;
- Campaign Health Score: Healthy, Needs attention или Risky;
- Quick Start сценарии для Email, Telegram и AI Draft Generation;
- smart warnings перед запуском отправки или Manual Assist;
- Operator Dashboard: drafts на проверке, replies, follow-up reminders, risk alerts и AI warnings;
- archive/duplicate/export действия без скрытой отправки.

Подробнее:

```text
docs/STAGE_3_9_OPERATOR_WORKFLOW.md
```

## 4.0.0 Real-World Readiness QA

`4.0.0` переводит платформу в production-readiness режим:

- queue recovery восстанавливает interrupted `running` jobs после рестарта;
- Stage 4 QA покрывает Gmail SMTP guardrails, IMAP idempotency, profile isolation, malformed AI output и Manual Assist safety;
- real-world checklist описывает controlled Gmail, Telegram, OpenAI, inbox, manual assist, performance, failure и recovery проверки;
- live integrations должны проверяться только на owned/test accounts с `safe_mode=true`, `allowed_test_recipient` и `daily_send_limit=1`;
- no autosend, no auto-reply и human confirmation остаются обязательными.

Подробнее:

```text
docs/STAGE_4_0_REAL_WORLD_QA.md
```

## 4.6.0 High Volume Operator Mode

`4.6.0` добавляет keyboard-first operator session поверх существующих безопасных каналов:

- переключатель `Precision Mode` / `High Volume Mode`;
- отдельный экран `Outreach Session` для conveyor review: lead → draft → copy/open → manual send → mark sent → next lead;
- hotkeys `A/R/C/O/S/N/P/F/L/1/2/3` для approve, regenerate, copy, open, mark sent, navigation, follow-up, lead status и AI variants;
- Smart Priority labels: High / Medium / Low Priority;
- session restore: текущий lead, фильтры, позиция и выбранный вариант сохраняются локально;
- AI feedback loop: useful, generic, inaccurate, too aggressive, weak personalization;
- manual assist остается честным: приложение может открыть профиль и скопировать текст, но не отправляет скрыто и не обходит ограничения платформ.

Подробнее:

```text
docs/STAGE_4_6_HIGH_VOLUME_OPERATOR.md
```

## 4.7.0 Operator Throughput Polish

`4.7.0` делает High Volume Mode быстрее и устойчивее в реальном рабочем темпе:

- repeatable QA dataset на 100 synthetic leads через `scripts/generate_operator_qa_data.py`;
- throughput benchmark через `scripts/operator_throughput_benchmark.py`;
- batch ordering: priority, new, AI confidence, channel, last activity;
- quick filters: High priority, Needs review, Ready to send, Manual Assist, Follow-up due, Has reply, Low confidence;
- Space/Enter/Cmd-C/Cmd-O/Cmd-S hotkeys с защитой от срабатывания во время редактирования текста;
- session recovery сохраняет current lead, filters, order, draft variant и unsaved draft;
- copy/mark-sent используют выбранный/отредактированный вариант;
- Manual Assist остается ручным: open profile/copy/mark sent без скрытой отправки.

Подробнее:

```text
docs/STAGE_4_7_OPERATOR_THROUGHPUT.md
```

## 4.8.0 Social Full-Ready Audit

`4.8.0` доводит Instagram, TikTok, X и VK до безопасного full-ready состояния через production-grade Manual Assist:

- `Готовность каналов`: понятная matrix по Email, Telegram, Instagram, TikTok, X, VK, WhatsApp future и Viber future;
- Instagram/TikTok/X/VK считаются full-ready как Manual Assist: import, handle/profile URL, enrichment, AI drafts, priority, Outreach Session, copy/open/mark sent, replies, timeline, analytics, follow-up, search и export;
- официальный live-send для restricted social channels остается выключенным, пока нет безопасной approved API-интеграции;
- новый раздел `Поиск` ищет по контактам, кампаниям, messages, replies, timeline, send logs, AI notes, enrichment и follow-ups;
- social QA dataset: `scripts/generate_social_qa_data.py`;
- social Manual Assist benchmark: `scripts/social_operator_benchmark.py`;
- human labels в UI: `Как отправляем`, `Помощник отправки`, `Ограничения канала`, `Что умеет канал`.

Подробнее:

```text
docs/STAGE_4_8_SOCIAL_FULL_READY.md
docs/CHANNEL_READINESS_MATRIX.md
```

## 4.9.0 Social Operator Finalization

`4.9.0` превращает social channels из набора возможностей в понятные operator cockpits:

- connector slots для Email, Telegram, Instagram, TikTok, X, VK, WhatsApp future и Viber future;
- connection states: Connected, Partial, Manual Assist, API Pending, Not Configured, Future Support;
- новый раздел `Каналы`: channel cockpit с текущим лидом, workflow checklist, message preview, copy/open/mark sent/add reply/exports;
- Focus Mode в Outreach Session: минимальный UI для текущего лида, черновика, hotkeys и действий;
- profile URL engine безопасно строит Instagram/TikTok/X/VK ссылки из handle/profile URL/external_id;
- per-channel exports: CSV, JSON и clipboard summary;
- smart channel recommendation предлагает канал, но не отправляет и не включает automation;
- Global Search получил recent searches и token fallback для более живого поиска.

Подробнее:

```text
docs/STAGE_4_9_SOCIAL_FINALIZATION.md
```

## 5.0.0 Production Operator Platform

`5.0.0` делает систему быстрее и удобнее для ежедневной операторской работы:

- новый performance layer: cache manager, session cache, latency metrics, virtualized paging и render budgets;
- Command Palette по `Cmd+K`/`Ctrl+K`: поиск, навигация и безопасные operator actions без autosend;
- Quick Review 2.0 в Outreach Session: минимальный UI, hotkeys `J/K`, `Enter`, `E`, `C`, `O`, `S`, `F`, `1/2/3`;
- Notification Center: replies, follow-ups, AI warnings и queue failures без шумных popups;
- Background Task Monitor: queue health, job counts, failed tasks и retries;
- chunked massive import, paginated contacts и operator exports;
- Stage 5 benchmark `scripts/perf_benchmark.py` для startup/search/session/import/queue latency.

Подробнее:

```text
docs/STAGE_5_0_OPERATOR_PLATFORM.md
```

## 5.1.1 Windows Port Packaging

`5.1.1` добавляет Windows-ready runtime/package flow:

- `%APPDATA%\Gmail Рассылка\` app-data dirs, включая `cache`;
- Windows Credential Manager / PasswordVault priority with encrypted local fallback;
- PowerShell scripts for setup/run/test/build/package/smoke;
- Windows `.bat`/`.ps1` launchers;
- PyInstaller Windows spec and `.ico` icon;
- Windows install guide for non-technical users.

На macOS Windows `.exe` не собирается; ZIP нужно создавать на Windows:

```powershell
.\scripts\windows\build_windows.ps1
.\scripts\windows\package_windows.ps1
```

Ожидаемый artifact:

```text
dist\windows\Gmail Рассылка-5.1.1-windows.zip
```

Подробнее:

```text
docs/STAGE_5_1_WINDOWS_PORT.md
docs/WINDOWS_INSTALL.md
```

## 5.1.1 GitHub Release Workflow

`5.1.1` также добавляет безопасный release workflow для macOS/Windows distribution:

- `scripts/release/prepare_release.sh` и `.ps1` для подготовки release assets;
- `scripts/release/validate_release.py` для SHA256 checksums и `dist/release_manifest.json`;
- `scripts/release/github_release.sh` и `.ps1` для draft-first GitHub release flow;
- `docs/RELEASE_PROCESS.md` и `docs/RELEASE_NOTES_5_1_1.md`.

GitHub upload по умолчанию не выполняется. Для draft release нужно явно запустить:

```bash
./scripts/release/github_release.sh --create-draft
```

Перед публикацией обязательно проверить `git remote -v`, чтобы assets ушли в правильный repository.

## Тесты

```bash
cd outreach_automation
pytest
```

Или через launcher:

```bash
./scripts/test_mac.sh
```

## Production build для macOS

Stage 1.9 переводит локальные runtime-файлы из папки проекта в пользовательскую папку macOS:

```text
~/Library/Application Support/Gmail Рассылка/
  data/
  exports/
  imports/
  logs/
  backups/
```

Это значит:

- SQLite база живет в `Application Support/Gmail Рассылка/data/outreach.sqlite`.
- Отчеты создаются в `Application Support/Gmail Рассылка/exports/`.
- Логи пишутся в `Application Support/Gmail Рассылка/logs/app.log` с rotation.
- Перед рискованными операциями создаются safety backups в `backups/`.
- `.env` по-прежнему не коммитится и не показывается в интерфейсе.

Сборка `.app`:

```bash
cd outreach_automation
./scripts/setup_mac.sh
./scripts/build_macos.sh
```

Результат:

```text
dist/Gmail Рассылка.app
```

`build_macos.sh` делает narrow PyInstaller build: собирает только нужные PySide6 runtime modules (`QtCore`, `QtGui`, `QtWidgets`) и проверяет, что в bundle попали app binary, Qt cocoa plugin и иконки. В конце скрипт печатает размер `.app`.

Сборка DMG:

```bash
./scripts/build_dmg.sh
```

Результат:

```text
dist/Gmail Рассылка.dmg
```

Версионированный release artifact:

```bash
./scripts/build_dmg.sh --versioned
```

Результат:

```text
dist/Gmail Рассылка-5.1.1.dmg
```

Smoke-проверки production artifacts:

```bash
./scripts/smoke_packaged_app.sh
./scripts/smoke_dmg.sh
```

Оба smoke-скрипта используют временную папку `OUTREACH_AUTOMATION_APP_DIR`, не читают реальные секреты и не используют project-local runtime данные.

Полный release-candidate smoke:

```bash
./scripts/check_no_secrets.sh
./scripts/release_smoke.sh
```

`release_smoke.sh` запускает тесты, собирает `.app`, проверяет packaged app, собирает versioned DMG и проверяет запуск приложения из DMG.

Если `build_macos.sh` пишет, что PyInstaller не установлен, обновите окружение:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### First launch / onboarding

При первом видимом запуске приложение показывает короткий onboarding:

1. Добро пожаловать.
2. Что умеет приложение.
3. Как подключить Gmail App Password.
4. Почему сначала нужно использовать тестовый режим.

После завершения сохраняется настройка:

```text
onboarding_completed=true
```

Для автоматических smoke-тестов onboarding можно отключить:

```bash
OUTREACH_AUTOMATION_DISABLE_ONBOARDING=1 ./scripts/run_mac.sh
```

### Backup / recovery

При старте приложение проверяет SQLite через `PRAGMA integrity_check`.
Если база отсутствует, она создается автоматически.
Если база повреждена, приложение:

1. Создает recovery backup в `backups/`.
2. Переименовывает поврежденный файл.
3. Запускает новую базу.
4. Показывает пользователю безопасное сообщение без Python traceback.

Хранятся последние 10 backup-файлов.

### Troubleshooting production build

- Запустите `./scripts/qt_doctor.py`, если `.app` не стартует из-за Qt platform plugin.
- Проверьте, что `resources/icons/app_icon.icns` существует.
- Не кладите `.env`, `.venv`, SQLite, exports или logs внутрь app bundle.
- Для локальной диагностики используйте `~/Library/Application Support/Gmail Рассылка/logs/app.log`.

### Signing / notarization

Локальный `.app` подходит для QA, но публичная раздача требует Apple Developer ID signing и notarization. Чеклист с командами:

```text
docs/MACOS_SIGNING_NOTARIZATION.md
```

Optional hooks:

```bash
DEVELOPER_ID_APP="Developer ID Application: ..." ./scripts/build_macos.sh
NOTARY_APPLE_ID="..." NOTARY_TEAM_ID="..." NOTARY_KEYCHAIN_PROFILE="..." ./scripts/build_dmg.sh --versioned
```

Если env vars не заданы, signing/notarization scripts делают graceful skip и сборка продолжается. Значения credentials не печатаются.

Release docs:

```text
docs/RELEASE_CHECKLIST.md
docs/RELEASE_NOTES_STAGE_1.md
```

## Сброс demo-настроек

После smoke-проверок можно вернуть безопасные настройки, дефолтный шаблон и удалить только известные demo/smoke кампании:

```bash
./scripts/reset_demo_data.py
```

Скрипт не удаляет `.env`, exports и log-файлы.

## Stage 1.6 PRO: Queue Engine

Stage 1.6 добавляет production-like очередь и background worker, чтобы долгие операции не блокировали UI.

Что появилось:

- SQLite table `job_queue` для `generate_message`, `dry_run_send`, `live_send`, `export_report`.
- Contact State Machine со строгими переходами:
  `new -> generation_queued -> generating -> pending_review -> approved -> queued -> sending -> dry_run_sent/sent/failed`.
- Queue Service для enqueue, retry, cancel, progress, stats и очистки completed jobs.
- PySide-safe worker на `QThread + QObject`, который выполняет jobs sequentially, ловит exceptions и продолжает следующий job.
- Campaign tab Queue Panel:
  worker status, current job/contact, queue stats, progress bar, ETA placeholder, refresh/cancel/retry/clear controls.
- Generate messages, Send approved и Export report теперь ставятся в очередь и выполняются worker-ом.

Queue statuses:

- `pending` / `queued`: job ожидает обработки.
- `running`: worker обрабатывает job.
- `completed`: job успешно завершен.
- `failed`: job завершился с ошибкой, можно retry.
- `cancelled`: job отменен оператором.
- `paused`: reserved для будущего pause/resume UX.

Cancel/retry behavior:

- Cancel works best for queued/current jobs and keeps worker alive.
- Retry moves failed send jobs back to `queued` when state-machine transition allows it.
- Worker never logs Gmail secrets and keeps existing guardrails: `send_mode=dry_run` default, `safe_mode`, `allowed_test_recipient`, blacklist, daily limit, live confirmation.

Why UI no longer freezes:

- Import already runs in a background task.
- Generate/send/export now enqueue lightweight jobs, then worker processes them outside the main UI thread.
- Export reports include a `job_queue` sheet alongside contacts, send logs, and import errors for queue smoke diagnostics.

Покрыты:

- импорт валидного Excel;
- пропуск невалидных email;
- дедупликация email;
- подстановка переменных шаблона;
- blacklist перед отправкой;
- daily rate limiter;
- защита Gmail password от попадания в логи.
- dry-run/live guardrails;
- allowed test recipient protection;
- one-contact test helper.
