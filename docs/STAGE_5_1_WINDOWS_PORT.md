# Stage 5.1 Windows Port Packaging

Stage 5.1 prepares a Windows-compatible test/distribution path without changing the macOS app architecture and without adding unsafe automation.

## What Was Ported

- Windows app-data directories under `%APPDATA%\Gmail Рассылка\`.
- Windows Credential Manager / PasswordVault backend remains the preferred Windows secure store.
- Encrypted local credential fallback remains available when platform APIs are unavailable.
- Windows launchers:
  - `launchers/windows/Gmail Рассылка.bat`
  - `launchers/windows/Gmail Рассылка.ps1`
- Windows scripts:
  - `scripts/windows/setup_windows.ps1`
  - `scripts/windows/run_windows.ps1`
  - `scripts/windows/test_windows.ps1`
  - `scripts/windows/build_windows.ps1`
  - `scripts/windows/package_windows.ps1`
  - `scripts/windows/smoke_windows.ps1`
- PyInstaller Windows spec:
  - `packaging/windows/Gmail Рассылка Windows.spec`
- Windows icon:
  - `resources/icons/app_icon.ico`
- User install guide:
  - `docs/WINDOWS_INSTALL.md`

## Platform Audit

Found and handled cross-platform points:

- App data paths: already abstracted; added `cache/` and testable Windows path resolution.
- Credential storage: Windows Credential Manager path already existed; hardened PowerShell invocation so secrets are not passed in process arguments.
- Profile opening: moved social profile open actions to `src/platform_actions.py`, using Qt/webbrowser cross-platform behavior.
- Clipboard: remains PySide6 clipboard and is already cross-platform.
- PySide6 plugins: Windows build validates `qwindows.dll`; macOS build still validates `libqcocoa.dylib`.
- Icons: added generated `.ico`; macOS `.icns` remains unchanged for DMG.
- Build scripts: Windows scripts live under `scripts/windows/`; macOS scripts remain unchanged.
- Launchers: Windows `.bat`/`.ps1` launchers are separate from macOS `.command`.

## Windows Paths

Runtime data is stored outside the project and outside the packaged app:

```text
%APPDATA%\Gmail Рассылка\
  data\
  exports\
  imports\
  logs\
  backups\
  cache\
```

The package must not include `.env`, SQLite databases, logs, imports, exports or personal runtime files.

## Credential Storage

Priority order on Windows:

1. Windows Credential Manager / PasswordVault.
2. Encrypted local fallback.
3. Environment variables only as dev fallback.

Secrets are not stored in SQLite, reports or logs.

## Build Flow

Run on Windows PowerShell:

```powershell
.\scripts\windows\setup_windows.ps1
.\scripts\windows\test_windows.ps1
.\scripts\windows\build_windows.ps1
.\scripts\windows\package_windows.ps1
.\scripts\windows\smoke_windows.ps1
```

Expected executable:

```text
dist\windows\Gmail Рассылка\Gmail Рассылка.exe
```

Expected ZIP:

```text
dist\windows\Gmail Рассылка-5.1.1-windows.zip
```

## macOS Compatibility

The macOS build remains unchanged:

```bash
./scripts/build_macos.sh
./scripts/build_dmg.sh --versioned
```

Stage 5.1 only adds Windows-specific scripts/specs and cross-platform runtime abstractions.

## Limitations

- The Windows `.exe` and ZIP must be built on Windows.
- SmartScreen can warn for unsigned internal PyInstaller builds.
- The Windows package is not code-signed in this stage.
- Live connector tests still require owned credentials and safe-mode controls.
- No social hidden automation was added.
