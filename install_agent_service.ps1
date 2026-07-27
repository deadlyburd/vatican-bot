# Vatican Agent — Windows Auto-Start Installer
# Run this ONCE as Administrator to install the agent as a startup task.
# After this, the agent starts automatically every time Windows boots.
#
# Usage:
#   Right-click → "Run as Administrator"
#   OR in PowerShell (admin): .\install_agent_service.ps1

param(
    [string]$AgentName = "my-pc",
    [string]$ExePath = "$PSScriptRoot\VaticanAgent.exe"
)

$TaskName = "VaticanBrowserAgent"
$LogFile  = "$env:USERPROFILE\VaticanAgent.log"

Write-Host "Installing Vatican Browser Agent as Windows startup task..." -ForegroundColor Cyan
Write-Host "Exe: $ExePath"
Write-Host "Agent name: $AgentName"
Write-Host ""

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task." -ForegroundColor Yellow
}

# Build the action — run exe with agent name, log output to file
$Action = New-ScheduledTaskAction `
    -Execute $ExePath `
    -Argument "--agent `"$AgentName`" --minimized" `
    -WorkingDirectory $PSScriptRoot

# Trigger: at logon (starts when user logs in)
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings: restart on failure, run indefinitely
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# Run as current user (so it can open Chrome with your profile)
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Vatican Browser Agent — auto-books Vatican tickets via Telegram snipe" `
    -Force | Out-Null

Write-Host ""
Write-Host "✅ Installed! The agent will now:" -ForegroundColor Green
Write-Host "   • Start automatically when you log into Windows"
Write-Host "   • Restart automatically if it crashes"
Write-Host "   • Run silently in the background (no window)"
Write-Host ""
Write-Host "To start it NOW without rebooting:" -ForegroundColor Cyan
Write-Host "   Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To stop it:" -ForegroundColor Cyan
Write-Host "   Stop-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To uninstall:" -ForegroundColor Cyan
Write-Host "   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""

# Start it immediately
$start = Read-Host "Start the agent now? (y/n)"
if ($start -eq 'y' -or $start -eq 'Y') {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep 2
    $state = (Get-ScheduledTask -TaskName $TaskName).State
    Write-Host "Agent status: $state" -ForegroundColor Green
}
