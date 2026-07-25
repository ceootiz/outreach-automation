param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

if (-not ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)) {
  Write-Host "Windows package must run on Windows. This script is Windows-ready but was not executed."
  exit 2
}

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  & (Join-Path $PSScriptRoot "setup_windows.ps1")
}

$AppName = "Gmail Рассылка"
$Version = & $PythonExe -c "from src.app_metadata import APP_VERSION; print(APP_VERSION)"
$DistRoot = Join-Path $ProjectDir "dist\windows"
$AppDir = Join-Path $DistRoot $AppName

if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot "build_windows.ps1")
}

if (-not (Test-Path (Join-Path $AppDir "$AppName.exe"))) {
  throw "Windows app is missing. Run scripts\windows\build_windows.ps1 first."
}

$PackageRoot = Join-Path $DistRoot "package"
$PackageAppDir = Join-Path $PackageRoot $AppName
$ZipPath = Join-Path $DistRoot "$AppName-$Version-windows.zip"

Remove-Item $PackageRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $PackageRoot | Out-Null
Copy-Item $AppDir $PackageAppDir -Recurse
Copy-Item "docs\WINDOWS_INSTALL.md" (Join-Path $PackageRoot "WINDOWS_INSTALL.md")
Copy-Item "README_TESTER_RU.txt" (Join-Path $PackageRoot "README_TESTER_RU.txt")
Copy-Item "docs\WINDOWS_CODEX_HANDOFF_RU.md" (Join-Path $PackageRoot "CODEX_WINDOWS_HANDOFF_RU.md")
Copy-Item "launchers\windows\Gmail Рассылка.bat" (Join-Path $PackageRoot "Gmail Рассылка.bat")
Copy-Item "launchers\windows\Gmail Рассылка.ps1" (Join-Path $PackageRoot "Gmail Рассылка.ps1")

$ForbiddenNames = @(
  ".env",
  ".venv",
  "data",
  "logs",
  "exports",
  "imports",
  "cache",
  "credentials",
  "backups",
  "outreach.sqlite",
  "gmail_credentials.enc",
  ".credential_key"
)
$ForbiddenSuffixes = @(".sqlite", ".sqlite3", ".db", ".log")
$PackageEntries = Get-ChildItem $PackageRoot -Recurse -Force
foreach ($Entry in $PackageEntries) {
  if ($ForbiddenNames -contains $Entry.Name.ToLowerInvariant()) {
    throw "Package contains forbidden runtime/secrets item: $($Entry.FullName)"
  }
  if (-not $Entry.PSIsContainer -and $ForbiddenSuffixes -contains $Entry.Extension.ToLowerInvariant()) {
    throw "Package contains forbidden runtime file: $($Entry.FullName)"
  }
}

Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipPath -Force
$Checksum = Get-FileHash -Algorithm SHA256 $ZipPath
$ChecksumPath = "$ZipPath.sha256"
"$($Checksum.Hash.ToLowerInvariant())  $(Split-Path $ZipPath -Leaf)" | Set-Content -Encoding UTF8 $ChecksumPath
Write-Host "Windows package created: $ZipPath"
Write-Host "SHA256 checksum: $ChecksumPath"
