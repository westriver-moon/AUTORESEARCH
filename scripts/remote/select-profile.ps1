param(
    [string] $ProjectRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib\common.ps1")
. (Join-Path $PSScriptRoot "lib\config.ps1")
. (Join-Path $PSScriptRoot "lib\remote_access.ps1")

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$config = Get-AutoresearchRemoteAccess -ProjectRoot $ProjectRoot -AllowInteractiveProfileSelection
[pscustomobject]@{
    remote_profile = [string] $config.SelectedRemoteProfile
    remote_host = [string] $config.RemoteHost
} | ConvertTo-Json -Compress
