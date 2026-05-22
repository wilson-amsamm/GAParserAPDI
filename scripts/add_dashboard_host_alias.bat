@echo off
setlocal EnableExtensions

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Please run this batch file as Administrator.
    echo.
    pause
    exit /b 1
)

set "HOST_NAME=quadro-analytics.local"
set "IP_ADDRESS=192.168.2.166"
set "HOSTS_FILE=%SystemRoot%\System32\drivers\etc\hosts"
set "ENTRY=%IP_ADDRESS% %HOST_NAME%"
set "TEMP_FILE=%TEMP%\quadro_analytics_hosts.tmp"

findstr /R /C:"^[ ]*[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*[ ]\+%HOST_NAME%[ ]*$" "%HOSTS_FILE%" >nul 2>&1
if "%errorlevel%"=="0" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$hosts = '%HOSTS_FILE%';" ^
        "$target = '%HOST_NAME%';" ^
        "$entry = '%ENTRY%';" ^
        "$content = Get-Content $hosts;" ^
        "$out = foreach ($line in $content) {" ^
        "  if ($line.Trim() -match ('^\s*\d{1,3}(\.\d{1,3}){3}\s+' + [regex]::Escape($target) + '\s*$')) { $entry } else { $line }" ^
        "};" ^
        "Set-Content -Path $hosts -Value $out -Encoding ASCII"
) else (
    copy "%HOSTS_FILE%" "%TEMP_FILE%" >nul
    echo.>>"%TEMP_FILE%"
    echo %ENTRY%>>"%TEMP_FILE%"
    copy /Y "%TEMP_FILE%" "%HOSTS_FILE%" >nul
    del "%TEMP_FILE%" >nul 2>&1
)

ipconfig /flushdns >nul

echo Hosts entry ensured: %ENTRY%
echo DNS cache flushed.
echo Open: http://%HOST_NAME%:8508/
echo.
pause
exit /b 0
