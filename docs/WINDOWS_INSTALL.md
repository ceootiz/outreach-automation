# Windows Install Guide

This guide is for a non-technical operator.

## Install

1. Download `Gmail Рассылка-5.1.1-windows.zip`.
2. Right-click the ZIP and choose `Extract All...`.
3. Open the extracted folder.
4. Double-click `Gmail Рассылка.exe`.

Do not move files out of the extracted folder one by one. Keep the whole folder together.

## Where Data Is Stored

The app stores local data here:

```text
%APPDATA%\Gmail Рассылка\
  data\
  exports\
  imports\
  logs\
  backups\
  cache\
```

Gmail App Passwords, Telegram tokens and AI API keys are not stored in SQLite.

## Connect Gmail

1. Open `Аккаунты и настройки`.
2. Open `Профили Gmail`.
3. Enter:
   - profile name;
   - Gmail address;
   - Gmail App Password.
4. Click `Сохранить профиль`.
5. Click `Сделать активным`.
6. Click `Проверить подключение Gmail`.

Use a Google App Password, not your normal Google password.

## Connect AI

1. Open `Аккаунты и настройки`.
2. Open `AI Assist`.
3. Choose provider `OpenAI`.
4. Paste API key into the masked field.
5. Click save/test.

The app never sends messages automatically from AI output. Drafts require human review.

## Windows SmartScreen

If Windows shows SmartScreen:

1. Click `More info`.
2. Check that the app name is `Gmail Рассылка`.
3. Click `Run anyway` only if you received the ZIP from the trusted release owner.

This can happen for unsigned internal builds.

## Antivirus False Positives

PyInstaller apps can sometimes trigger false positives because they bundle Python and Qt runtime files. If this happens:

1. Do not disable antivirus globally.
2. Ask the release owner for a fresh signed build or checksum.
3. Keep the app in a normal user folder, not a system folder.

## Safety

- Never share Gmail App Passwords.
- Never paste secrets into screenshots or chat.
- Use dry-run first.
- Live send must remain human-confirmed.
- Social channels use Manual Assist when official automation is unavailable.
