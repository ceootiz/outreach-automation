# Telegram Bot Integration

Stage 3.1 adds the first official social live integration: Telegram Bot API.

## What Is Supported

- Save a Telegram Bot Token in secure local storage.
- Check connection with `getMe`.
- Dry-run Telegram sends without HTTP calls.
- Live send with `sendMessage` only to `chat_id` values where the bot has access.
- Safe mode with `allowed_test_recipient` matched against Telegram `chat_id`.

## What Is Not Supported

- Userbots.
- Login/password automation.
- Browser automation.
- Captcha or anti-spam bypass.
- Messaging arbitrary users who have not started a bot chat.
- Rewriting a recipient to some default chat.

## Create A Bot

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Choose a bot name and username.
4. Copy the Bot Token.
5. Open the app: `Аккаунты и настройки` -> `Telegram`.
6. Paste the Bot Token into `Bot Token`.
7. Click `Сохранить Telegram`.
8. Click `Проверить подключение`.

The app stores the token through macOS Keychain, Windows Credential Manager or
encrypted local fallback. It is not stored in SQLite, logs, exports or reports.

## Get chat_id

Telegram Bot API can reliably send to `chat_id`. A bot can only write to chats
it can access:

- a user has already started a conversation with the bot;
- the bot is a member of a group/channel with permission to send.

Common safe ways to get `chat_id`:

1. Start a chat with your bot from your owned test Telegram account.
2. Call `getUpdates` for the bot token locally, or use a trusted admin tool.
3. Copy the numeric `chat.id`.
4. Put it into the recipient row as `ID / chat`.

Do not collect private data or attempt to message users who did not opt in.

## Safe Test Flow

1. Keep `Тестовый режим` enabled.
2. Select channel `Telegram`.
3. Add one recipient with `ID / chat`.
4. Prepare message.
5. Confirm recipient.
6. Run dry-run.
7. Set `allowed_test_recipient` to the same `chat_id`.
8. Switch to live only for the one owned test chat.
9. Confirm the live dialog.

If `safe_mode=true` and `allowed_test_recipient` is set, the app blocks any
Telegram live send where `contact.external_id` does not exactly match it.

## Stage 3.1.1 Controlled Verification

Date: 2026-05-22.

Local verification status:

- Precheck tests passed.
- No-secrets audit passed.
- Telegram UI clickability passed.
- Bot Token detected: no.
- Default test `chat_id` detected: no.
- `getMe` check: skipped because Bot Token was not configured.
- Real live send: not executed.

The live verification remains pending until an operator saves a Bot Token in
`Аккаунты и настройки` -> `Telegram` and sets a single owned test `chat_id`.
Do not paste token or chat values into logs, reports, issues or documentation.

Required live checklist:

1. The bot is created through BotFather.
2. The owned test account has started a chat with the bot.
3. The recipient row uses that chat as `ID / chat`.
4. `safe_mode=true`.
5. `allowed_test_recipient` exactly matches the owned test `chat_id`.
6. `daily_send_limit=1`.
7. The app is in live mode only for this one controlled test.
8. The confirmation dialog shows Telegram, one recipient and the bot label.
9. After send, verify exactly one `sendMessage` result and one `sent` log row.
