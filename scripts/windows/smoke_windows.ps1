param(
  [string]$ExePath = ""
)

$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

if (-not ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)) {
  Write-Host "Windows smoke must run on Windows. This script is Windows-ready but was not executed."
  exit 2
}

$AppName = "Gmail Рассылка"
if (-not $ExePath) {
  $ExePath = Join-Path $ProjectDir "dist\windows\$AppName\$AppName.exe"
}
if (-not (Test-Path $ExePath)) {
  throw "Executable not found: $ExePath"
}

$SmokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("outreach_windows_smoke_" + [Guid]::NewGuid().ToString("N"))
$AppData = Join-Path $SmokeRoot "AppData\Roaming\$AppName"
New-Item -ItemType Directory -Path $AppData | Out-Null

$env:OUTREACH_AUTOMATION_APP_DIR = $AppData
$env:OUTREACH_AUTOMATION_CREDENTIAL_BACKEND = "file"
$env:OUTREACH_AUTOMATION_DISABLE_ONBOARDING = "1"
$env:OUTREACH_AUTOMATION_SMOKE_EXIT_MS = "1000"
$env:QT_QPA_PLATFORM = ""

& $ExePath
if ($LASTEXITCODE -ne 0) {
  throw "Windows app smoke failed with exit code $LASTEXITCODE"
}

foreach ($dir in @("data", "exports", "imports", "logs", "backups", "cache")) {
  $path = Join-Path $AppData $dir
  if (-not (Test-Path $path)) {
    throw "Expected app data directory missing: $path"
  }
}

Write-Host "Windows smoke passed."
Write-Host "App data dir: $AppData"
