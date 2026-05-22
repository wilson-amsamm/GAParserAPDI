param(
    [string]$TaskName = "OnlinePlatformAnalytics_MetaDailySync",
    [string]$StartTime = "06:15",
    [switch]$Headless
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonExe = (Get-Command python).Source
$runnerPath = Join-Path $projectRoot "scripts\run_meta_daily_sync.py"

if (-not (Test-Path $runnerPath)) {
    throw "Runner script not found: $runnerPath"
}

$runnerArgs = "`"$runnerPath`""
if ($Headless) {
    $runnerArgs += " --headless"
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
    -Description "Daily Meta Business Suite sync into PostgreSQL for Online Platform Analytics." `
    -Force | Out-Null

Write-Output "Registered scheduled task '$TaskName' to run daily at $StartTime."
Write-Output "Runner: $runnerPath"
Write-Output "Latest log: $(Join-Path $projectRoot 'logs\meta_daily_sync\latest.log')"
