$ErrorActionPreference = "Stop"

$AppName = "Gmail Рассылка"
$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $LauncherDir "..\..")
$ExePath = Join-Path $ProjectDir "dist\windows\$AppName\$AppName.exe"
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"

Write-Host "Gmail Рассылка"
Write-Host "Project folder: $ProjectDir"
Write-Host ""

try {
  if (Test-Path $ExePath) {
    Write-Host "Starting fresh Windows build from dist\windows..."
    & $ExePath
    exit $LASTEXITCODE
  }

  if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment is missing. Run scripts\windows\setup_windows.ps1 first."
  }

  Write-Host "Built app not found. Starting dev mode..."
  Set-Location $ProjectDir
  & $PythonExe app.py
  exit $LASTEXITCODE
} catch {
  Write-Host ""
  Write-Host "Launch failed: $($_.Exception.Message)"
  Write-Host "See docs\WINDOWS_INSTALL.md for troubleshooting."
  Read-Host "Press Enter to close"
  exit 1
}
