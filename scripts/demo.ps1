param(
    [int]$MockPort = 8790,
    [int]$GatewayPort = 8788,
    [string]$PythonPath = "",
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = $PythonPath
if (-not $Python) { $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python) { throw "Python not found. Activate .venv or pass -PythonPath .\.venv\Scripts\python.exe" }
$MockLog = Join-Path ([System.IO.Path]::GetTempPath()) "mcp-sentinel-mock.log"
$MockErrorLog = Join-Path ([System.IO.Path]::GetTempPath()) "mcp-sentinel-mock-error.log"
$GatewayLog = Join-Path ([System.IO.Path]::GetTempPath()) "mcp-sentinel-gateway.log"
$GatewayErrorLog = Join-Path ([System.IO.Path]::GetTempPath()) "mcp-sentinel-gateway-error.log"
$StateFile = Join-Path ([System.IO.Path]::GetTempPath()) "mcp-sentinel-demo-$PID-state.json"
$MockUrl = "http://127.0.0.1:$MockPort"
$GatewayUrl = "http://127.0.0.1:$GatewayPort"

function Invoke-Rpc {
    param([string]$Method, [hashtable]$Params, [object]$Id, [string]$Intent, [string]$Session)
    $Payload = @{jsonrpc="2.0"; method=$Method; params=$Params}
    if ($null -ne $Id) { $Payload.id = $Id }
    $Headers = @{"Authorization"="Bearer demo-client-token-change-this-value-123456"; "X-Sentinel-Intent"=$Intent; "X-Sentinel-Session"=$Session}
    return Invoke-WebRequest -UseBasicParsing -Uri $GatewayUrl -Method Post -ContentType "application/json" `
        -Headers $Headers -Body ($Payload | ConvertTo-Json -Depth 8 -Compress)
}

function Convert-ResponseJson {
    param($Response)
    $Content = $Response.Content
    if ($Content -is [byte[]]) { $Content = [System.Text.Encoding]::UTF8.GetString($Content) }
    return $Content | ConvertFrom-Json
}

Write-Host "MCP Runtime Sentinel local demonstration"
Write-Host "Mock: $MockUrl  Gateway: $GatewayUrl  Audit remains loopback-only."
Set-Location -LiteralPath $ProjectRoot
$MockProcess = $null; $GatewayProcess = $null
try {
    $MockProcess = Start-Process -FilePath $Python -ArgumentList @("-u","-m","sentinel.cli","mock-server","--host","127.0.0.1","--port",$MockPort) `
        -RedirectStandardOutput $MockLog -RedirectStandardError $MockErrorLog -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 600
    & $Python -m sentinel.cli baseline --upstream $MockUrl --server-id demo-mcp --state-file $StateFile --rounds 10
    if ($LASTEXITCODE -ne 0) { throw "Baseline enrollment failed with exit code $LASTEXITCODE" }
    $GatewayProcess = Start-Process -FilePath $Python -ArgumentList @("-u","-m","sentinel.cli","gateway","--host","127.0.0.1","--port",$GatewayPort,"--upstream",$MockUrl,"--server-id","demo-mcp","--auth-token","demo-operator-auth-token-change-this-123456","--client-auth-token","demo-client-token-change-this-value-123456","--state-file",$StateFile,"--allow-tool","safe_read","--allow-tool","calculate","--allow-tool","schema_mutation") `
        -RedirectStandardOutput $GatewayLog -RedirectStandardError $GatewayErrorLog -WindowStyle Hidden -PassThru
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        try { Invoke-RestMethod -Uri "$GatewayUrl/health" | Out-Null; break } catch { Start-Sleep -Milliseconds 200 }
    }

    $Initialize = Invoke-Rpc "initialize" @{protocolVersion="2025-06-18"} 1 "Initialize MCP" "demo"
    $Notification = Invoke-Rpc "notifications/initialized" @{} $null "Initialize MCP" "demo"
    $Tools = Invoke-Rpc "tools/list" @{} 2 "List available tools" "demo"
    $Safe = Invoke-Rpc "tools/call" @{name="safe_read"; arguments=@{record_id="demo-1001"}} 3 "Read record demo-1001" "demo-safe"
    $Blocked = Invoke-Rpc "tools/call" @{name="simulated_delete"; arguments=@{record_id="demo-1001"}} 4 "Read record demo-1001" "demo-blocked"
    $Schema = Invoke-Rpc "tools/call" @{name="schema_mutation"; arguments=@{}} 5 "Read the schema" "demo-schema"
    $Unsupported = Invoke-Rpc "resources/list" @{} 6 "List resources" "demo-error"
    $Malformed = Invoke-WebRequest -UseBasicParsing -Uri $GatewayUrl -Method Post -ContentType "application/json" -Body "{broken"
    $Audit = Invoke-RestMethod -Uri "$GatewayUrl/v1/audit" -Headers @{"Authorization"="Bearer demo-secret-token"}

    $Summary = [ordered]@{
        initialize = Convert-ResponseJson $Initialize
        initialized_notification_status = $Notification.StatusCode
        tools = (($Tools.Content | ConvertFrom-Json).result.tools.name)
        safe_response = Convert-ResponseJson $Safe
        safe_decision = $Safe.Headers["X-Sentinel-Decision"]
        safe_trace = $Safe.Headers["X-Sentinel-Trace"]
        destructive_response = Convert-ResponseJson $Blocked
        destructive_forwarded = $Audit[-2].forwarded
        schema_response = Convert-ResponseJson $Schema
        unsupported_method_response = Convert-ResponseJson $Unsupported
        malformed_json_response = Convert-ResponseJson $Malformed
        audit_records = $Audit.Count
        latest_audit = $Audit[-1]
    }
    $Summary | ConvertTo-Json -Depth 10
    if ($KeepRunning) {
        Write-Host "Servers remain local and running. Press Ctrl+C to stop."
        Wait-Process -Id $GatewayProcess.Id
    }
}
finally {
    if (-not $KeepRunning) {
        if ($GatewayProcess -and -not $GatewayProcess.HasExited) { Stop-Process -Id $GatewayProcess.Id }
        if ($MockProcess -and -not $MockProcess.HasExited) { Stop-Process -Id $MockProcess.Id }
        if (Test-Path -LiteralPath $StateFile) { Remove-Item -LiteralPath $StateFile -Force }
    }
}
