param(
  [switch]$CreateDraft,
  [switch]$AllowPartial
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

$Tag = "v$Version"
$Notes = "docs\RELEASE_NOTES_$($Version.Replace('.', '_')).md"
$AssetDir = "dist\release-assets\v$Version"

$ValidateArgs = @("scripts\release\validate_release.py", "--version", $Version, "--smoke-status", "prepared", "--asset-dir", $AssetDir)
if ((-not $CreateDraft) -or $AllowPartial) {
  $ValidateArgs += @("--allow-missing-macos", "--allow-missing-windows")
}
& $PythonExe @ValidateArgs

$Gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $Gh) {
  Write-Host "GitHub CLI not found. Draft release not created."
  Write-Host "Prepared tag/title: $Tag"
  Write-Host "Prepared notes: $Notes"
  Write-Host "Prepared assets directory: $AssetDir"
  exit 0
}

if (-not $CreateDraft) {
  Write-Host "Dry run only. To create a draft GitHub release, run:"
  Write-Host ".\scripts\release\github_release.ps1 -CreateDraft"
  Write-Host "Use -AllowPartial only for internal partial release prep."
  Write-Host "Tag/title: $Tag"
  Write-Host "Notes: $Notes"
  exit 0
}

$Assets = Get-ChildItem $AssetDir -File | Sort-Object Name | ForEach-Object { $_.FullName }
gh release create $Tag --draft --title $Tag --notes-file $Notes @Assets
Write-Host "Draft GitHub release created: $Tag"
