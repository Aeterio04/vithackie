<#
.SYNOPSIS
    Starts an ngrok tunnel to the local Kawach MCP server (127.0.0.1:8765).

.DESCRIPTION
    Verifies that the Kawach Backend API and MCP HTTP server are running,
    ensures ngrok is installed and authenticated, launches an ngrok HTTP tunnel
    with local introspection disabled (--inspect=false for credential security),
    and saves the ephemeral public URL to scripts/tunnel/.current_url and .env.local.

.PARAMETER Domain
    Optional reserved or static domain (e.g. "my-reserved.ngrok-free.app").
    If omitted on a free tier, ngrok assigns an ephemeral public URL.

.PARAMETER UseTrafficPolicy
    Optional switch to apply the cloud-edge traffic policy (scripts/tunnel/traffic-policy.yml).
    Note: Requires an ngrok plan that supports traffic policies.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Domain,

    [Parameter(Mandatory = $false)]
    [switch]$UseTrafficPolicy
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$PidFile = Join-Path $ScriptDir ".ngrok.pid"
$CurrentUrlFile = Join-Path $ScriptDir ".current_url"
$EnvLocalFile = Join-Path $ProjectRoot ".env.local"
$TrafficPolicyFile = Join-Path $ScriptDir "traffic-policy.yml"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " Kawach Temporary MCP Tunnel Starter" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# 1. Verify Kawach Backend API is running on :8000
Write-Host "`n[1/5] Checking Kawach Backend API on http://127.0.0.1:8000..." -NoNewline
try {
    $backendRes = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -Method GET -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    Write-Host " [OK]" -ForegroundColor Green
} catch {
    # 401 or 403 on protected routes also proves the backend is running
    if ($_.Exception.Response -and ($_.Exception.Response.StatusCode.value__ -in @(200, 401, 403, 404))) {
        Write-Host " [OK]" -ForegroundColor Green
    } else {
        Write-Host " [FAILED]" -ForegroundColor Red
        Write-Host "ERROR: Kawach Backend API is not responding on http://127.0.0.1:8000." -ForegroundColor Red
        Write-Host "Start the backend first in a separate terminal: make backend" -ForegroundColor Yellow
        exit 1
    }
}

# 2. Verify Kawach MCP HTTP Server is running on :8765
Write-Host "[2/5] Checking Kawach MCP HTTP Server on http://127.0.0.1:8765/healthz..." -NoNewline
try {
    $mcpHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8765/healthz" -Method GET -TimeoutSec 3 -ErrorAction Stop
    if ($mcpHealth.ok -eq $true) {
        Write-Host " [OK]" -ForegroundColor Green
    } else {
        throw "Unexpected health response"
    }
} catch {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host "ERROR: Kawach MCP server is not running on http://127.0.0.1:8765." -ForegroundColor Red
    Write-Host "Start it first with:" -ForegroundColor Yellow
    Write-Host "  kawach-mcp --transport http --port 8765" -ForegroundColor White
    exit 1
}

# 3. Verify ngrok CLI installation and authentication
Write-Host "[3/5] Verifying ngrok CLI..." -NoNewline
$ngrokCmd = Get-Command "ngrok" -ErrorAction SilentlyContinue
if (-not $ngrokCmd) {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host "ERROR: ngrok CLI not found in PATH." -ForegroundColor Red
    Write-Host "Install it from https://ngrok.com/download and add it to your PATH." -ForegroundColor Yellow
    exit 1
}

# Check authtoken configuration without printing secret
$hasAuthtoken = $false
$configPaths = @(
    "$env:LOCALAPPDATA\ngrok\ngrok.yml",
    "$env:USERPROFILE\.config\ngrok\ngrok.yml"
)
foreach ($cfg in $configPaths) {
    if (Test-Path $cfg) {
        if (Select-String -Path $cfg -Pattern "authtoken:" -Quiet) {
            $hasAuthtoken = $true
            break
        }
    }
}
if (-not $hasAuthtoken) {
    Write-Host " [FAILED]" -ForegroundColor Red
    Write-Host "ERROR: ngrok is not authenticated on this machine." -ForegroundColor Red
    Write-Host "Authenticate ngrok by running: ngrok config add-authtoken <your-authtoken>" -ForegroundColor Yellow
    exit 1
}
Write-Host " [OK] (Authenticated)" -ForegroundColor Green

# 4. Check if an existing ngrok instance was started by this script
if (Test-Path $PidFile) {
    $existingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($existingPid) {
        $existingProc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProc -and $existingProc.ProcessName -eq "ngrok") {
            Write-Host "`nWARNING: An ngrok tunnel is already running with PID $existingPid." -ForegroundColor Yellow
            Write-Host "Stopping existing tunnel first..."
            Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 5. Build arguments and launch ngrok
Write-Host "[4/5] Launching ngrok HTTP tunnel (inspection disabled for secret protection)..." -NoNewline

$ngrokArgs = @("http", "127.0.0.1:8765", "--inspect=false", "--log=false")

if ($Domain) {
    $ngrokArgs += @("--url", $Domain)
}

if ($UseTrafficPolicy) {
    if (Test-Path $TrafficPolicyFile) {
        $ngrokArgs += @("--traffic-policy-file", $TrafficPolicyFile)
    } else {
        Write-Host "`n[WARN] Traffic policy file not found at $TrafficPolicyFile; skipping." -ForegroundColor Yellow
    }
}

$proc = Start-Process -FilePath "ngrok" -ArgumentList $ngrokArgs -PassThru -WindowStyle Hidden
$proc.Id | Out-File -FilePath $PidFile -Encoding utf8 -Force
Write-Host " [PID $($proc.Id)]" -ForegroundColor Green

# 6. Poll ngrok agent API for public URL
Write-Host "[5/5] Querying public URL from ngrok agent API..." -NoNewline
$publicUrl = $null
$attempts = 0
$maxAttempts = 15

while ($attempts -lt $maxAttempts -and -not $publicUrl) {
    Start-Sleep -Seconds 1
    $attempts++
    try {
        $agentRes = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -Method GET -TimeoutSec 2 -ErrorAction Stop
        if ($agentRes.tunnels -and $agentRes.tunnels.Count -gt 0) {
            $httpsTunnel = $agentRes.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
            if ($httpsTunnel) {
                $publicUrl = $httpsTunnel.public_url
            } else {
                $publicUrl = $agentRes.tunnels[0].public_url
            }
        }
    } catch {
        # Agent API not ready yet, continue polling
    }
}

if (-not $publicUrl) {
    Write-Host " [TIMEOUT]" -ForegroundColor Red
    Write-Host "ERROR: Timed out waiting for ngrok public URL." -ForegroundColor Red
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host " [CONNECTED]" -ForegroundColor Green

# 7. Persist public URL to untracked ephemeral files
$publicUrl | Out-File -FilePath $CurrentUrlFile -Encoding utf8 -Force

# Append or update MCP_PUBLIC_URL in .env.local
$mcpEndpoint = "$publicUrl/mcp"
$envLine = "MCP_PUBLIC_URL=$mcpEndpoint"
if (Test-Path $EnvLocalFile) {
    $envContent = Get-Content $EnvLocalFile
    $filtered = $envContent | Where-Object { $_ -notmatch "^MCP_PUBLIC_URL=" }
    $filtered += $envLine
    $filtered | Out-File -FilePath $EnvLocalFile -Encoding utf8 -Force
} else {
    $envLine | Out-File -FilePath $EnvLocalFile -Encoding utf8 -Force
}

Write-Host "`n========================================================================" -ForegroundColor Green
Write-Host " Kawach Remote MCP Tunnel Active" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "Public MCP Endpoint:  " -NoNewline; Write-Host $mcpEndpoint -ForegroundColor Yellow
Write-Host "Local Target:         http://127.0.0.1:8765/mcp"
Write-Host "Local Inspection:     DISABLED (--inspect=false for credential security)"

if (-not $Domain) {
    Write-Host "`n[NOTICE] Using ephemeral random domain (free tier)." -ForegroundColor Yellow
    Write-Host "         This URL changes on every restart. Send this URL to your tester:" -ForegroundColor Yellow
    Write-Host "         $mcpEndpoint" -ForegroundColor White
}

Write-Host "`nVerify tunnel health:" -ForegroundColor Cyan
Write-Host "  python scripts/verify_remote_mcp.py $mcpEndpoint <token>" -ForegroundColor White

Write-Host "`nTo stop the tunnel:" -ForegroundColor Cyan
Write-Host "  powershell -File scripts/tunnel/stop-ngrok.ps1" -ForegroundColor White
Write-Host "========================================================================`n" -ForegroundColor Green
