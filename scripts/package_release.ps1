$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path "release\\GAParserCLI\\GAParserCLI.exe")) {
    throw "Missing release build. Run scripts/build_exe.ps1 first."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$zipPath = "release\\GAParserCLI_$stamp.zip"

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path "release\\GAParserCLI\\*" -DestinationPath $zipPath -Force
Write-Host "Package created: $zipPath"
