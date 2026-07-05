param(
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$bootstrapRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$remoteScriptRoot = Split-Path -Parent $bootstrapRoot
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\ssh.ps1")

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$root = [string] $config.RemoteProxyRoot
Assert-RemotePath -Path $root -Name "RemoteProxyRoot"

$cmd = "bash -lc " + (Quote-PosixSingle "test -f '$root/proxy-env.sh' && test -f '$root/ensure-vscode-proxy-active.sh'")
$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $cmd `
    -AllowFailure

$ok = ($result.exit_code -eq 0)
$status = New-StatusObject -ScriptName "verify-remote-proxy-prereqs.ps1" -Ok $ok -Details @{
    remote_proxy_root = $root
    exit_code = $result.exit_code
    output = $result.output
}

Write-StatusJson -Data $status -Json:$Json
if (-not $ok) {
    exit 1
}

