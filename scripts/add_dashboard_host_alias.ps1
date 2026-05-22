param(
    [string]$HostName = "quadro-analytics.local",
    [string]$IPAddress = "192.168.2.166"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$entry = "$IPAddress $HostName"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    throw "Run this script in an elevated PowerShell window."
}

$content = if (Test-Path $hostsPath) {
    Get-Content $hostsPath -ErrorAction Stop
} else {
    @()
}

$updated = $false
$newContent = New-Object System.Collections.Generic.List[string]

foreach ($line in $content) {
    $trimmed = $line.Trim()
    if ($trimmed -match "^\s*\d{1,3}(\.\d{1,3}){3}\s+$([regex]::Escape($HostName))\s*$") {
        if (-not $updated) {
            $newContent.Add($entry)
            $updated = $true
        }
        continue
    }
    $newContent.Add($line)
}

if (-not $updated) {
    if ($newContent.Count -gt 0 -and $newContent[$newContent.Count - 1] -ne "") {
        $newContent.Add("")
    }
    $newContent.Add($entry)
}

Set-Content -Path $hostsPath -Value $newContent -Encoding ASCII
ipconfig /flushdns | Out-Null

Write-Host "Hosts entry ensured: $entry"
Write-Host "DNS cache flushed."
Write-Host "Open: http://$HostName`:8508/"
