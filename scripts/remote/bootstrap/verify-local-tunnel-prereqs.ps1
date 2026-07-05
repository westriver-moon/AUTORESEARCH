param(
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$bootstrapRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$remoteScriptRoot = Split-Path -Parent $bootstrapRoot
. (Join-Path $remoteScriptRoot "lib\common.ps1")

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot

$tunnelScript = Find-LocalTunnelScript -Config $config
$taskOutput = & schtasks.exe /Query /TN ([string] $config.ProxyTaskName) 2>&1
$taskExists = ($LASTEXITCODE -eq 0)

$status = New-StatusObject -ScriptName "verify-local-tunnel-prereqs.ps1" -Ok ($taskExists -and (-not [string]::IsNullOrWhiteSpace($tunnelScript))) -Details @{
    proxy_task_name = [string] $config.ProxyTaskName
    proxy_task_exists = $taskExists
    local_tunnel_script = $tunnelScript
    local_tunnel_script_exists = -not [string]::IsNullOrWhiteSpace($tunnelScript)
}

Write-StatusJson -Data $status -Json:$Json
if (-not $status.ok) {
    exit 1
}

