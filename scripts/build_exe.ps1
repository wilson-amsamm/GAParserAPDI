param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $SkipTests) {
    python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed."
    }
}

if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}
if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
}
if (Test-Path "release\\GAParserCLI") {
    Remove-Item "release\\GAParserCLI" -Recurse -Force
}

python -m PyInstaller --noconfirm --clean --onefile --name GAParserCLI --paths src ga_summary.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}
python -m PyInstaller --noconfirm --clean --onefile --name GAParserStart --paths src ga_start.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller launcher build failed."
}

$releaseRoot = Join-Path $repoRoot "release\\GAParserCLI"
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $releaseRoot "config") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $releaseRoot "out") -Force | Out-Null

Copy-Item "dist\\GAParserCLI.exe" (Join-Path $releaseRoot "GAParserCLI.exe") -Force
Copy-Item "dist\\GAParserStart.exe" (Join-Path $releaseRoot "GAParserStart.exe") -Force
Copy-Item "README.md" (Join-Path $releaseRoot "README.md") -Force
Copy-Item "config\\properties.example.json" (Join-Path $releaseRoot "config\\properties.example.json") -Force

$quickStart = @"
GAParser CLI Quick Start

1) Copy config\properties.example.json to config\properties.json
2) Easiest: place your key in this folder and rename it to service_account.json
3) Run:

GAParserStart.exe

or direct CLI:
GAParserCLI.exe --menu --config config\properties.json --service-account C:\path\to\service_account.json

Output text file is auto-saved to:
out\website_summary_YYYYMMDD_HHMMSS.txt
"@
$quickStartPath = Join-Path $releaseRoot "QUICKSTART.txt"
Set-Content -Path $quickStartPath -Value $quickStart -Encoding UTF8

Write-Host "Build complete: $releaseRoot"
