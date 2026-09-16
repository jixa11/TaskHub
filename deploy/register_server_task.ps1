param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [string]$TaskName = "TaskHub Server"
)
$ErrorActionPreference = "Stop"
$exe = Join-Path $InstallDir "TaskHub.exe"
$config = Join-Path $InstallDir "taskhub_config.json"
if (-not (Test-Path $exe)) { throw "Server executable not found: $exe" }
if (-not (Test-Path $config)) { throw "Configuration not found: $config" }

$action = New-ScheduledTaskAction -Execute $exe -Argument "--server" -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started: $TaskName"
