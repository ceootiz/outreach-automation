param(
  [switch]$Dev,
  [int]$SmokeExitMs = 0
)

$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

$AppName = "Gmail Рассылка"
$ExePath = Join-Path $ProjectDir "dist\windows\$AppName\$AppName.exe"
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if ($SmokeExitMs -gt 0) {
  $env:OUTREACH_AUTOMATION_SMOKE_EXIT_MS = [string]$SmokeExitMs
}

if ((-not $Dev) -and (Test-Path $ExePath)) {
  Write-Host "Starting $AppName from dist\windows..."
  & $ExePath
  exit $LASTEXITCODE
}

if (-not (Test-Path $PythonExe)) {
  Write-Host ".venv is missing. Running setup first..."
  & (Join-Path $PSScriptRoot "setup_windows.ps1")
}

Write-Host "Starting $AppName in dev mode..."
& $PythonExe app.py
exit $LASTEXITCODE
