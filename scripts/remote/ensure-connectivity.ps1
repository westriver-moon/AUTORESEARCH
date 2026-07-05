param(
    [string] $ExperimentId = "",
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\ssh.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }
if (-not [string]::IsNullOrWhiteSpace($ExperimentId)) { Assert-ExperimentId -ExperimentId $ExperimentId }

$details = [ordered] @{}
$tunnelScript = Find-LocalTunnelScript -Config $config
$details.local_tunnel_script = $tunnelScript

if (-not [string]::IsNullOrWhiteSpace($tunnelScript)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tunnelScript
    $details.local_tunnel_invoked = $true
} else {
    $details.local_tunnel_invoked = $false
}

Start-Sleep -Seconds 1

$sshCheck = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand "exit" `
    -AllowFailure
$details.ssh_exit_code = $sshCheck.exit_code
$details.ssh_output = $sshCheck.output

$proxyPort = [int] $config.ProxyPort
$remoteProxyCommand = "bash -lc " + (Quote-PosixSingle "timeout 2 bash -c ':</dev/tcp/127.0.0.1/$proxyPort' >/dev/null 2>&1")
$proxyCheck = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteProxyCommand `
    -AllowFailure
$details.remote_proxy_port_open = ($proxyCheck.exit_code -eq 0)

$ok = [bool] (($sshCheck.exit_code -eq 0) -and $details.remote_proxy_port_open)
$status = New-StatusObject -ScriptName "ensure-connectivity.ps1" -Ok $ok -ExperimentId $ExperimentId -Details $details

$outPath = ""
if (-not [string]::IsNullOrWhiteSpace($ExperimentId)) {
    $outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "connectivity"
}
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}

