# Vatican Browser Agent — 24/7 Setup via Task Scheduler
# Run this once as Administrator in PowerShell:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup_agent_24_7.ps1

$TaskName = "VaticanBrowserAgent"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = (Get-Command python).Source
$AgentScript = Join-Path $ScriptDir "backend\local_browser_agent.py"

Write-Host "Setting up Vatican Browser Agent 24/7..." -ForegroundColor Cyan
Write-Host "Python: $PythonPath"
Write-Host "Script: $AgentScript"

# Remove existing task if any
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create action
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$AgentScript`"" `
    -WorkingDirectory $ScriptDir

# Triggers: at login + every 5 min (restart if crashed)
$TriggerLogin = New-ScheduledTaskTrigger -AtLogOn
$TriggerRepeat = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) -Once -At (Get-Date)

# Settings: restart on failure, run whether logged in or not
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# Register
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $TriggerLogin `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host ""
Write-Host "SUCCESS! Vatican Browser Agent installed as scheduled task." -ForegroundColor Green
Write-Host ""
Write-Host "Starting agent now..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2

$State = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Agent status: $State" -ForegroundColor $(if ($State -eq 'Running') {'Green'} else {'Yellow'})
Write-Host ""
Write-Host "The agent will:" -ForegroundColor Cyan
Write-Host "  - Start automatically when you log in"
Write-Host "  - Restart automatically if it crashes"
Write-Host "  - Run silently in the background"
Write-Host "  - Open Chrome when a Vatican slot is detected"
Write-Host ""
Write-Host "To check status:  Get-ScheduledTask -TaskName VaticanBrowserAgent"
Write-Host "To stop:          Stop-ScheduledTask -TaskName VaticanBrowserAgent"
Write-Host "To uninstall:     Unregister-ScheduledTask -TaskName VaticanBrowserAgent -Confirm:`$false"
