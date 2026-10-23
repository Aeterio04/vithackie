<#
.SYNOPSIS
    Stops the active ngrok tunnel process launched by start-ngrok.ps1.

.DESCRIPTION
    Reads the process ID from scripts/tunnel/.ngrok.pid, safely terminates only
    that ngrok process, and removes temporary state files.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "SilentlyContinue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$PidFile = Join-Path $ScriptDir ".ngrok.pid"
$CurrentUrlFile = Join-Path $ScriptDir ".current_url"
$EnvLocalFile = Join-Path $ProjectRoot ".env.local"

Write-Host "Stopping Kawach ngrok tunnel..." -NoNewline

$stopped = $false

if (Test-Path $PidFile) {
    $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($rawPid) {
        $procId = [int]($rawPid.ToString().Trim())
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "ngrok") {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $stopped = $true
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# If PID didn't catch it, check for any orphan ngrok processes
if (-not $stopped) {
    $orphans = Get-Process -Name "ngrok" -ErrorAction SilentlyContinue
    if ($orphans) {
        $orphans | Stop-Process -Force -ErrorAction SilentlyContinue
        $stopped = $true
    }
}

# Clean up ephemeral URL state
if (Test-Path $CurrentUrlFile) {
    Remove-Item $CurrentUrlFile -Force -ErrorAction SilentlyContinue
}

# Clear MCP_PUBLIC_URL in .env.local
if (Test-Path $EnvLocalFile) {
    $envContent = Get-Content $EnvLocalFile -ErrorAction SilentlyContinue
    if ($envContent) {
        $filtered = $envContent | Where-Object { $_ -notmatch "^MCP_PUBLIC_URL=" }
        $filtered | Out-File -FilePath $EnvLocalFile -Encoding utf8 -Force
    }
}

if ($stopped) {
    Write-Host " [OK] (Process $procId terminated)" -ForegroundColor Green
} else {
    Write-Host " [OK] (No active tunnel process found)" -ForegroundColor Yellow
}
