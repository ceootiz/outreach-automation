param(
  [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

if (-not ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)) {
  Write-Host "Windows build must run on Windows. This script is Windows-ready but was not executed."
  exit 2
}

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  & (Join-Path $PSScriptRoot "setup_windows.ps1")
}

& $PythonExe scripts\generate_app_icon.py

$AppName = "Gmail Рассылка"
$IconPath = Join-Path $ProjectDir "resources\icons\app_icon.ico"
$DistRoot = Join-Path $ProjectDir "dist\windows"
$AppDir = Join-Path $DistRoot $AppName
$WorkPath = Join-Path $ProjectDir "build\windows"
$SpecPath = Join-Path $ProjectDir "packaging\windows\Gmail Рассылка Windows.spec"
if (-not (Test-Path $IconPath)) {
  throw "Windows icon missing: $IconPath"
}

if (-not $NoClean) {
  Remove-Item $WorkPath -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $AppDir -Recurse -Force -ErrorAction SilentlyContinue
}

& $PythonExe -m PyInstaller --noconfirm --clean --distpath $DistRoot --workpath $WorkPath $SpecPath

$ExePath = Join-Path $AppDir "$AppName.exe"
$QtPlugin = Get-ChildItem $AppDir -Recurse -Filter "qwindows.dll" | Select-Object -First 1
if (-not (Test-Path $ExePath)) {
  throw "Build failed: missing $ExePath"
}
if (-not $QtPlugin) {
  throw "Build failed: Qt qwindows.dll platform plugin was not packaged."
}

$Version = & $PythonExe -c "from src.app_metadata import APP_VERSION; print(APP_VERSION)"
Write-Host "Windows build created: $AppDir"
Write-Host "App version: $Version"
Write-Host "Qt Windows plugin: $($QtPlugin.FullName)"
