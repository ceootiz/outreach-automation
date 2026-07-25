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
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$QtPlugins = & $PythonExe -c "from PySide6.QtCore import QLibraryInfo; print(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))"
if ($LASTEXITCODE -ne 0) {
  throw "Unable to locate Qt plugins."
}
$QtWindowsPlugin = Join-Path $QtPlugins "platforms\qwindows.dll"
if (-not (Test-Path $QtWindowsPlugin)) {
  throw "Qt Windows platform plugin is missing: $QtWindowsPlugin"
}

$WindowsTests = @(
  "tests\test_stage_5_1_windows_port.py",
  "tests\test_stage_5_1_4_windows_gmail_credentials.py",
  "tests\test_stage_5_1_5_windows_release_handoff.py",
  "tests\test_stage_1_9_production_ready.py::test_corrupt_database_gets_recovery_backup"
)
& $PythonExe -m pytest @WindowsTests -q
if ($LASTEXITCODE -ne 0) {
  throw "Windows release tests failed."
}

& $PythonExe -m compileall -q -x "(\.venv|\.pytest_cache|__pycache__|build|dist)" .
if ($LASTEXITCODE -ne 0) {
  throw "Python compile check failed."
}

if (git ls-files --error-unmatch .env *> $null) {
  throw ".env is tracked"
}
$runtimeFiles = git ls-files data exports logs imports cache credentials
if ($runtimeFiles) {
  throw "Runtime files are tracked: $runtimeFiles"
}
Write-Host "Tracked no-secrets/runtime audit passed."

Write-Host "Windows test pass complete."
