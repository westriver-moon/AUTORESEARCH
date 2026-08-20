param(
    [string] $ProjectRoot = "",
    [string] $RemoteProfile = "",
    [switch] $NonInteractive,
    [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib\common.ps1")
. (Join-Path $PSScriptRoot "lib\config.ps1")
. (Join-Path $PSScriptRoot "lib\profile_session_state.ps1")
. (Join-Path $PSScriptRoot "lib\remote_access.ps1")

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$resolved = Resolve-AutoresearchSessionProfile -ProjectRoot $ProjectRoot -Force:$Force
$selectedProfile = $RemoteProfile
if ([string]::IsNullOrWhiteSpace($selectedProfile)) {
    $selectedProfile = $resolved.profile
}
Save-AutoresearchSessionProfile -ProjectRoot $ProjectRoot -Profile $selectedProfile

$config = Get-AutoresearchRemoteAccess `
    -ProjectRoot $ProjectRoot `
    -RemoteProfile $selectedProfile
[pscustomobject]@{
    remote_profile = [string] $config.SelectedRemoteProfile
    remote_host = [string] $config.RemoteHost
    locked = [bool] $resolved.locked
    session = Get-AutoresearchSessionId
} | ConvertTo-Json -Compress
