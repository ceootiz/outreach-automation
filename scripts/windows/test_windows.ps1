$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  & (Join-Path $PSScriptRoot "setup_windows.ps1")
}

$env:QT_QPA_PLATFORM = "offscreen"
$env:OUTREACH_AUTOMATION_DISABLE_ONBOARDING = "1"
$env:OUTREACH_AUTOMATION_CREDENTIAL_BACKEND = "file"

& $PythonExe scripts\qt_doctor.py
& $PythonExe -m pytest tests -q
& $PythonExe -m compileall -q -x "(\.venv|\.pytest_cache|__pycache__|build|dist)" .

$Bash = Get-Command bash -ErrorAction SilentlyContinue
if ($Bash) {
  & bash scripts/check_no_secrets.sh
} else {
  if (git ls-files --error-unmatch .env *> $null) {
    throw ".env is tracked"
  }
  $runtimeFiles = git ls-files data exports logs imports
  if ($runtimeFiles) {
    throw "Runtime files are tracked: $runtimeFiles"
  }
  Write-Host "Basic no-secrets/runtime audit passed (bash unavailable for deep scan)."
}

Write-Host "Windows test pass complete."
