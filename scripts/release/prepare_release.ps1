param(
  [switch]$SkipBuild,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = Join-Path $ProjectDir ".venv\bin\python"
}
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

$Version = & $PythonExe -c "from src.app_metadata import APP_VERSION; print(APP_VERSION)"

& $PythonExe scripts\release\verify_git_remote.py

if (-not $SkipTests) {
  if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
    & (Join-Path $PSScriptRoot "..\windows\test_windows.ps1")
  } elseif (Test-Path "./scripts/check_no_secrets.sh") {
    bash ./scripts/check_no_secrets.sh
  }
}

if (-not $SkipBuild) {
  if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
    & (Join-Path $PSScriptRoot "..\windows\package_windows.ps1")
    & (Join-Path $PSScriptRoot "..\windows\smoke_windows.ps1")
    & $PythonExe scripts\release\validate_release.py --version $Version --allow-missing-macos --smoke-status "passed" --asset-dir "dist\release-assets\v$Version"
  } else {
    ./scripts/release/prepare_release.sh
  }
} else {
  & $PythonExe scripts\release\validate_release.py --version $Version --allow-missing-macos --allow-missing-windows --smoke-status "prepared" --asset-dir "dist\release-assets\v$Version"
}

Write-Host "Release preparation complete for v$Version"
