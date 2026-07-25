# Handoff для Codex на Windows

## Назначение сборки

Это тестовая Windows-сборка Outreach Automation / Gmail Рассылка `5.1.1`.
Она предназначена для проверки desktop runtime, Gmail credential storage,
интерфейса и безопасных dry-run сценариев.

Сборка не должна выполнять массовые или скрытые отправки. Не используйте
реальные письма, Telegram-сообщения или social DM во время проверки.

## Что находится рядом

- `Gmail Рассылка/Gmail Рассылка.exe` - основной executable.
- `README_TESTER_RU.txt` - короткая инструкция для тестировщика.
- `WINDOWS_INSTALL.md` - инструкция по установке.
- `Gmail Рассылка.bat` и `Gmail Рассылка.ps1` - launchers.

## Безопасные границы

- Не выводить Gmail App Password, Telegram Bot Token или OpenAI API key.
- Не читать и не показывать содержимое `.env`.
- Не выполнять live send.
- Не добавлять реальные контакты для массовой рассылки.
- Не менять recipient routing, queue или safe-mode без отдельной задачи.
- Не загружать runtime `data`, `logs`, `exports`, `imports`, `cache`,
  `credentials`, `*.sqlite` или `*.db` в git/архивы/отчеты.

## Black-box проверка готового ZIP

1. Распаковать ZIP в новую пустую папку.
2. Запустить `Gmail Рассылка/Gmail Рассылка.exe`.
3. Подтвердить, что окно открывается без `.env`, Python и терминала.
4. Открыть `Аккаунты и настройки`.
5. Проверить кликабельность Gmail address и App Password.
6. Убедиться, что App Password masked.
7. Сохранить отдельный тестовый Gmail-профиль с Google App Password.
8. Перезапустить приложение и проверить сохранение профиля.
9. Если Windows Credential Manager недоступен, убедиться, что UI не блокируется
   и безопасный DPAPI/encrypted fallback позволяет продолжить.
10. Проверить `Проверить подключение Gmail` только на owned test account.
11. Оставить режим `dry_run`; реальные письма не отправлять.
12. Проверить навигацию, таблицу, поиск, настройки, Inbox и Outreach Session.
13. Закрыть приложение и убедиться, что нет зависшего процесса.

## Проверка исходного репозитория

В PowerShell из корня checkout:

```powershell
git status
git branch --show-current
python scripts/release/verify_git_remote.py
Set-ExecutionPolicy -Scope Process Bypass -Force
.\scripts\windows\setup_windows.ps1
.\scripts\windows\test_windows.ps1
.\scripts\windows\build_windows.ps1
.\scripts\windows\package_windows.ps1 -SkipBuild
.\scripts\windows\smoke_windows.ps1
python scripts\release\validate_release.py `
  --windows-zip "dist\windows\Gmail Рассылка-5.1.1-windows.zip" `
  --allow-missing-macos `
  --smoke-status passed
```

Ожидаемый ZIP:

```text
dist\windows\Gmail Рассылка-5.1.1-windows.zip
```

## Что обязательно проверить и вернуть

- Версия Windows и архитектура CPU.
- Запустился ли EXE из чистой распакованной папки.
- Появлялся ли SmartScreen.
- Работает ли ввод текста во всех Gmail fields.
- Какой backend показан после сохранения: Credential Manager, DPAPI fallback
  или encrypted local fallback. Значения секретов не записывать.
- Сохранился ли профиль после перезапуска.
- Работает ли connection check и какой безопасный текст ошибки показан.
- Есть ли clipping, overlap, black overlay или некликабельные controls.
- Результат `test_windows.ps1`, `smoke_windows.ps1` и release validator.
- Скриншоты проблем и точные шаги воспроизведения.
- Логи только после ручной проверки, что в них нет секретов.

## Формат отчета

```text
STATUS:
WINDOWS VERSION:
APP START:
GMAIL FIELDS:
CREDENTIAL BACKEND:
PROFILE AFTER RESTART:
DRY-RUN:
UI/CLICKABILITY:
TEST_WINDOWS:
SMOKE:
ZIP AUDIT:
BUGS FOUND:
REPRODUCTION STEPS:
```

## Известные ограничения

- EXE не подписан цифровой подписью, поэтому SmartScreen может показать warning.
- Реальная SMTP/IMAP/Telegram/OpenAI работа требует owned credentials и отдельного
  controlled live QA.
- Manual Assist не выполняет скрытую отправку и требует действий оператора.
