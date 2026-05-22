param(
    [string]$TaskName = "OnlinePlatformAnalytics_TikTokDailySync",
    [string]$StartTime = "09:30",
    [int]$WindowDays = 5,
    [int]$EndOffsetDays = 2,
    [switch]$UseSystemProfile
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonExe = (Get-Command python).Source
$runnerPath = Join-Path $projectRoot "scripts\run_tiktok_daily_sync.py"

if (-not (Test-Path $runnerPath)) {
    throw "Runner script not found: $runnerPath"
}

$runnerArgs = "`"$runnerPath`" --window-days $WindowDays --end-offset-days $EndOffsetDays"
if ($UseSystemProfile) {
    $runnerArgs += " --use-system-profile"
}

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $runnerArgs -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Daily TikTok Shop sync into PostgreSQL for Online Platform Analytics." `
    -Force | Out-Null

Write-Output "Registered scheduled task '$TaskName' to run daily at $StartTime."
Write-Output "Runner: $runnerPath"
Write-Output "Latest log: $(Join-Path $projectRoot 'logs\tiktok_daily_sync\latest.log')"
