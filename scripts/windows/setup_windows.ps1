param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectDir

function Find-Python {
  $candidates = @(
    @("py", "-3.12"),
    @("py", "-3.11"),
    @("python", "")
  )
  foreach ($candidate in $candidates) {
    $exe = $candidate[0]
    $arg = $candidate[1]
    try {
      if ($arg) {
        & $exe $arg -c "import sys; print(sys.version)" *> $null
      } else {
        & $exe -c "import sys; print(sys.version)" *> $null
      }
      return $candidate
    } catch {
      continue
    }
  }
  throw "Python 3.11+ was not found. Install Python from python.org and enable 'Add Python to PATH'."
}

if ($Force -and (Test-Path ".venv")) {
  Remove-Item ".venv" -Recurse -Force
}

if (-not (Test-Path ".venv")) {
  $python = Find-Python
  if ($python[1]) {
    & $python[0] $python[1] -m venv .venv
  } else {
    & $python[0] -m venv .venv
  }
}

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  throw "Virtual environment is incomplete: $PythonExe"
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r requirements.txt

Write-Host "Windows setup complete."
Write-Host "Run: .\scripts\windows\run_windows.ps1"
