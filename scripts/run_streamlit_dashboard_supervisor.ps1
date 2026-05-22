$ErrorActionPreference = "Stop"

$projectRoot = "C:\Users\Administrator\DevProjs\OnlinePlatformAnalytics"
$pythonExe = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
$scriptPath = Join-Path $projectRoot "streamlit_app.py"
$logDir = Join-Path $projectRoot "logs\streamlit_supervisor"
$restartDelaySeconds = 5

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Set-Location $projectRoot

function Get-RunningDashboardProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -and
            $_.CommandLine -match [regex]::Escape($scriptPath)
        } |
        Select-Object -First 1
}

while ($true) {
    $existing = Get-RunningDashboardProcess
    if ($existing) {
        Start-Sleep -Seconds $restartDelaySeconds
        continue
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdoutLog = Join-Path $logDir "streamlit-$timestamp.out.log"
    $stderrLog = Join-Path $logDir "streamlit-$timestamp.err.log"

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            "-m",
            "streamlit",
            "run",
            $scriptPath,
            "--server.headless",
            "true",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            "8508"
        ) `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    $process.WaitForExit()
    Start-Sleep -Seconds $restartDelaySeconds
}
